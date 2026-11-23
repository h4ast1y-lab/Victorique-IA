import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent

# Caminho padrão da instalação local do llama.cpp (já presente na máquina).
DEFAULT_LLAMA_CPP_DIR = Path(
    os.environ.get("LLAMA_CPP_DIR", r"C:\Users\Usuário\llama.cpp")
)
DEFAULT_LLAMA_CPP_MODEL = (
    DEFAULT_LLAMA_CPP_DIR / "models" / "Qwen_Qwen3.5-9B-IQ4_XS.gguf"
)

# Data location can be overridden for tests or portable installs.
# Never point this at user data you do not intend to modify.
DATA_DIR = Path(os.environ.get("ASSISTANT_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DOCS_DIR = DATA_DIR / "documents"
BACKUPS_DIR = DATA_DIR / "backups"
DB_PATH = Path(os.environ.get("ASSISTANT_DB_PATH", str(DATA_DIR / "assistant.db"))).expanduser().resolve()

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_dirs(name: str, defaults: list) -> list:
    raw = os.environ.get(name)
    if raw:
        items = [p.strip() for p in raw.split(";") if p.strip()]
        if items:
            return items
    return defaults


class Settings(BaseModel):
    app_name: str = "Victorique"
    version: str = "1.1.0"
    host: str = "127.0.0.1"
    port: int = _env_int("ASSISTANT_PORT", 8765)
    ollama_base_url: str = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    # Requested by the user and verified as installed on this machine.
    # qwen2.5-coder:7b needs ~5.2 GB VRAM at 4096 ctx, so the GTX 1660 Super
    # (6 GB) offloads part of the layers to CPU. qwen2.5:3b runs 100% on GPU.
    default_model: str = os.environ.get("ASSISTANT_MODEL", "qwen2.5-coder:7b")
    embedding_model: str = os.environ.get("ASSISTANT_EMBEDDING_MODEL", "nomic-embed-text")
    # Contexto duplicado (8192) e tokens de saída ampliados (4096) para raciocínio profundo
    max_context_tokens: int = _env_int("ASSISTANT_NUM_CTX", 8192)
    max_output_tokens: int = _env_int("ASSISTANT_MAX_OUTPUT_TOKENS", 4096)
    temperature: float = 0.7
    max_history_messages: int = 25
    max_message_chars: int = 64000
    max_upload_mb: int = 50
    allowed_document_extensions: list[str] = [
        ".pdf", ".txt", ".md", ".docx", ".epub",
        ".csv", ".json", ".py", ".js", ".html",
        ".css", ".xml", ".yaml", ".yml"
    ]
    authorization_ttl_seconds: int = 120

    # Modo turbo (opt-in): escrita e internet rodam sem pedir aprovação.
    # Exclusões continuam exigindo aprovação mesmo com o turbo ligado.
    # Desligado por padrão: ligue só com ASSISTANT_TURBO_MODE=1.
    turbo_mode: bool = os.environ.get(
        "ASSISTANT_TURBO_MODE", "0"
    ).lower() in ("1", "true", "yes")

    # Acesso a qualquer pasta do computador (opt-in). Por padrão só os
    # diretórios em authorized_directories são acessíveis. Independe do turbo.
    allow_all_directories: bool = os.environ.get(
        "ASSISTANT_ALLOW_ALL_DIRS", "0"
    ).lower() in ("1", "true", "yes")

    # RAG: Busca Híbrida (vetorial + palavras-chave/BM25)
    rag_hybrid_search: bool = os.environ.get(
        "ASSISTANT_HYBRID_RAG", "1"
    ).lower() not in ("0", "false", "no")

    # Memória: limite de memórias ativas injetadas no prompt para economizar contexto
    max_active_memories_prompt: int = _env_int("ASSISTANT_MAX_MEMORIES_PROMPT", 10)

    # Tool calling
    tool_calling_enabled: bool = os.environ.get(
        "ASSISTANT_TOOL_CALLING", "1"
    ).lower() not in ("0", "false", "no")
    max_tool_rounds: int = _env_int("ASSISTANT_MAX_TOOL_ROUNDS", 6)
    max_tool_calls_per_round: int = _env_int("ASSISTANT_MAX_TOOL_CALLS", 4)
    tool_result_max_chars: int = _env_int("ASSISTANT_TOOL_RESULT_CHARS", 8000)

    # OCR for PDFs without an embedded text layer. Uses Tesseract; if it is
    # not installed the app keeps working and reports the limitation.
    ocr_enabled: bool = os.environ.get(
        "ASSISTANT_OCR", "1"
    ).lower() not in ("0", "false", "no")
    ocr_lang: str = os.environ.get("ASSISTANT_OCR_LANG", "")
    ocr_dpi: int = _env_int("ASSISTANT_OCR_DPI", 200)
    ocr_min_chars: int = _env_int("ASSISTANT_OCR_MIN_CHARS", 40)
    tesseract_cmd: str = os.environ.get("TESSERACT_CMD", "")

    # Local origins allowed to call the API from a browser.
    allowed_origins: list[str] = [
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ]

    # ----------------- Voz (TTS + STT) -----------------
    # Síntese de fala (texto -> áudio) via pyttsx3/SAPI5 (offline, Windows).
    tts_enabled: bool = os.environ.get("ASSISTANT_TTS", "1").lower() not in (
        "0", "false", "no"
    )
    # Reconhecimento de fala (áudio -> texto) via SpeechRecognition (offline).
    stt_enabled: bool = os.environ.get("ASSISTANT_STT", "1").lower() not in (
        "0", "false", "no"
    )
    # Falar automaticamente as respostas do assistente (pode ser desativado).
    tts_speak_responses: bool = os.environ.get(
        "ASSISTANT_TTS_SPEAK", "1"
    ).lower() not in ("0", "false", "no")

    # ----------------- llama.cpp (backend padrão agora) -----------------
    # Caminho para o executável llama-server.exe (instalação local já presente).
    llama_cpp_dir: str = os.environ.get(
        "LLAMA_CPP_DIR", r"C:\Users\Usuário\llama.cpp"
    )
    llama_cpp_server_exe: str = os.environ.get(
        "LLAMA_CPP_SERVER_EXE", ""
    )
    # Modelo GGUF já baixado localmente (não há download automático).
    llama_cpp_model_path: str = os.environ.get(
        "LLAMA_CPP_MODEL_PATH",
        str(DEFAULT_LLAMA_CPP_DIR / "models" / "Qwen_Qwen3.5-9B-IQ4_XS.gguf"),
    )
    llama_cpp_host: str = os.environ.get("LLAMA_CPP_HOST", "127.0.0.1")
    llama_cpp_port: int = _env_int("LLAMA_CPP_PORT", 8899)
    llama_cpp_n_ctx: int = _env_int("LLAMA_CPP_N_CTX", 8192)
    llama_cpp_n_gpu_layers: int = _env_int("LLAMA_CPP_N_GPU_LAYERS", 33)
    # Backend padrão: "llama-cpp" usa o servidor local; "ollama" usa o Ollama.
    default_backend: str = os.environ.get(
        "ASSISTANT_DEFAULT_BACKEND", "llama-cpp"
    )
    # ----------------- Claude Code (Claude Agent SDK) -----------------
    # Pasta de trabalho do Claude Code (cwd das sessões).
    claude_code_workspace: str = os.environ.get(
        "ASSISTANT_CLAUDE_WORKSPACE", str(Path.home() / "Documents")
    )
    # Modelo do Claude Code; vazio = padrão do Claude Code.
    claude_code_model: str = os.environ.get("ASSISTANT_CLAUDE_MODEL", "")
    # Se True, inicia o llama-server automaticamente ao subir o app.
    llama_cpp_auto_start: bool = os.environ.get(
        "ASSISTANT_LLAMA_CPP_AUTO_START", "1"
    ).lower() not in ("0", "false", "no")

    # Security Whitelist: directories the assistant is authorized to access.
    # By default: the application workspace and the user's Documents folder.
    authorized_directories: list[str] = _env_dirs(
        "ASSISTANT_AUTHORIZED_DIRS",
        [
            str(DATA_DIR),
            str(Path.home() / "Documents"),
            str(BASE_DIR),
        ],
    )


# Backends accepted by the chat API and the mode selector.
VALID_BACKENDS = ("llama-cpp", "llama-cpp-server", "ollama", "claude-code")

settings = Settings()
