"""Run an explicitly preinstalled free model only inside the approved task."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import time


@contextmanager
def running():
    from .local_text import configuration,ready
    base,model=configuration()
    root=Path(__file__).resolve().parents[2]/'.ebook-runtime'
    if base!='http://127.0.0.1:11434' or model!='qwen3:8b':
        raise ValueError('Pilot requires the accepted local-only model and loopback address')
    if not (root/'bin/ollama').is_file() or not (root/'installed').is_file():
        raise ValueError('Verified free writer is not installed; no model was started')
    env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_MODELS':str(root/'models'),
         'OLLAMA_NO_CLOUD':'1','OLLAMA_NUM_PARALLEL':'1','OLLAMA_CONTEXT_LENGTH':'8192'}
    process=subprocess.Popen([str(root/'bin/ollama'),'serve'],env=env,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+90
        while not ready():
            if process.poll() is not None or time.monotonic()>=deadline:
                raise ValueError('Local writer did not become ready; paid-provider fallback is forbidden')
            time.sleep(1)
        yield
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
