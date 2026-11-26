import asyncio
import ipaddress
import re
import socket
import urllib.parse
from typing import Any, Dict
import httpx

async def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Executes a web search via DuckDuckGo lite HTML parser.
    Mandatory requirement: Must be authorized by the user before invocation.
    """
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    results = []
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return {
                "query": query,
                "error": f"Falha na busca web (status {resp.status_code})",
                "results": []
            }

        html = resp.text
        # Extract title and snippet patterns
        links = re.findall(r'<a class="result__url" href="([^"]+)">([^<]+)</a>', html)
        snippets = re.findall(r'<a class="result__snippet[^>]*>([\s\S]*?)</a>', html)

        for i in range(min(len(links), len(snippets), max_results)):
            link_url, display_url = links[i]
            # Strip html tags from snippet
            clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            # Duckduckgo redirect link cleanup
            if "uddg=" in link_url:
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(link_url).query)
                real_url = parsed_q.get("uddg", [link_url])[0]
            else:
                real_url = link_url

            results.append({
                "title": display_url.strip(),
                "url": real_url,
                "snippet": clean_snippet
            })

    return {
        "query": query,
        "total_found": len(results),
        "results": results,
        "source": "Web (DuckDuckGo)"
    }


MAX_REDIRECTS = 5
MAX_PAGE_BYTES = 3 * 1024 * 1024  # a page bigger than this is cut before parsing
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")


def _ip_is_public(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # is_global is False for private, loopback, link-local, CGNAT (100.64/10),
    # reserved and unspecified ranges, in IPv4 and IPv6 alike.
    return ip.is_global and not ip.is_multicast


def _is_safe_public_url(url: str) -> bool:
    """Syntactic check: http(s), a host, and no obviously internal name or IP.

    The host is resolved again right before each request (see _host_is_public),
    which also catches names and odd notations that point inside the network.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or parsed.username or parsed.password:
            return False
        if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
            return False
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            return True  # a name: resolved and checked before connecting
        return _ip_is_public(host)
    except Exception:
        return False


def _host_is_public(host: str) -> bool:
    """Every address the host resolves to must be public (blocks SSRF)."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    return bool(infos) and all(_ip_is_public(str(info[4][0])) for info in infos)


def _blocked(url: str, reason: str) -> Dict[str, Any]:
    return {"url": url, "error": reason, "status": "error"}


async def read_url(url: str, max_chars: int = 6000) -> Dict[str, Any]:
    """
    Lê e extrai o conteúdo em texto limpo de uma página web específica.
    Requisito de segurança: deve ser autorizada explicitamente pelo usuário.
    """
    url = (url or "").strip()
    if not _is_safe_public_url(url):
        return _blocked(url, "URL inválida ou não permitida (apenas URLs públicas http/https são aceitas).")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        # Redirects are followed by hand so every hop is checked again: a
        # public page must not bounce the request to 127.0.0.1 or the LAN.
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            current = url
            for _hop in range(MAX_REDIRECTS + 1):
                host = urllib.parse.urlparse(current).hostname or ""
                if not await asyncio.to_thread(_host_is_public, host):
                    return _blocked(current, "Endereço interno ou inexistente; só páginas públicas podem ser lidas.")
                async with client.stream("GET", current, headers=headers) as resp:
                    if resp.is_redirect and resp.headers.get("location"):
                        current = urllib.parse.urljoin(str(resp.url), resp.headers["location"])
                        if not _is_safe_public_url(current):
                            return _blocked(current, "A página redirecionou para um endereço não permitido.")
                        continue
                    if resp.status_code != 200:
                        return _blocked(current, f"Não foi possível acessar a página (HTTP {resp.status_code})")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= MAX_PAGE_BYTES:
                            break
                    try:
                        html = bytes(body[:MAX_PAGE_BYTES]).decode(resp.encoding or "utf-8", errors="replace")
                    except LookupError:  # unknown charset in the headers
                        html = bytes(body[:MAX_PAGE_BYTES]).decode("utf-8", errors="replace")
                    break
            else:
                return _blocked(url, "Redirecionamentos demais.")
            url = current
            # Extrai título
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "Sem título"
            title = re.sub(r"\s+", " ", title)

            # Remove scripts, estilos e navegações
            clean = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<style.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<svg.*?</svg>", "", clean, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<nav.*?</nav>", "", clean, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<header.*?</header>", "", clean, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<footer.*?</footer>", "", clean, flags=re.DOTALL | re.IGNORECASE)
            # Remove tags HTML
            clean = re.sub(r"<[^>]+>", " ", clean)
            # Normaliza espaços
            clean = re.sub(r"\s+", " ", clean).strip()

            if len(clean) > max_chars:
                clean = clean[:max_chars] + "... [conteúdo truncado por limite de tamanho]"

            return {
                "url": url,
                "title": title,
                "content": clean,
                "status": "success",
                "length_chars": len(clean),
                "source": "Web (Página externa)"
            }
    except Exception as e:
        return {
            "url": url,
            "error": f"Erro de conexão ao acessar a página: {str(e)}",
            "status": "error"
        }
