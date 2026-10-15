"""Real saved records: compact lists, unchanged originals, bounded native memory."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def isolated_env(tmp_path):
    out = os.environ.copy()
    out.update(FACTORY_TEST_MODE='1', FACTORY_EXECUTION_MODE='inline',
               FACTORY_DB_PATH=str(tmp_path/'projects.db'), FACTORY_EXPORTS_DIR=str(tmp_path/'exports'),
               FLASK_EXPORTS_DIR=str(tmp_path/'exports'), FACTORY_INVITE_CODE='', SECRET_KEY='local-only',
               OPENAI_API_KEY='', AI_INTEGRATIONS_OPENAI_API_KEY='', TAVILY_API_KEY='', PEXELS_API_KEY='')
    return out


def test_compact_list_preserves_original_and_detail_reads(tmp_path):
    script = r'''
import hashlib,json
from tests._isolated_saved_server import seed,app,database
pid=seed()[0]
before=database._encode_project_data(database.get_project(pid)['data'])
client=app.test_client()
response=client.get('/projects?limit=10')
assert response.status_code==200
row=next(p for p in response.get_json() if p['id']==pid)
assert row['_list_summary'] is True
assert row['data']['pdf_bytes']=='' and row['data']['preview_html']==''
assert len(response.data)<20000
full=client.get(f'/projects/{pid}').get_json()
assert full['data']['preview_html'].startswith('<h1>Recovered saved preview</h1>')
assert len(full['data']['preview_html'])>2000000
assert full['data']['pdf_bytes']==database.get_project(pid)['data']['pdf_bytes']
assert database._encode_project_data(database.get_project(pid)['data'])==before
print('original preserved')
'''
    output = subprocess.check_output([sys.executable, '-c', script], cwd=ROOT, env=isolated_env(tmp_path), text=True, timeout=60)
    assert 'original preserved' in output


def test_parallel_large_saved_lists_fit_the_website_memory_budget(tmp_path):
    script = r'''
import json,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tests._isolated_saved_server import seed,app,database
seed(count=12,size=12000000)
def read(_):
    response=app.test_client().get('/projects?limit=10')
    assert response.status_code==200
    assert len(response.get_json())==10
    assert response.headers['X-Saved-Has-More']=='1'
    assert len(response.data)<100000
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(read,range(3)))
if sys.platform.startswith('linux'):
    rows=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    peak=int(rows['VmHWM'].split()[0])
elif sys.platform=='win32':
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    read=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    read.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    assert read(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb)
    peak=counters.PeakWorkingSetSize//1024
else:
    import resource
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024
print(json.dumps({'peak_kib':peak}))
'''
    output = subprocess.check_output([sys.executable, '-c', script], cwd=ROOT, env=isolated_env(tmp_path), text=True, timeout=120)
    result = json.loads(output.splitlines()[-1])
    assert result['peak_kib'] < 320*1024, result


def test_browser_retries_failed_list_and_opens_original_full_record(tmp_path):
    from playwright.sync_api import sync_playwright
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    env=isolated_env(tmp_path)
    env['SAVED_BROWSER_PORT']=str(port)
    with (tmp_path/'server.log').open('w') as log:
        proc=subprocess.Popen([sys.executable,str(ROOT/'tests/_isolated_saved_server.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',port))==0:break
            assert proc.poll() is None,(tmp_path/'server.log').read_text()
            time.sleep(.2)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            from types import SimpleNamespace
            from tests.test_ebook_real_browser_customer_path import EbookRealBrowserCustomerPathTests
            fixture=SimpleNamespace(browser=browser,ASSETS=EbookRealBrowserCustomerPathTests.ASSETS)
            context=EbookRealBrowserCustomerPathTests._new_context(fixture)
            page=context.new_page()
            page.goto(f'http://127.0.0.1:{port}')
            page.route('**/projects?limit=10*',lambda route:route.fulfill(status=502,json={'error':'temporary failure'}),times=1)
            list_requests=[]
            page.on('request',lambda r:list_requests.append(r.url) if '/projects?limit=10' in r.url else None)
            page.locator('#nav [data-go="saved"]').click()
            page.locator('[data-retry-saved]').wait_for()
            assert 'No saved projects yet' not in page.locator('#savedList').inner_text()
            assert len(list_requests)==1
            page.locator('[data-retry-saved]').click()
            page.locator('#savedList').get_by_text('Saved Ocean 0',exact=True).wait_for()
            with page.expect_response(lambda response: '/projects/' in response.url) as opened:
                page.locator('#savedList [data-open]').click()
            full=opened.value.json()
            assert full['data']['preview_html'].startswith('<h1>Recovered saved preview</h1>')
            assert len(full['data']['preview_html'])>2000000
            assert full['data']['pdf_bytes']
            page.locator('#factoryOutput').get_by_role('heading',name='Saved Ocean 0',exact=True).wait_for()
            assert page.locator('#factoryForm [name="pages"]').input_value()=='2'
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
