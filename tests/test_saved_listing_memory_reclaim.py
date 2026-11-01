"""Listing requests must release temporary artifact memory between reads."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_listing_returns_temporary_heap_pages_to_the_os():
    if not sys.platform.startswith('linux'):
        # The Linux allocator is the production contract; other platforms
        # still exercise the portable cleanup and result/exception tests.
        return
    script = r'''
import ctypes,json
from pathlib import Path
from services.saved_project_listing import serialized_listing
libc=ctypes.CDLL(None)
libc.malloc_trim(0)
libc.malloc.argtypes=[ctypes.c_size_t]
libc.malloc.restype=ctypes.c_void_p
libc.free.argtypes=[ctypes.c_void_p]
def rss():
    return int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
anchors=[]
@serialized_listing
def listing():
    temporary=[]
    for i in range(1024):
        block=libc.malloc(65536)
        assert block
        ctypes.memset(block,120,65536)
        temporary.append(block)
        anchors.append(libc.malloc(32))
    for block in temporary:
        libc.free(block)
    return {'projects':[{'id':23}], 'has_more':False}
baseline=rss()
for _ in range(3):
    assert listing()=={'projects':[{'id':23}], 'has_more':False}
print(json.dumps({'retained':rss()-baseline}))
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                            capture_output=True, text=True, check=True, timeout=45)
    import json
    report = json.loads(result.stdout.splitlines()[-1])
    assert report['retained'] < 24 * 1024 * 1024, report


def test_listing_releases_cycles_after_success_and_failure():
    import gc
    import weakref
    from services.saved_project_listing import serialized_listing
    refs=[]
    class TemporaryArtifact:
        pass
    @serialized_listing
    def listing(fail=False):
        item=TemporaryArtifact()
        item.cycle=item
        item.buffer=bytearray(1024*1024)
        refs.append(weakref.ref(item))
        if fail:
            raise ValueError('original failure')
        return ['unchanged result']
    enabled=gc.isenabled()
    gc.disable()
    try:
        assert listing()==['unchanged result']
        assert refs[-1]() is None
        try:
            listing(True)
        except ValueError as exc:
            assert str(exc)=='original failure'
        else:
            raise AssertionError('listing swallowed the original failure')
        # The exception traceback belongs to the caller until except exits.
        gc.collect()
        assert refs[-1]() is None
    finally:
        if enabled:
            gc.enable()
