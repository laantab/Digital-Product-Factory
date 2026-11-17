# Hosted saved-manuscript recovery connection

This configuration connects the new API to an independent polling worker.
It is not an activation of the existing Render build_ebook Workflow task.
The existing web service and builder have not been changed on Render.

Both processes require the same PostgreSQL DATABASE_URL, R2 bucket/credentials,
and absolute FACTORY_V2_WORK_DIR (for example /tmp/factory-ebook-v2).
Paths must be identical across workers because persisted unit payloads contain
that root. The web process does not render or write book files.

Install both requirement files in the worker environment:

    pip install -r requirements.txt -r requirements-ebook-v2.txt

Initialize the separate recovery tables once:

    python -m services.ebook_v2.hosted_runtime init

Start the independent worker:

    python -m services.ebook_v2.hosted_runtime worker

Enable FACTORY_V2_HOSTED_RECOVERY=1 on the web process after the worker is
running. A missing worker heartbeat refuses new recovery requests. Leaving the
flag unset preserves the existing web behavior. Do not run the worker inside a
web request or as an unmonitored thread inside Gunicorn.

The worker accepts supplied manuscripts only; Ollama/topic jobs are ignored.
Intermediate files are verified in R2 before unit completion and restored after
local disk loss. Final shared receipts are committed only after both downloads
pass readback. Failed upload remains unfinished, not falsely complete.

Current boundary: the connection is exercised with a disposable SQLite state
store and the real local implementation of the shared storage contract. It has
not yet been activated on Render or verified against live R2. The existing
Render workflow still needs a deliberate deployment choice: configure an
independent worker, or implement an on-demand dispatch adapter for that workflow.
No new paid service was created. The customer review/approval UI and fresh-topic
model execution are separate remaining work.
