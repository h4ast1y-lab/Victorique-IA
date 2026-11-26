"""Módulo de voz do Assistente Pessoal.

Oferece:
  * TTS (texto -> fala) via pyttsx3 (SAPI5 no Windows, offline).
  * STT (fala -> texto) via SpeechRecognition (microfone ou arquivo de áudio).

Tudo roda localmente. Nenhum áudio é enviado para fora da máquina.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voice")

# ---------------------------------------------------------------------------
# TTS (text-to-speech)
# ---------------------------------------------------------------------------

try:
    import pyttsx3  # type: ignore

    _TTS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on environment
    _TTS_AVAILABLE = False
    _TTS_IMPORT_ERROR = exc


class TTSEngine:
    """Síntese de fala local (offline). Usa pyttsx3/SAPI5 no Windows."""

    def __init__(self):
        self._engine = None
        self._lock = threading.Lock()
        self._available = False
        self._init_error: Optional[str] = None
        self._init_engine()

    def _init_engine(self):
        if not _TTS_AVAILABLE:
            self._init_error = f"pyttsx3 não instalado: {_TTS_IMPORT_ERROR}"
            logger.warning(self._init_error)
            return
        try:
            engine = pyttsx3.init()
            # Ajustes razoáveis para voz em português do Brasil, se disponível.
            voices = engine.getProperty("voices")
            pt_voice = None
            for v in voices or []:
                vid = (v.id or "").lower()
                vname = (v.name or "").lower()
                if "brazil" in vid or "brazil" in vname or "portuguese" in vid or "portuguese" in vname:
                    pt_voice = v.id
                    break
            if pt_voice:
                engine.setProperty("voice", pt_voice)
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 1.0)
            self._engine = engine
            self._available = True
            logger.info("TTS engine inicializado (pyttsx3/SAPI5).")
        except Exception as exc:  # pragma: no cover - depends on environment
            self._init_error = str(exc)
            logger.warning(f"Falha ao inicializar TTS: {exc}")

    @property
    def available(self) -> bool:
        return self._available and self._engine is not None

    def status(self) -> dict:
        return {
            "available": self.available,
            "engine": "pyttsx3",
            "error": self._init_error,
        }

    def speak(self, text: str) -> bool:
        """Fala o texto de forma síncrona. Retorna True se conseguiu."""
        if not self.available:
            logger.warning("TTS não disponível; ignorando speak().")
            return False
        try:
            with self._lock:
                self._engine.say(text)
                self._engine.runAndWait()
            return True
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.error(f"Erro durante TTS: {exc}")
            return False

    def speak_async(self, text: str) -> None:
        """Fala o texto em uma thread separada (não bloqueia)."""

        def _run():
            self.speak(text)

        threading.Thread(target=_run, daemon=True).start()


if (Path(__file__).resolve().parents[2] / ".venv-voice/Scripts/python.exe").is_file():
    from app.voice.provider import ChatterboxEngine
    import atexit
    tts_engine = ChatterboxEngine()
    atexit.register(tts_engine.close)
else:
    tts_engine = TTSEngine()


# ---------------------------------------------------------------------------
# STT (speech-to-text)
# ---------------------------------------------------------------------------

try:
    import speech_recognition as sr  # type: ignore

    _STT_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on environment
    _STT_AVAILABLE = False
    _STT_IMPORT_ERROR = exc

_MIC_LOCK = threading.Lock()


class STTEngine:
    """Reconhecimento de fala local (offline).

    Usa SpeechRecognition. No Windows tenta usar o recognizer do Sphinx
    (offline) quando disponível; caso contrário, reporta a limitação.
    """

    def __init__(self):
        self._recognizer = None
        self._microphone = None
        self._available = False
        self._init_error: Optional[str] = None
        self._init_engine()

    def _init_engine(self):
        if not _STT_AVAILABLE:
            self._init_error = f"SpeechRecognition não instalado: {_STT_IMPORT_ERROR}"
            logger.warning(self._init_error)
            return
        try:
            recognizer = sr.Recognizer()
            try:
                microphone = sr.Microphone()
            except Exception as exc:  # PyAudio ausente, etc.
                microphone = None
                self._init_error = (
                    f"Microfone não disponível (PyAudio ausente): {exc}. "
                    "Use transcrever_arquivo() com um arquivo de áudio."
                )
                logger.warning(self._init_error)
            self._recognizer = recognizer
            self._microphone = microphone
            self._available = recognizer is not None
            logger.info("STT engine inicializado (SpeechRecognition).")
        except Exception as exc:  # pragma: no cover - depends on environment
            self._init_error = str(exc)
            logger.warning(f"Falha ao inicializar STT: {exc}")

    @property
    def available(self) -> bool:
        return self._available

    @property
    def microphone_available(self) -> bool:
        return self._microphone is not None

    def status(self) -> dict:
        return {
            "available": self.available,
            "microphone_available": self.microphone_available,
            "engine": "speech_recognition",
            "error": self._init_error,
        }

    def ouvir(self, timeout: float = 5.0, phrase_time_limit: float = 15.0) -> Optional[str]:
        """Captura áudio do microfone e transcreve. Retorna o texto ou None."""
        if not self.available or self._microphone is None:
            logger.warning("STT/microfone não disponível para ouvir().")
            return None
        # One shared Microphone object: a second listen at the same time (now
        # that listening runs in a worker thread) would fail inside PyAudio.
        if not _MIC_LOCK.acquire(blocking=False):
            logger.info("Microfone já em uso; pedido de ditado ignorado.")
            return None
        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
            return self._transcrever_audio(audio)
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.error(f"Erro ao ouvir microfone: {exc}")
            return None
        finally:
            _MIC_LOCK.release()

    def transcrever_arquivo(self, file_path: str) -> Optional[str]:
        """Transcreve um arquivo de áudio (WAV, MP3, etc.)."""
        if not self.available:
            logger.warning("STT não disponível para transcrever_arquivo().")
            return None
        try:
            with sr.AudioFile(file_path) as source:
                audio = self._recognizer.record(source)
            return self._transcrever_audio(audio)
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.error(f"Erro ao transcrever arquivo {file_path}: {exc}")
            return None

    def _transcrever_audio(self, audio) -> Optional[str]:
        """Tenta reconhecer offline (Sphinx) e, se falhar, reporta."""
        try:
            return self._recognizer.recognize_sphinx(audio, language="pt-BR")
        except Exception:
            pass
        try:
            return self._recognizer.recognize_sphinx(audio, language="en-US")
        except Exception:
            pass
        # Se nenhum recognizer offline estiver disponível, não enviamos para
        # serviços de nuvem (Google, etc.) por padrão — isso quebraria o
        # princípio offline-first. Retornamos None com erro claro.
        logger.warning("Nenhum recognizer offline (Sphinx) disponível.")
        return None


stt_engine = STTEngine()
