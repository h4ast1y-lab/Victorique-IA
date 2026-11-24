import json
from pathlib import Path

import pytest

from app.config import BASE_DIR
from app.core.assistant import assistant_engine, CANCELLED_MARKER
from app.memory.conversation_store import conversation_store
from app.models.ollama_client import ollama_client


async def _fake_tokens(*args, **kwargs):
    yield "Resposta "
    yield "local "
    yield "de teste."


async def _fake_context(*args, **kwargs):
    return {"system_prompt": "teste", "messages": [{"role": "user", "content": "oi"}], "sources": []}


@pytest.mark.asyncio
async def test_stream_meta_done_and_conversation_id(monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_stream", _fake_tokens)
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", _fake_context)

    conv = conversation_store.create_conversation(title="Teste SSE")
    events = []
    async for chunk in assistant_engine.chat_stream(
        conversation_id=conv["id"], user_message="oi", enable_rag=False
    ):
        events.append(json.loads(chunk.replace("data: ", "")))

    assert events[0]["type"] == "meta"
    assert events[0]["conversation_id"] == conv["id"]
    done = [e for e in events if e["type"] == "done"][-1]
    assert done["conversation_id"] == conv["id"]
    assert done["message_id"]
    assert "Resposta local de teste." in done["content"]

    messages = conversation_store.get_messages(conv["id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_cancellation_persists_partial_answer(monkeypatch):
    async def many_tokens(*args, **kwargs):
        for i in range(50):
            yield f"token{i} "

    monkeypatch.setattr(ollama_client, "chat_stream", many_tokens)
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", _fake_context)

    conv = conversation_store.create_conversation(title="Teste cancelamento")
    agen = assistant_engine.chat_stream(
        conversation_id=conv["id"], user_message="gere bastante", enable_rag=False
    )
    seen = 0
    async for _ in agen:
        seen += 1
        if seen >= 3:
            break
    await agen.aclose()

    messages = conversation_store.get_messages(conv["id"])
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert assistant_msgs, "a resposta parcial deve ser persistida"
    assert CANCELLED_MARKER.strip() in assistant_msgs[-1]["content"]
    conversation_store.delete_conversation(conv["id"])


def test_chat_endpoint_streams_meta_and_done(client, monkeypatch):
    monkeypatch.setattr(ollama_client, "chat_stream", _fake_tokens)
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", _fake_context)

    with client.stream(
        "POST",
        "/api/chat",
        json={"conversation_id": "", "message": "oi", "enable_rag": False},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = []
    for block in body.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "done"
    assert events[0]["conversation_id"] == events[-1]["conversation_id"]


def test_ui_is_offline_and_handlers_exist():
    ui_dir = BASE_DIR / "app" / "ui"
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    js = (ui_dir / "js" / "app.js").read_text(encoding="utf-8")
    css = (ui_dir / "css" / "style.css").read_text(encoding="utf-8")

    assert "cdn." not in html.lower()
    assert "https://" not in html
    assert "marked.min.js" not in html
    assert (ui_dir / "js" / "markdown.js").exists()
    assert "renderMarkdown" in (ui_dir / "js" / "markdown.js").read_text(encoding="utf-8")

    for snippet in [
        "function openLibraryModal",
        "btnCreateProject",
        "btnCreateMemory",
        "$('btnStop').addEventListener",
        "AbortController",
        "conversation_id",
        "authorization_required",
        "tool_result",
        "appendToolEvent",
    ]:
        assert snippet in js, f"handler ausente: {snippet}"

    for element_id in [
        "projectModal", "memoryModal", "libraryModal", "settingModel",
        "btnSaveProject", "btnSaveMemory", "btnCreateBackup",
    ]:
        assert f'id="{element_id}"' in html, f"elemento ausente: {element_id}"

    assert "http://" not in css and "https://" not in css and "@import" not in css

    # Every static $(...) lookup used by app.js must exist in the HTML.
    import re
    referenced = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", js))
    for ref in referenced:
        assert f'id="{ref}"' in html, f"app.js referencia id inexistente: {ref}"


def test_markdown_renderer_escapes_html():
    js = (BASE_DIR / "app" / "ui" / "js" / "markdown.js").read_text(encoding="utf-8")
    # Structural guarantees: escaping exists and links are restricted.
    assert "escapeHtml" in js
    assert "javascript:" in js
    assert "target=\"_blank\"" in js


def test_markdown_renderer_blocks_xss_in_node(tmp_path):
    """Behavioral check: executed with Node when available (skipped otherwise)."""
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível")

    harness = tmp_path / "harness.js"
    harness.write_text(
        """
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync(process.argv[2], 'utf8');
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const render = sandbox.window.renderMarkdown;
console.log(JSON.stringify({
  tag: render('<img src=x onerror=alert(1)>'),
  js: render('[clique](javascript:alert(1))'),
  proto: render('[clique](//evil.example/x)'),
  bold: render('**forte**'),
  code: render('```html\\n<script>alert(1)</script>\\n```'),
  table: render('| A | <b>B</b> |\\n|---|:-:|\\n| **1** | 2 |')
}));
""",
        encoding="utf-8",
    )
    md_path = BASE_DIR / "app" / "ui" / "js" / "markdown.js"
    result = subprocess.run(
        [node, str(harness), str(md_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    assert "&lt;img" in data["tag"] and "<img" not in data["tag"]
    assert "href" not in data["js"]
    assert "href" not in data["proto"]
    assert "<strong>forte</strong>" in data["bold"]
    assert "&lt;script&gt;" in data["code"] and "<script>" not in data["code"]
    assert "<table>" in data["table"] and "<th>A</th>" in data["table"]
    assert "<strong>1</strong>" in data["table"] and "text-align:center" in data["table"]
    assert "&lt;b&gt;" in data["table"] and "<b>" not in data["table"]


def test_index_loads_katex_locally():
    ui_dir = BASE_DIR / "app" / "ui"
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    assert '<script src="/ui/vendor/katex/katex.min.js"></script>' in html
    assert 'href="/ui/vendor/katex/katex.min.css"' in html
    assert html.index("katex.min.js") < html.index("/ui/js/markdown.js")
    vendor = ui_dir / "vendor" / "katex"
    assert (vendor / "LICENSE").exists()
    css = (vendor / "katex.min.css").read_text(encoding="utf-8")
    assert "http" not in css  # fontes locais, nada de CDN
    for name in __import__("re").findall(r"url\(fonts/([^)]+)\)", css):
        assert (vendor / "fonts" / name).exists(), name


def test_markdown_renders_math_but_not_money_in_node(tmp_path):
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js não disponível")
    harness = tmp_path / "math.js"
    harness.write_text(
        """
const fs = require('fs'), vm = require('vm');
const sandbox = { window: {} };
sandbox.self = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), sandbox);
sandbox.window.katex = sandbox.window.katex || sandbox.katex;
vm.runInContext(fs.readFileSync(process.argv[3], 'utf8'), sandbox);
const r = sandbox.window.renderMarkdown;
const B = String.fromCharCode(92), NL = String.fromCharCode(10), T = String.fromCharCode(96);
console.log(JSON.stringify({
  money: r('Custa R$ 10 e R$ 20, ou $5 e $8.'),
  inline: r('A area e $A = ' + B + 'pi r^2$.'),
  paren: r('Seja ' + B + '(x^2' + B + ').'),
  display: r('Veja:' + NL + '$$' + B + 'frac12$$' + NL + 'fim'),
  code: r('Use ' + T + '$HOME$' + T + '.'),
  broken: r('$' + B + 'frac{1$ <img src=x>'),
}));
""",
        encoding="utf-8",
    )
    vendor = BASE_DIR / "app" / "ui" / "vendor" / "katex" / "katex.min.js"
    md_path = BASE_DIR / "app" / "ui" / "js" / "markdown.js"
    result = subprocess.run(
        [node, str(harness), str(vendor), str(md_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "katex" not in data["money"] and "R$ 10 e R$ 20" in data["money"]
    assert 'class="katex"' in data["inline"] and "$" not in data["inline"]
    assert 'class="katex"' in data["paren"]
    assert '<div class="math-block">' in data["display"] and "katex-display" in data["display"]
    assert "<code>$HOME$</code>" in data["code"] and "katex" not in data["code"]
    assert "katex-error" in data["broken"] and "<img" not in data["broken"]


def test_mini_chat_page_is_offline_and_complete():
    import re
    ui_dir = BASE_DIR / "app" / "ui"
    html = (ui_dir / "mini.html").read_text(encoding="utf-8")
    js = (ui_dir / "js" / "mini.js").read_text(encoding="utf-8")
    assert "https://" not in html and "http://" not in html and "cdn." not in html.lower()
    order = ["/ui/vendor/katex/katex.min.js", "/ui/js/markdown.js", "/ui/js/thought.js", "/ui/js/mini.js"]
    positions = [html.index(src) for src in order]
    assert positions == sorted(positions)
    for ref in set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", js)):
        assert f'id="{ref}"' in html, f"mini.js referencia id inexistente: {ref}"
    for symbol in set(re.findall(r'href="#i-([a-z-]+)"', html)) | set(re.findall(r"thoughtIcon\('([a-z-]+)'\)",
                                                                                 (ui_dir / "js" / "thought.js").read_text(encoding="utf-8"))):
        assert f'<symbol id="i-{symbol}"' in html, f"ícone ausente no mini: {symbol}"
    assert "deep_thinking" in js and "mini_conversation_id" in js and "/api/mascot/open-conversation" in js


def test_index_loads_the_shared_thought_box_before_app():
    html = (BASE_DIR / "app" / "ui" / "index.html").read_text(encoding="utf-8")
    assert html.index("/ui/js/thought.js") < html.index("/ui/js/app.js")


def test_library_hall_page_is_wired():
    import re
    import subprocess
    import shutil
    ui_dir = BASE_DIR / "app" / "ui"
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    js = (ui_dir / "js" / "library.js").read_text(encoding="utf-8")
    assert html.index("/ui/js/app.js") < html.index("/ui/js/library.js")
    for ref in set(re.findall(r"byId\('([A-Za-z0-9_-]+)'\)", js)):
        assert f'id="{ref}"' in html, f"library.js referencia id inexistente: {ref}"
    for symbol in set(re.findall(r'href="#i-([a-z-]+)"', js)):
        assert f'<symbol id="i-{symbol}"' in html, f"ícone ausente: {symbol}"
    # The old document tab is now "Documentos"; the hall is the new "Biblioteca".
    assert 'data-tab="hall"' in html and 'id="paneHall"' in html and 'id="paneLibrary"' in html
    assert "https://" not in js and "http://" not in js
    node = shutil.which("node")
    if node:
        subprocess.run([node, "--check", str(ui_dir / "js" / "library.js")], check=True)


def test_library_hall_follows_her_presence():
    """One Victorique: the hall shows her only when the server says she is there."""
    ui_dir = BASE_DIR / "app" / "ui"
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    js = (ui_dir / "js" / "library.js").read_text(encoding="utf-8")
    assert 'id="btnLibraryCall"' in html
    for needle in ("applyPresence", "reportHall", "visibilitychange", "/api/library/presence",
                   "left_hall", "hall_open", "herWhere", "doorOpen"):
        assert needle in js, needle


def test_library_hand_edits_are_wired():
    """Drag a book to another shelf or the cart, right-click it, or use the card."""
    ui_dir = BASE_DIR / "app" / "ui"
    html = (ui_dir / "index.html").read_text(encoding="utf-8")
    js = (ui_dir / "js" / "library.js").read_text(encoding="utf-8")
    for ident in ("btnBookMove", "btnBookRename", "btnBookReserve", "bookMoveList",
                  "bookRenameForm", "bookRenameInput", "bookMenu"):
        assert f'id="{ident}"' in html, ident
    for route in ("/api/library/books/move", "/api/library/books/rename", "/api/library/books/reserve"):
        assert route in js, route
    assert "contextmenu" in js and "bookDrag" in js


def test_index_page_is_never_cached(client):
    """A stale index.html with a new library.js breaks the hall after an update."""
    r = client.get("/")
    assert r.status_code == 200 and "no-store" in r.headers.get("cache-control", "")


def test_hall_waits_for_her_to_leave_the_desktop():
    """While she walks to her door on the desktop ("entrando") the hall must not show her."""
    js = (BASE_DIR / "app" / "ui" / "js" / "library.js").read_text(encoding="utf-8")
    body = js.split("function applyPresence", 1)[1].split("\n  function ", 1)[0]
    assert "const here = p.state === 'biblioteca';" in body
    assert "const onTheWay = p.state === 'entrando';" in body
    assert "Ela está a caminho da porta" in js
