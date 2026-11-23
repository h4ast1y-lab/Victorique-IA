import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def configure_console():
    """Avoid mojibake in cmd/PowerShell consoles when possible."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def ollama_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def ensure_ollama_running():
    """Checks if Ollama daemon is running, otherwise launches it."""
    try:
        r = httpx.get(f"{ollama_url()}/api/version", timeout=2.0)
        if r.status_code == 200:
            print("[OK] Ollama já está em execução.")
            return True
    except Exception:
        pass

    ollama_path = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    if ollama_path.exists():
        print("Iniciando serviço local do Ollama em segundo plano...")
        subprocess.Popen(
            [str(ollama_path), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        time.sleep(3)
        return True

    print("[AVISO] Executável do Ollama não encontrado no caminho padrão.")
    print("        O chat local não funcionará até iniciar o Ollama manualmente.")
    return False


def run_backend():
    """Runs Uvicorn ASGI server in a background thread."""
    from app.main import app
    from app.config import settings
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")


def wait_for_backend(url: str, timeout: float = 12.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=3.0)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.3)
    return False


def check_configured_model():
    """Warns (without downloading anything) when the configured model is absent."""
    try:
        from app.config import settings
        r = httpx.get(f"{ollama_url()}/api/tags", timeout=3.0)
        names = [m.get("name") for m in r.json().get("models", [])]
        configured = settings.default_model
        # The UI may have persisted a different model in the settings table.
        try:
            from app.memory.database import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = 'default_model'"
                ).fetchone()
                if row and row["value"]:
                    configured = row["value"]
        except Exception:
            pass
        if configured not in names:
            print(f"[AVISO] Modelo configurado '{configured}' não está instalado.")
            print(f"        Disponíveis: {', '.join(n for n in names if n) or '(nenhum)'}")
        else:
            print(f"[OK] Modelo configurado: {configured}")
    except Exception:
        pass


def main():
    configure_console()
    print("=" * 60)
    print("  Iniciando Victorique (Desktop)")
    print("=" * 60)

    args = set(sys.argv[1:])
    headless = "--server" in args
    use_browser = "--browser" in args or headless

    if "--no-ollama" not in args:
        ensure_ollama_running()

    from app.config import settings
    app_url = f"http://{settings.host}:{settings.port}"

    backend_thread = threading.Thread(target=run_backend, daemon=True)
    backend_thread.start()

    print(f"Aguardando servidor local em {app_url}...")
    if not wait_for_backend(f"{app_url}/api/ping", timeout=30.0):
        print("Erro: o servidor backend não respondeu a tempo.")
        print("Verifique se a porta está ocupada e execute novamente.")
        sys.exit(1)

    print("[OK] Backend inicializado com sucesso!")
    check_configured_model()

    if headless:
        print(f"Modo servidor: interface em {app_url} (Ctrl+C para encerrar).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nEncerrando assistente.")
        return

    if use_browser:
        import webbrowser
        print(f"Abrindo interface no navegador: {app_url}")
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nEncerrando assistente.")
        return

    try:
        import webview
        print("Abrindo janela de desktop nativa (WebView2)...")
        webview.create_window(
            title="Victorique",
            url=app_url,
            width=1200,
            height=820,
            min_size=(920, 600),
            text_select=True
        )
        webview.start()
    except Exception as e:
        print(f"Aviso ao abrir janela nativa: {e}. Alternando para navegador padrão...")
        import webbrowser
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
