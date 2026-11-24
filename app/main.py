import asyncio
import atexit
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings, DOCS_DIR, BASE_DIR, VALID_BACKENDS
from app.memory.database import init_db, get_connection
from app.memory.conversation_store import conversation_store
from app.memory.memory_store import memory_store
from app.memory.project_store import project_store
from app.core.personality import personality_manager
from app.core import preferences
from app.core.avatar_protocol import avatar_manifest
from app.core import avatar_photo
from app.core.sse import sse_event
from app.core.assistant import assistant_engine
from app.core.backup import create_backup, list_backups, backup_path, restore_backup
from app.models.ollama_client import ollama_client
from app.models.llama_cpp_client import llama_cpp_client
from app.models.llama_cpp_server_client import llama_cpp_server
from app.rag.vector_store import vector_store
from app.rag.document_loader import document_loader
from app.security.permissions import security_manager
from app.tools.registry import tool_registry
from app.tools import organizer
from app.life.service import life_service
from app.mascot.bus import mascot_bus
from app.voice import tts_engine, stt_engine

# Initialize database schema on startup
init_db()
preferences.apply_to_settings()


app = FastAPI(title=settings.app_name, version=settings.version)

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def _local_hosts() -> set:
    import os
    hosts = {"127.0.0.1", "localhost", "::1"}
    if os.environ.get("ASSISTANT_TESTING") == "1":
        hosts.add("testserver")
    return hosts


def _local_origins() -> set:
    origins = set(settings.allowed_origins)
    origins.add(f"http://127.0.0.1:{settings.port}")
    origins.add(f"http://localhost:{settings.port}")
    return origins


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """
    Blocks DNS-rebinding (unexpected Host) and cross-site browser requests
    (unexpected Origin) before any endpoint runs. No external CORS is allowed.
    """
    raw_host = request.headers.get("host", "")
    host = raw_host.split(":")[0].strip("[]").lower()
    if host and host not in _local_hosts():
        return JSONResponse({"detail": "Host não permitido."}, status_code=400)

    origin = request.headers.get("origin")
    if origin and origin not in _local_origins():
        return JSONResponse({"detail": "Origem não permitida."}, status_code=403)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = CSP
    if request.url.path.startswith("/ui"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ----------------- Models & Schemas -----------------
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = ""
    message: str = Field(min_length=1)
    model: Optional[str] = None
    backend: Optional[str] = None  # "ollama", "llama-cpp", "llama-cpp-server"
    project_id: Optional[str] = None
    personality_id: Optional[str] = None
    enable_rag: bool = True

class ConversationCreate(BaseModel):
    title: Optional[str] = "Nova Conversa"
    project_id: Optional[str] = None
    personality_id: Optional[str] = None

class ConversationUpdate(BaseModel):
    title: str

class PersonalityCreate(BaseModel):
    id: Optional[str] = None
    name: str
    system_instructions: str
    description: Optional[str] = ""
    tone: Optional[str] = "prestativo"
    formality: Optional[int] = 3
    objectivity: Optional[int] = 4
    detail_level: Optional[int] = 3
    is_default: Optional[bool] = False
    avatar: Optional[str] = ""
    emoji_level: Optional[int] = 2

class MemoryCreate(BaseModel):
    category: str
    content: str
    project_id: Optional[str] = None

class MemoryUpdate(BaseModel):
    content: str
    category: Optional[str] = None
    is_active: Optional[bool] = None

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    instructions: Optional[str] = ""

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None

class ProjectArchive(BaseModel):
    archived: bool = True

class AuthorizeActionRequest(BaseModel):
    action_id: str
    approved: bool

class ToolExecuteRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]
    # Kept for API compatibility. It is NEVER trusted by the backend.
    authorized: Optional[bool] = False

class BackupCreate(BaseModel):
    label: Optional[str] = "manual"

class BackupRestoreRequest(BaseModel):
    name: str
    confirm: bool = False

class SettingsUpdate(BaseModel):
    default_model: Optional[str] = None
    default_backend: Optional[str] = None


class TTSSpeakRequest(BaseModel):
    text: str = Field(min_length=1)
    async_: Optional[bool] = False


class STTListenRequest(BaseModel):
    timeout: Optional[float] = 5.0
    phrase_time_limit: Optional[float] = 15.0


class STTTranscribeRequest(BaseModel):
    file_path: str


class LlamaCppLoadRequest(BaseModel):
    model_path: str
    n_ctx: Optional[int] = None


def _get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def _set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )


def _current_model() -> str:
    return _get_setting("default_model", settings.default_model) or settings.default_model


def _current_backend() -> str:
    """Mode saved from the UI (settings table), else the env/config default."""
    value = (_get_setting("default_backend", settings.default_backend) or "").strip().lower()
    return value if value in VALID_BACKENDS else settings.default_backend


# Auto-start do servidor llama.cpp em segundo plano, só quando o modo salvo é
# local: o modelo pode levar minutos para carregar e a API responde enquanto isso.
if settings.llama_cpp_auto_start and _current_backend() in ("llama-cpp", "llama-cpp-server"):
    llama_cpp_server.start_in_background(wait_seconds=180)
# Encerra o llama-server iniciado por este app ao sair (libera a VRAM).
atexit.register(llama_cpp_server.stop)


def _claude_sdk_installed() -> bool:
    import importlib.util
    return importlib.util.find_spec("claude_agent_sdk") is not None


# ----------------- System & Health -----------------
@app.get("/api/ping")
async def ping():
    """Liveness only: answers at once, without probing models or engines."""
    return {"status": "ok"}


@app.get("/api/health")
async def health_check():
    ollama_ok = await ollama_client.is_alive()
    ollama_version = await ollama_client.get_version() if ollama_ok else None
    models = await ollama_client.list_models() if ollama_ok else []
    names = [m.get("name", "") for m in models]
    active = _current_model()
    backend = _current_backend()
    if backend in ("llama-cpp", "llama-cpp-server"):
        backend_ok = llama_cpp_server.available or llama_cpp_client.available
    elif backend == "claude-code":
        backend_ok = _claude_sdk_installed()
    else:
        backend_ok = ollama_ok
    return {
        "status": "healthy" if backend_ok else "degraded",
        "active_backend": backend,
        "app_name": settings.app_name,
        "ollama_online": ollama_ok,
        "ollama_version": ollama_version,
        "models_count": len(models),
        "default_model": active,
        "default_model_installed": active in names if ollama_ok else None,
        "tool_calling_enabled": settings.tool_calling_enabled,
        "tools_count": len(tool_registry.tools),
        "ocr": document_loader.ocr.status(),
        "tts": tts_engine.status(),
        "stt": stt_engine.status(),
        "llama_cpp": llama_cpp_client.status(),
        "llama_cpp_server": llama_cpp_server.status(),
    }

@app.get("/api/models")
async def list_models():
    models = await ollama_client.list_models()
    return {"models": models, "active_default": _current_model()}

@app.get("/api/settings")
async def get_settings():
    return {
        "default_model": _current_model(),
        "default_backend": _current_backend(),
        "available_backends": list(VALID_BACKENDS),
        "max_context_tokens": settings.max_context_tokens,
        "max_output_tokens": settings.max_output_tokens,
        "authorization_ttl_seconds": settings.authorization_ttl_seconds,
    }

@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    if req.default_model is not None:
        name = req.default_model.strip()
        if not name or len(name) > 120 or not re.fullmatch(r"[A-Za-z0-9._:/-]+", name):
            raise HTTPException(status_code=400, detail="Nome de modelo inválido.")
        _set_setting("default_model", name)
        settings.default_model = name
    if req.default_backend is not None:
        backend = req.default_backend.strip().lower()
        if backend not in VALID_BACKENDS:
            raise HTTPException(status_code=400, detail="Modo inválido.")
        _set_setting("default_backend", backend)
    return {
        "status": "updated",
        "default_model": _current_model(),
        "default_backend": _current_backend(),
    }


@app.get("/api/preferences")
async def get_preferences():
    return preferences.load()


@app.post("/api/preferences")
async def update_preferences(changes: Dict[str, Any]):
    try:
        return preferences.update(changes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/claude-code/status")
async def claude_code_status():
    installed = _claude_sdk_installed()
    cli_path = None
    last_error = None
    if installed:
        import claude_agent_sdk
        bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude.exe"
        cli_path = str(bundled) if bundled.is_file() else None
        try:  # filled by the Claude Code backend once it exists and has run
            from app.claude_code.backend import claude_code_backend
            last_error = claude_code_backend.last_error
        except ImportError:
            last_error = None
    return {
        "sdk_installed": installed,
        "cli_path": cli_path,
        "workspace": settings.claude_code_workspace,
        "model": settings.claude_code_model,
        "last_error": last_error,
    }


# ----------------- Voz (TTS / STT) -----------------
@app.get("/api/tts/status")
async def tts_status():
    return tts_engine.status()


@app.post("/api/tts/speak")
async def tts_speak(req: TTSSpeakRequest):
    if not settings.tts_enabled:
        raise HTTPException(status_code=400, detail="TTS está desativado.")
    if not tts_engine.available:
        raise HTTPException(
            status_code=503,
            detail="TTS não disponível (pyttsx3/SAPI5 não instalado ou falhou ao iniciar).",
        )
    if req.async_:
        tts_engine.speak_async(req.text)
        return {"status": "speaking_async"}
    ok = tts_engine.speak(req.text)
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao sintetizar fala.")
    return {"status": "spoken"}


@app.get("/api/stt/status")
async def stt_status():
    return stt_engine.status()


@app.post("/api/stt/listen")
async def stt_listen(req: STTListenRequest):
    if not settings.stt_enabled:
        raise HTTPException(status_code=400, detail="STT está desativado.")
    if not stt_engine.available:
        raise HTTPException(
            status_code=503,
            detail="STT não disponível (SpeechRecognition não instalado).",
        )
    if not stt_engine.microphone_available:
        raise HTTPException(
            status_code=503,
            detail=(
                "Microfone não disponível (PyAudio ausente). "
                "Use /api/stt/transcribe com um arquivo de áudio."
            ),
        )
    text = stt_engine.ouvir(
        timeout=req.timeout or 5.0,
        phrase_time_limit=req.phrase_time_limit or 15.0,
    )
    if text is None:
        return {"status": "no_speech", "text": ""}
    return {"status": "ok", "text": text}


@app.post("/api/stt/transcribe")
async def stt_transcribe(req: STTTranscribeRequest):
    if not settings.stt_enabled:
        raise HTTPException(status_code=400, detail="STT está desativado.")
    if not stt_engine.available:
        raise HTTPException(
            status_code=503,
            detail="STT não disponível (SpeechRecognition não instalado).",
        )
    text = stt_engine.transcrever_arquivo(req.file_path)
    if text is None:
        return {"status": "no_speech", "text": ""}
    return {"status": "ok", "text": text}


@app.post("/api/stt/upload-audio")
async def stt_upload_audio(file: UploadFile = File(...)):
    """
    Recebe arquivo de áudio gravado diretamente pelo frontend (microfone do navegador/WebView2)
    e executa o reconhecimento de voz localmente.
    """
    if not settings.stt_enabled:
        raise HTTPException(status_code=400, detail="STT está desativado.")
    if not stt_engine.available:
        raise HTTPException(
            status_code=503,
            detail="STT não disponível (SpeechRecognition não instalado).",
        )
    import tempfile
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)

    try:
        text = stt_engine.transcrever_arquivo(str(tmp_path))
        if text is None:
            return {"status": "no_speech", "text": ""}
        return {"status": "ok", "text": text}
    finally:
        tmp_path.unlink(missing_ok=True)


# ----------------- llama.cpp (backend alternativo) -----------------
@app.get("/api/llama-cpp/status")
async def llama_cpp_status():
    return llama_cpp_client.status()


@app.post("/api/llama-cpp/load")
async def llama_cpp_load(req: LlamaCppLoadRequest):
    if not settings.llama_cpp_enabled:
        raise HTTPException(status_code=400, detail="llama.cpp está desativado.")
    n_ctx = req.n_ctx or settings.llama_cpp_n_ctx
    ok = llama_cpp_client.load_model(req.model_path, n_ctx=n_ctx)
    if not ok:
        raise HTTPException(status_code=400, detail=llama_cpp_client._init_error or "Falha ao carregar modelo.")
    return {"status": "loaded", "model_path": req.model_path, "n_ctx": n_ctx}


# ----------------- llama.cpp server (backend padrão) -----------------
class LlamaCppServerStartRequest(BaseModel):
    wait_seconds: Optional[int] = 60


@app.get("/api/llama-cpp-server/status")
async def llama_cpp_server_status():
    # Dispara o auto-start em segundo plano; o status informa "starting".
    if not llama_cpp_server.available and settings.default_backend == "llama-cpp":
        llama_cpp_server.start_in_background(wait_seconds=180)
    return llama_cpp_server.status()


@app.post("/api/llama-cpp-server/start")
async def llama_cpp_server_start(req: LlamaCppServerStartRequest):
    ok = await asyncio.to_thread(llama_cpp_server.start, req.wait_seconds or 60)
    if not ok:
        raise HTTPException(
            status_code=400, detail=llama_cpp_server._init_error or "Falha ao iniciar servidor."
        )
    return {"status": "started", "base_url": llama_cpp_server.base_url}


@app.post("/api/llama-cpp-server/stop")
async def llama_cpp_server_stop():
    llama_cpp_server.stop()
    return {"status": "stopped"}

# ----------------- Chat (Streaming) -----------------
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    if len(req.message) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail="Mensagem longa demais.")

    conv = None
    if req.conversation_id:
        conv = conversation_store.get_conversation(req.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if req.project_id and not project_store.get_project(req.project_id):
        raise HTTPException(status_code=400, detail="Projeto não encontrado.")
    if req.personality_id and not personality_manager.get_personality(req.personality_id):
        raise HTTPException(status_code=400, detail="Personalidade não encontrada.")

    if not conv:
        title = req.message.strip()[:60] or "Nova Conversa"
        conv = conversation_store.create_conversation(
            title=title,
            project_id=req.project_id,
            personality_id=req.personality_id,
        )

    async def event_generator():
        backend = req.backend or _current_backend()
        agen = assistant_engine.chat_stream(
            conversation_id=conv["id"],
            user_message=req.message,
            model=req.model or _current_model(),
            backend=backend,
            project_id=req.project_id,
            personality_id=req.personality_id,
            enable_rag=req.enable_rag,
        )
        try:
            async for chunk in agen:
                if await request.is_disconnected():
                    break
                yield chunk
        except Exception as exc:  # engine offline etc.: tell the UI instead of cutting the stream
            logging.getLogger(__name__).exception("Falha na geração")
            message = f"Não consegui falar com o motor ({backend}): {exc}"
            yield sse_event({"type": "error", "message": message})
            yield sse_event({"type": "done", "conversation_id": conv["id"], "content": ""})
        finally:
            # Closing the async generator closes the Ollama HTTP stream too.
            await agen.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ----------------- Conversations -----------------
@app.get("/api/conversations")
async def get_conversations(project_id: Optional[str] = None):
    return conversation_store.list_conversations(project_id)

@app.get("/api/conversations/search")
async def search_conversations(q: str = "", project_id: Optional[str] = None):
    if not q.strip():
        return []
    return conversation_store.search_conversations(q.strip()[:200], project_id=project_id)

@app.post("/api/conversations")
async def create_conversation(req: ConversationCreate):
    if req.project_id and not project_store.get_project(req.project_id):
        raise HTTPException(status_code=400, detail="Projeto não encontrado.")
    if req.personality_id and not personality_manager.get_personality(req.personality_id):
        raise HTTPException(status_code=400, detail="Personalidade não encontrada.")
    return conversation_store.create_conversation(
        title=(req.title or "Nova Conversa").strip()[:120] or "Nova Conversa",
        project_id=req.project_id,
        personality_id=req.personality_id
    )

@app.get("/api/conversations/{conv_id}/messages")
async def get_conversation_messages(conv_id: str):
    conv = conversation_store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    messages = conversation_store.get_messages(conv_id)
    return {"conversation": conv, "messages": messages}

@app.put("/api/conversations/{conv_id}")
async def rename_conversation(conv_id: str, req: ConversationUpdate):
    title = req.title.strip()[:120]
    if not title:
        raise HTTPException(status_code=400, detail="Título vazio.")
    ok = conversation_store.update_title(conv_id, title)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return {"status": "success", "title": title}

@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    ok = conversation_store.delete_conversation(conv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return {"status": "deleted"}

@app.get("/api/conversations/{conv_id}/export")
async def export_conversation(conv_id: str, format: str = "json"):
    if format not in ("json", "md", "txt"):
        raise HTTPException(status_code=400, detail="Formato inválido. Use json, md ou txt.")
    try:
        content = conversation_store.export_conversation(conv_id, export_format=format)
        return {"content": content, "format": format}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ----------------- Personalities -----------------
@app.get("/api/personalities")
async def get_personalities():
    return personality_manager.list_personalities()

@app.post("/api/personalities")
async def create_personality(req: PersonalityCreate):
    try:
        return personality_manager.save_personality(
            personality_id=req.id,
            name=req.name,
            description=req.description or "",
            system_instructions=req.system_instructions,
            tone=req.tone or "prestativo",
            formality=req.formality or 3,
            objectivity=req.objectivity or 4,
            detail_level=req.detail_level or 3,
            is_default=req.is_default or False,
            avatar=req.avatar or "",
            emoji_level=req.emoji_level or 2,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/personalities/{p_id}/factory")
async def factory_personality(p_id: str):
    profile = personality_manager.factory_profile(p_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Este perfil não tem versão original.")
    return profile

@app.post("/api/personalities/{p_id}/default")
async def set_default_personality(p_id: str):
    if not personality_manager.set_default(p_id):
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return {"status": "updated", "default_id": p_id}

@app.delete("/api/personalities/{p_id}")
async def delete_personality(p_id: str):
    ok = personality_manager.delete_personality(p_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Não foi possível excluir (perfil padrão ou último perfil).")
    return {"status": "deleted"}

# ----------------- Memories -----------------
@app.get("/api/memories")
async def get_memories(
    project_id: Optional[str] = None,
    category: Optional[str] = None,
    include_global: bool = False,
):
    return memory_store.list_memories(
        project_id=project_id,
        category=category,
        only_active=False,
        include_global=include_global,
    )

@app.post("/api/memories")
async def create_memory(req: MemoryCreate):
    try:
        return memory_store.add_memory(
            category=req.category,
            content=req.content,
            project_id=req.project_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/memories/{mem_id}")
async def update_memory(mem_id: str, req: MemoryUpdate):
    try:
        ok = memory_store.update_memory(
            mem_id, req.content, req.category, is_active=req.is_active
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Memória não encontrada")
    return {"status": "updated"}

@app.delete("/api/memories/{mem_id}")
async def delete_memory(mem_id: str):
    ok = memory_store.delete_memory(mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memória não encontrada")
    return {"status": "deleted"}

# ----------------- Projects -----------------
@app.get("/api/projects")
async def get_projects():
    return project_store.list_projects()

@app.post("/api/projects")
async def create_project(req: ProjectCreate):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Nome do caso vazio.")
    return project_store.create_project(
        name=req.name[:120],
        description=req.description or "",
        instructions=req.instructions or ""
    )

@app.put("/api/projects/{proj_id}")
async def update_project(proj_id: str, req: ProjectUpdate):
    ok = project_store.update_project(
        project_id=proj_id,
        name=req.name,
        description=req.description,
        instructions=req.instructions
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return {"status": "updated"}

@app.post("/api/projects/{proj_id}/archive")
async def archive_project(proj_id: str, req: ProjectArchive):
    if not project_store.set_archived(proj_id, req.archived):
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return {"status": "archived" if req.archived else "reopened"}

@app.delete("/api/projects/{proj_id}")
async def delete_project(proj_id: str):
    ok = project_store.delete_project(proj_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return {"status": "deleted"}

# ----------------- Documents (RAG) -----------------
@app.get("/api/documents")
async def get_documents(project_id: Optional[str] = None):
    return vector_store.list_documents(project_id)

@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form("Geral"),
    project_id: Optional[str] = Form(None)
):
    original = Path(file.filename or "").name
    ext = Path(original).suffix.lower()
    if not original:
        raise HTTPException(status_code=400, detail="Nome de arquivo ausente.")
    if ext not in settings.allowed_document_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado. Use: {', '.join(settings.allowed_document_extensions)}."
        )
    if project_id and project_id != "null" and not project_store.get_project(project_id):
        raise HTTPException(status_code=400, detail="Projeto não encontrado.")

    # Unique safe name: never overwrite an existing document.
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(original).stem)[:80] or "documento"
    save_path = DOCS_DIR / f"{stem}-{uuid.uuid4().hex[:8]}{ext}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0

    try:
        with open(save_path, "wb") as buffer:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Arquivo maior que o limite de {settings.max_upload_mb} MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        save_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Falha ao salvar arquivo: {e}")

    try:
        indexed = await vector_store.index_document(
            file_path=str(save_path),
            collection=(collection or "Geral")[:60],
            project_id=project_id if project_id and project_id != "null" else None
        )
        indexed["ocr"] = dict(document_loader.last_ocr or {})
        return indexed
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Erro ao processar documento: {str(e)}")

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    ok = vector_store.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {"status": "deleted"}

# ----------------- Security & Tools -----------------
@app.get("/api/security/pending")
async def get_pending_authorizations():
    return security_manager.list_pending_actions()

@app.post("/api/security/authorize")
async def authorize_action(req: AuthorizeActionRequest):
    status, action = security_manager.resolve_action_detailed(req.action_id, req.approved)
    if status == "approved" and action and action.get("kind") == "claude_code":
        # Claude Code runs the tool itself; resolving released its callback.
        return {"status": "approved"}
    if status == "approved" and action:
        result = await tool_registry.execute_approved_action(action)

        # If the action came from a conversation, persist a compact result so
        # the next model turn can see what happened without inventing details.
        conversation_id = (action.get("context") or {}).get("conversation_id")
        if conversation_id and conversation_store.get_conversation(conversation_id):
            tool_name = action.get("action_type", "ferramenta")
            summary = json.dumps(result, ensure_ascii=False, default=str)
            if len(summary) > settings.tool_result_max_chars:
                summary = summary[: settings.tool_result_max_chars] + "...[truncado]"
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=(
                    f"_[Ferramenta `{tool_name}` aprovada e executada pelo usuário]_\n"
                    f"Resultado: {summary}"
                ),
            )

        return {
            "status": "executed",
            "result": result,
            "conversation_id": conversation_id,
        }

    if status == "rejected":
        return {"status": "rejected"}
    if status in ("not_found", "expired"):
        raise HTTPException(status_code=404, detail=f"Autorização {status}. Nada foi executado.")
    if status == "tampered":
        raise HTTPException(status_code=409, detail="Parâmetros divergentes. Ação bloqueada.")
    raise HTTPException(status_code=400, detail="Não foi possível resolver a autorização.")

# ----------------- Avatar (expressions and gestures of the figure) -----------------
@app.get("/api/avatar/manifest")
async def get_avatar_manifest():
    return avatar_manifest()


# ----------------- Avatar photo (default or chosen by the user) -----------------
@app.get("/api/avatar/photo")
async def get_avatar_photo():
    path = avatar_photo.current_path()
    media = "image/png" if path.suffix == ".png" else "image/webp"
    return FileResponse(str(path), media_type=media, headers={"Cache-Control": "no-cache"})

@app.get("/api/avatar/photo/info")
async def get_avatar_photo_info():
    return avatar_photo.info()

@app.post("/api/avatar/photo")
async def upload_avatar_photo(file: UploadFile = File(...)):
    data = await file.read(avatar_photo.MAX_BYTES + 1)
    try:
        return avatar_photo.save_custom(data)
    except avatar_photo.AvatarError as e:
        raise HTTPException(status_code=e.status, detail=str(e))

@app.delete("/api/avatar/photo")
async def reset_avatar_photo():
    return avatar_photo.restore_default()

# ----------------- Vida própria (spontaneous lines) -----------------
class LifeTick(BaseModel):
    app_idle_seconds: float = Field(0, ge=0, le=10_000_000)
    typing: bool = False
    generating: bool = False
    visible: bool = True
    settings_open: bool = False
    backend: Optional[str] = Field(None, max_length=40)
    personality_id: Optional[str] = Field(None, max_length=80)


class LifeSilence(BaseModel):
    minutes: int = Field(120, ge=1, le=24 * 60)


class LifeTest(LifeTick):
    category: str = Field("tedio", max_length=20)


def _life_ui(req: LifeTick) -> Dict[str, Any]:
    ui = req.model_dump()
    # With Victorique on the desktop her balloon is visible even when the
    # chat window is hidden or minimized.
    if mascot_bus.visible:
        ui["visible"] = True
    return ui


@app.post("/api/life/tick")
async def life_tick(req: LifeTick):
    result = await life_service.tick(_life_ui(req))
    return {**result, "mascot": mascot_bus.active}


@app.get("/api/life/status")
async def life_status():
    return life_service.status()


@app.post("/api/life/silence")
async def life_silence(req: LifeSilence):
    return {"silenced_until": life_service.silence(req.minutes)}


@app.post("/api/life/resume")
async def life_resume():
    life_service.resume()
    return life_service.status()


@app.post("/api/life/test")
async def life_test(req: LifeTest):
    try:
        result = await life_service.test(req.category, _life_ui(req))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**result, "mascot": mascot_bus.active}


# ----------------- Victorique on the desktop (app/mascot) -----------------
class MascotSignal(BaseModel):
    state: Optional[str] = Field(None, max_length=20)
    expression: Optional[str] = Field(None, max_length=32)
    gesture: Optional[str] = Field(None, max_length=32)


class MascotCase(BaseModel):
    titulo: str = Field("", max_length=160)
    pergunta: str = Field("", max_length=600)


class MascotSay(BaseModel):
    category: str = Field(..., max_length=20)
    text: str = Field(..., min_length=1, max_length=2000)
    case: Optional[MascotCase] = None
    test: bool = False


class MascotReply(BaseModel):
    text: str = Field(..., max_length=50_000)


class MascotCommand(BaseModel):
    action: Literal["home", "hide"]


@app.get("/api/mascot/status")
async def mascot_status():
    return mascot_bus.status()


@app.post("/api/mascot/signal")
async def mascot_signal(req: MascotSignal):
    """Operational state and model-chosen expression/gesture from the chat page."""
    from app.core.avatar_protocol import EXPRESSIONS, GESTURES, STATES
    state = req.state if req.state in {s for s, _ in STATES} else None
    expression = req.expression if req.expression in EXPRESSIONS else None
    gesture = req.gesture if req.gesture in GESTURES else None
    return {"delivered": mascot_bus.signal(state, expression, gesture)}


@app.post("/api/mascot/say")
async def mascot_say(req: MascotSay):
    return {"shown": mascot_bus.say(req.model_dump(exclude_none=True))}


@app.post("/api/mascot/reply")
async def mascot_reply(req: MascotReply):
    return {"shown": mascot_bus.reply(req.text)}


@app.post("/api/mascot/command")
async def mascot_command(req: MascotCommand):
    return {"delivered": mascot_bus.command(req.action)}

# ----------------- Organizer (history of moves, undo) -----------------
@app.get("/api/operations")
async def get_operations(limit: int = 50):
    return organizer.list_batches(limit=min(max(limit, 1), 300))

@app.post("/api/operations/{batch_id}/undo")
async def undo_operation(batch_id: str):
    # Only the user reaches this, from the Organizer panel; the model has no undo tool.
    try:
        return await asyncio.to_thread(organizer.undo, batch_id)
    except (ValueError, FileExistsError, FileNotFoundError, PermissionError) as e:
        raise HTTPException(status_code=409, detail=f"Não foi possível desfazer: {e}")

@app.post("/api/tools/execute")
async def execute_tool(req: ToolExecuteRequest):
    # Never pass client-supplied "authorized" to the registry.
    return await tool_registry.execute_tool(
        name=req.tool_name,
        params=req.parameters,
    )

@app.get("/api/tools/list")
async def list_tools():
    return [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category.value,
            "risk_description": t.risk_description,
            "parameters": t.parameters,
        }
        for t in tool_registry.tools.values()
    ]

# ----------------- Backup / Restore -----------------
@app.post("/api/backup")
async def make_backup(req: Optional[BackupCreate] = None):
    try:
        return create_backup(label=(req.label if req else "manual") or "manual")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao criar backup: {e}")

@app.get("/api/backups")
async def get_backups():
    return list_backups()

@app.get("/api/backups/{name}")
async def download_backup(name: str):
    try:
        p = backup_path(name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(str(p), filename=p.name, media_type="application/octet-stream")

@app.post("/api/backup/restore")
async def restore(req: BackupRestoreRequest):
    try:
        result = restore_backup(req.name, confirm=req.confirm)
        # Pending actions from the previous database state must not survive.
        security_manager.pending_actions.clear()
        return result
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

# ----------------- Mount Static UI -----------------
UI_DIR = BASE_DIR / "app" / "ui"
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

@app.get("/")
async def root():
    return FileResponse(str(UI_DIR / "index.html"))

@app.get("/favicon.ico")
async def favicon():
    return await get_avatar_photo()
