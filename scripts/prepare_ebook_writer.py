"""Explicit build-time installation; no inference or paid model call.

Run only on the existing workflow build, never on the small web service.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request


def main():
    import zstandard
    root=Path(__file__).resolve().parents[1]/'.ebook-runtime'
    root.mkdir(exist_ok=True)
    (root/'installed').unlink(missing_ok=True)
    url='https://github.com/ollama/ollama/releases/download/v0.40.13/ollama-linux-amd64.tar.zst'
    expected='c9490e0f520be21271d969e6703f012268b1d39f8b70dd58854e5bfef7a75bb6'
    with tempfile.TemporaryDirectory() as directory:
        archive=Path(directory)/'ollama.zst'
        urllib.request.urlretrieve(url,archive)
        checksum=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
        if checksum!=expected:raise ValueError('Official runtime checksum mismatch')
        with archive.open('rb') as source,zstandard.ZstdDecompressor().stream_reader(source) as stream:
            with tarfile.open(fileobj=stream,mode='r|') as package:
                for entry in package:
                    relative=Path(entry.name)
                    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe runtime path')
                    if any(part.startswith(('cuda','rocm','vulkan')) for part in relative.parts):continue
                    if not (str(relative).startswith('lib/ollama/') or str(relative)=='bin/ollama'):continue
                    target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                    if entry.issym():
                        resolved=(target.parent/entry.linkname).resolve()
                        if not resolved.is_relative_to(root.resolve()):raise ValueError('Unsafe runtime link')
                        target.unlink(missing_ok=True);target.symlink_to(entry.linkname);continue
                    if not entry.isfile():continue
                    with package.extractfile(entry) as content,target.open('wb') as destination:shutil.copyfileobj(content,destination)
                    target.chmod(entry.mode & 0o755)
    env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_MODELS':str(root/'models'),'OLLAMA_NO_CLOUD':'1'}
    process=subprocess.Popen([str(root/'bin/ollama'),'serve'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2).close();break
            except OSError:
                if process.poll() is not None:raise RuntimeError('Runtime exited during installation')
                time.sleep(1)
        else:raise RuntimeError('Runtime installation readiness timeout')
        subprocess.run([str(root/'bin/ollama'),'pull','qwen3:8b'],env=env,check=True,timeout=900)
        (root/'installed').write_text(expected+'\nqwen3:8b\n')
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)


if __name__=='__main__':main()
