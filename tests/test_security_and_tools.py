import pytest
from app.security.path_guard import path_guard
from app.security.permissions import security_manager, ActionCategory
from app.tools.system_tools import calculate, get_system_info
from app.tools.registry import tool_registry

def test_path_guard_whitelist_and_traversal():
    # Valid path inside project data dir
    from app.config import DATA_DIR
    valid_file = str(DATA_DIR / "test.txt")
    assert path_guard.is_safe_path(valid_file) is True

    # Path traversal attack attempt
    traversal_path = str(DATA_DIR / ".." / ".." / "Windows" / "System32" / "cmd.exe")
    assert path_guard.is_safe_path(traversal_path) is False

    with pytest.raises(PermissionError):
        path_guard.validate_and_resolve(traversal_path)

def test_safe_calculate_tool():
    res1 = calculate("12 * 12")
    assert res1["status"] == "success"
    assert res1["result"] == 144

    res2 = calculate("100 / 4 + 25")
    assert res2["status"] == "success"
    assert res2["result"] == 50.0

    # Malicious code injection attempt should fail safely
    res3 = calculate("__import__('os').system('dir')")
    assert res3["status"] == "error"

def test_system_info_tool():
    info = get_system_info()
    assert "os" in info
    assert "disk_c" in info
    assert info["disk_c"]["free_gb"] > 0

@pytest.mark.asyncio
async def test_tool_authorization_barrier():
    # Attempting to execute write_file without prior authorization
    result = await tool_registry.execute_tool(
        name="write_file",
        params={"path": "test.txt", "content": "hello"},
        authorized=False
    )
    assert result["status"] == "requires_authorization"
    assert "action_id" in result
    assert result["category"] == ActionCategory.REQUIRES_AUTH.value


def test_read_file_extracts_pdf_pages_and_supports_query(tmp_path, monkeypatch):
    from app.config import DATA_DIR
    from app.tools.file_tools import read_file

    target_dir = DATA_DIR / "test_docs_tmp"
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / "husserl.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%binary-garbage\n")

    class _FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class _FakeReader:
        def __init__(self, _path):
            self.pages = [
                _FakePage("Página 1: Introdução à fenomenologia."),
                _FakePage("Página 2: Redução fenomenológica e epoche."),
                _FakePage("Página 3: A crítica do conhecimento."),
                _FakePage("Página 4: Capítulo final sobre evidência."),
            ]

    monkeypatch.setattr("pypdf.PdfReader", _FakeReader)
    try:
        res = read_file(str(pdf_path))
        assert res["format"] == "pdf"
        assert res["total_pages"] == 4
        assert res["start_page"] == 1 and res["end_page"] == 3
        assert "Introdução à fenomenologia" in res["content"]
        assert "Capítulo final" not in res["content"]
        assert "%binary-garbage" not in res["content"]

        res_p4 = read_file(str(pdf_path), start_page=4, end_page=4)
        assert res_p4["start_page"] == 4 and res_p4["end_page"] == 4
        assert "Capítulo final" in res_p4["content"]

        res_q = read_file(str(pdf_path), query="epoche")
        assert res_q["matches"] == 1
        assert "[Página 2]" in res_q["content"]
        assert "epoche" in res_q["content"]
    finally:
        pdf_path.unlink(missing_ok=True)
        try:
            target_dir.rmdir()
        except OSError:
            pass
