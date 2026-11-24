import atexit
import json
import logging
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib import request, error
import winsound

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/voice"
PYTHON = ROOT / ".venv-voice/Scripts/python.exe"


class ChatterboxEngine:
    def __init__(self):
        self.process = None
        self.guard = threading.Lock()
        self.secret = secrets.token_hex(32)
        self.queue = ThreadPoolExecutor(1)

    @property
    def available(self):
        return PYTHON.is_file() and (DATA/"models/t3_mtl23ls_v2.safetensors").is_file() and (DATA/"references/normal.wav").is_file()

    def status(self):
        return {"available":self.available, "engine":"Chatterbox Multilingual", "error":None if self.available else "Modelo ou referência ausente."}

    def call(self, route, payload=None, timeout=300):
        req = request.Request("http://127.0.0.1:8100/"+route,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"X-Voice-Key":self.secret,"Content-Type":"application/json"})
        with request.urlopen(req,timeout=timeout) as res:
            return res.read()

    def audio(self, text, language="pt", emotion="normal"):
        with self.guard:
            if self.process is None or self.process.poll() is not None:
                with (DATA/"service.log").open("ab") as log:
                    self.process = subprocess.Popen([str(PYTHON),str(ROOT/"app/voice/service.py")],
                        cwd=ROOT, env=dict(os.environ, VICTORIQUE_VOICE_TOKEN=self.secret, PYTHONUTF8="1", VICTORIQUE_PARENT_PID=str(os.getpid())),
                        stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                for _ in range(100):
                    if self.process.poll() is not None:
                        raise RuntimeError("O serviço de voz encerrou. Consulte data/voice/service.log.")
                    try:
                        self.call("ready",timeout=.4)
                        break
                    except OSError:
                        time.sleep(.15)
                else:
                    self.process.terminate()
                    raise RuntimeError("O serviço de voz não iniciou na porta 8100.")
        return self.call("audio",dict(text=text,language=language,emotion=emotion))

    def speak(self,text):
        try:
            for sentence in re.split(r"(?<=[.!?。！？])\s+",text.strip()):
                for start in range(0,len(sentence),500):
                    winsound.PlaySound(self.audio(sentence[start:start+500]),winsound.SND_MEMORY)
            return True
        except Exception:
            logging.getLogger("voice").exception("Falha na leitura Chatterbox")
            return False

    def speak_async(self,text):
        self.queue.submit(self.speak,text)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

