"""Execute the shipped poller against delayed replies; no provider calls."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WorkspacePollLifecycleTests(unittest.TestCase):
    def run_js(self, scenario):
        src = (ROOT / 'static/js/app.js').read_text(encoding='utf-8')
        poll = src[src.index('async function _wsPollUntilStepLands('):src.index('//: v1.8.1. The estimate-then-confirm')]
        action = src[src.index('async function postEbookWorkspaceAction('):src.index('async function estimateCorrectionInWorkspace(')]
        script = """
const assert = require('node:assert/strict');
let _wsPollRun = 1;
const WS_POLL_MS = 0;
const WS_POLL_TIMEOUT_MS = 100;
const messages = [], renders = [];
const toast = (msg, type) => messages.push({msg, type});
const renderEbookWorkspace = ws => renders.push(ws);
""" + poll + action + '\nPromise.race([(async () => {\n' + scenario + '\n})(), new Promise((_, reject) => setTimeout(() => reject(Error("Poll did not finish")), 1000))]).then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });'
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_approving_research_retires_its_pending_status_reply(self):
        self.run_js("""
let resolveStatus;
api = async url => {
  if (url.endsWith('/status')) return await new Promise(r => {resolveStatus = r;});
  if (url === '/approve') return {workspace: {current_stage: 'title'}};
  throw Error('Unexpected request ' + url);
};
const pending = _wsPollUntilStepLands(12, 1, 'Research finished');
await new Promise(r => setTimeout(r, 5));
await postEbookWorkspaceAction('/approve', {stage:'research'}, 'Research approved. Next: Generate Title Options.');
resolveStatus({message:'Researching your topic'});
await pending;
assert.equal(renders.at(-1).current_stage, 'title');
assert.equal(messages.at(-1).msg, 'Research approved. Next: Generate Title Options.');
assert(!messages.some(m => m.msg === 'Researching your topic'));
""")

    def test_cancelled_workspace_refresh_cannot_overwrite_the_new_step(self):
        self.run_js("""
let resolveWorkspace;
api = async url => {
  if (url.endsWith('/status')) return {held_after:'research', message:'Research ready'};
  return await new Promise(r => {resolveWorkspace = r;});
};
const pending = _wsPollUntilStepLands(12, 1, 'Research finished');
await new Promise(r => setTimeout(r, 5));
_wsPollRun += 1;
resolveWorkspace({workspace:{current_stage:'research'}});
await pending;
assert.equal(renders.length, 0);
assert(!messages.some(m => m.msg === 'Research finished'));
""")

    def test_status_failures_end_with_an_honest_timeout_message(self):
        self.run_js("""
api = async () => {throw Error('Network unavailable');};
await _wsPollUntilStepLands(12, 1, 'Research finished');
assert.equal(messages.at(-1).type, 'error');
assert(messages.at(-1).msg.includes('Continue'));
assert(!messages.some(m => m.msg === 'Research finished'));
""")

    def test_completed_step_renders_and_finishes_normally(self):
        self.run_js("""
api = async url => url.endsWith('/status') ? {held_after:'research', message:'Ready'} : {workspace:{current_stage:'title'}};
await _wsPollUntilStepLands(12, 1, 'Research finished');
assert.equal(renders.at(-1).current_stage, 'title');
assert.equal(messages.at(-1).msg, 'Research finished');
""")

    def test_failed_step_does_not_report_success(self):
        self.run_js("""
api = async url => url.endsWith('/status') ? {failed:true, message:'Researching your topic'} : {workspace:{current_stage:'research'}};
await _wsPollUntilStepLands(12, 1, 'Research finished');
assert.equal(messages.at(-1).type, 'error');
assert(!messages.some(m => m.msg === 'Research finished'));
""")
