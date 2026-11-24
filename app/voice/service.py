"""Motor local. O processo de voz acompanha a duração da sessão."""
import asyncio
import hmac
import io
import os
from pathlib import Path
import sys
import threading

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/voice"
os.environ["PKUSEG_HOME"] = str(DATA / "models/pkuseg")
os.environ.setdefault("NUMBA_CACHE_DIR", str(DATA / "cache/numba"))
os.environ.setdefault("HF_HOME", str(DATA / "cache/hf"))
os.environ.setdefault("XDG_CACHE_HOME", str(DATA / "cache"))
os.environ.setdefault("MPLCONFIGDIR", str(DATA / "cache/mpl"))

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Literal
import uvicorn

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
token = os.environ["VICTORIQUE_VOICE_TOKEN"]
model = None
lock = threading.Lock()


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    language: Literal["pt", "ja"] = "pt"
    emotion: str = "normal"


def authorize(key):
    if not hmac.compare_digest(token, key):
        raise HTTPException(403)


@app.get("/ready")
def ready(x_voice_key: str = Header("")):
    authorize(x_voice_key)
    return True


@app.post("/audio")
def synthesize(req: Speech, x_voice_key: str = Header("")):
    global model
    authorize(x_voice_key)
    import soundfile as sf
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    refs = {p.stem:p for p in (DATA / "references").glob("*.wav")}
    ref = refs.get(req.emotion) or refs["normal"]
    with lock, torch.inference_mode():
        device = "cuda" if torch.cuda.is_available() else "cpu"
        torch.set_num_threads(min(6, os.cpu_count() or 1))
        for attempt in range(2):
            try:
                if model is None:
                    model = ChatterboxMultilingualTTS.from_local(DATA / "models", device=device)
                audio = model.generate(req.text, language_id=req.language, audio_prompt_path=str(ref))
                break
            except torch.cuda.OutOfMemoryError:
                if attempt or device == "cpu":
                    raise
                model = None
                device = "cpu"
        out = io.BytesIO()
        sf.write(out, audio.detach().cpu().numpy().reshape(-1), model.sr, format="WAV", subtype="PCM_16")
        return Response(out.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    def watch_parent():
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        parent = kernel.OpenProcess(0x00100000, False, int(os.environ["VICTORIQUE_PARENT_PID"]))
        if parent:
            kernel.WaitForSingleObject(wintypes.HANDLE(parent), 0xFFFFFFFF)
        os._exit(0)
    threading.Thread(target=watch_parent, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8100, access_log=False)

