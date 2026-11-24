import re
import urllib.parse
from typing import Dict, Any, List
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


def _is_safe_public_url(url: str) -> bool:
    """Verifica se a URL é pública e segura, bloqueando SSRF em localhost ou redes privadas."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        # Bloqueia localhost e loopbacks
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        # Bloqueia ranges de rede privada comuns
        if (
            host.startswith("10.")
            or host.startswith("192.168.")
            or host.startswith("169.254.")
        ):
            return False
        return True
    except Exception:
        return False


async def read_url(url: str, max_chars: int = 6000) -> Dict[str, Any]:
    """
    Lê e extrai o conteúdo em texto limpo de uma página web específica.
    Requisito de segurança: deve ser autorizada explicitamente pelo usuário.
    """
    url = url.strip()
    if not _is_safe_public_url(url):
        return {
            "url": url,
            "error": "URL inválida ou não permitida (apenas URLs públicas http/https são aceitas).",
            "status": "error"
        }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return {
                    "url": url,
                    "error": f"Não foi possível acessar a página (HTTP {resp.status_code})",
                    "status": "error"
                }

            html = resp.text
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
