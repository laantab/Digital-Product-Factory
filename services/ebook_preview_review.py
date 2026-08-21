"""Serve-time Full Preview review chrome. Never persisted into stored book HTML."""
from __future__ import annotations

import html
import json
import re
from urllib.parse import urlencode

REVIEW_BAR_TITLE = "Review Your Ebook"
REVIEW_BAR_HELP = "Check the pages below, then approve or request changes."
APPROVE_CONFIRM_PROMPT = (
    "Approve this exact preview and continue to Preflight? "
    "Approval will use the cover, manuscript, visuals, and design shown here."
)
STALE_PREVIEW_MESSAGE = "This preview has changed. Open the newest preview before approving."
APPROVE_SUCCESS_NOTICE = "Preview approved. Next: Run Preflight."
REQUEST_CHANGES_NOTICE = "Preview was not approved. Choose what needs correction."
CHANGE_CATEGORIES = (
    "Cover",
    "Interior design",
    "Text/content",
    "Tables or visuals",
    "Other",
)
CHANGE_CATEGORY_STAGES = {
    "Cover": "cover",
    "Interior design": "design",
    "Text/content": "manuscript",
    "Tables or visuals": "visuals",
    "Other": "preview",
}

_BODY_OPEN_RE = re.compile(r"(<body\b[^>]*>)", re.I)
_BODY_CLOSE_RE = re.compile(r"</body>", re.I)
_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.I)
_HEAD_CLOSE_RE = re.compile(r"</head>", re.I)
_HTML_OPEN_RE = re.compile(r"(<html\b)([^>]*)>", re.I)
_NEXTPAGE_RE = re.compile(r"<pdf:nextpage\s*/>", re.I)
_VIEWPORT_META = (
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>'
)
VIEWER_BREAKPOINTS = (320, 768, 1366, 1920)
_BOOK_SHELL_OPEN = (
    '<div class="ebook-preview-stage">'
    '<div class="ebook-preview-frame">'
    '<div class="ebook-preview-book">'
)
_BOOK_SHELL_CLOSE = "</div></div></div>"


def workspace_return_url(project_id: int, *, stage: str = "preview", **query: str) -> str:
    params = {
        "view": "ebook-workspace",
        "project_id": str(int(project_id)),
        "stage": str(stage or "preview"),
    }
    for key, value in query.items():
        if value:
            params[str(key)] = str(value)
    return "/?" + urlencode(params)


def wrap_preview_review_document(
    book_html: str,
    *,
    title: str,
    project_id: int,
    digest: str,
    can_approve: bool,
    already_approved: bool = False,
) -> str:
    """Attach sticky review controls around stored book HTML for the viewer only."""
    raw = str(book_html or "")
    if not raw.strip():
        return raw
    if "ebook-preview-review-bar" in raw:
        return raw
    title_text = str(title or "Ebook").strip() or "Ebook"
    digest_text = str(digest or "").strip()
    pid = int(project_id)
    back_url = workspace_return_url(pid, stage="preview")
    changes_url = workspace_return_url(pid, stage="preview", review="changes")
    preflight_url = workspace_return_url(pid, stage="preflight", notice="preview-approved")
    payload = {
        "projectId": pid,
        "digest": digest_text,
        "canApprove": bool(can_approve) and not already_approved,
        "alreadyApproved": bool(already_approved),
        "approveUrl": f"/ebook-workspace/{pid}/approve",
        "workspaceUrl": f"/ebook-workspace/{pid}",
        "backUrl": back_url,
        "changesUrl": changes_url,
        "preflightUrl": preflight_url,
        "staleMessage": STALE_PREVIEW_MESSAGE,
        "successNotice": APPROVE_SUCCESS_NOTICE,
    }
    css = _REVIEW_CSS
    bar = _review_bar_html(title_text, can_approve=payload["canApprove"], already_approved=already_approved)
    footer = _review_footer_html(can_approve=payload["canApprove"], already_approved=already_approved)
    dialog = _review_dialog_html()
    script = (
        "<script type=\"application/json\" id=\"ebook-preview-review-config\">"
        + json.dumps(payload, separators=(",", ":"))
        + "</script>\n<script>"
        + _REVIEW_JS
        + "</script>"
    )
    out = _with_html_viewer_class(raw)
    head_extra = _VIEWPORT_META + f"<style>{css}</style>"
    # Inject after book styles so viewer chrome wins without mutating stored HTML.
    if _HEAD_CLOSE_RE.search(out):
        out = _HEAD_CLOSE_RE.sub(head_extra + "</head>", out, count=1)
    elif _HEAD_OPEN_RE.search(out):
        out = _HEAD_OPEN_RE.sub(lambda m: m.group(0) + head_extra, out, count=1)
    else:
        out = head_extra + out
    if _BODY_OPEN_RE.search(out):
        out = _BODY_OPEN_RE.sub(lambda m: m.group(0) + bar + _BOOK_SHELL_OPEN, out, count=1)
    else:
        out = bar + _BOOK_SHELL_OPEN + out
    if _BODY_CLOSE_RE.search(out):
        out = _BODY_CLOSE_RE.sub(_BOOK_SHELL_CLOSE + footer + dialog + script + "</body>", out, count=1)
    else:
        out = out + _BOOK_SHELL_CLOSE + footer + dialog + script
    # HTML5 does not treat <pdf:nextpage /> as self-closing; unwrap it in the viewer only.
    out = _NEXTPAGE_RE.sub('<hr class="ebook-preview-page-break"/>', out)
    return out


def _with_html_viewer_class(html_doc: str) -> str:
    match = _HTML_OPEN_RE.search(html_doc)
    if not match:
        return html_doc
    attrs = match.group(2) or ""
    if "ebook-preview-viewer" in attrs:
        return html_doc
    if re.search(r"\bclass\s*=", attrs, re.I):
        new_attrs = re.sub(
            r'\bclass\s*=\s*(["\'])',
            r'class=\1ebook-preview-viewer ',
            attrs,
            count=1,
            flags=re.I,
        )
    else:
        new_attrs = attrs + ' class="ebook-preview-viewer"'
    return html_doc[: match.start()] + match.group(1) + new_attrs + ">" + html_doc[match.end() :]


def _action_buttons_html(*, can_approve: bool, already_approved: bool, location: str) -> str:
    approve_disabled = "" if can_approve and not already_approved else " disabled"
    approve_label = "Preview already approved" if already_approved else "Approve Preview"
    aria_disabled = " aria-disabled=\"true\"" if approve_disabled else ""
    return (
        f'<a class="ebook-review-btn ebook-review-btn-back" data-ebook-review-back '
        f'href="#" aria-label="Back to Project">Back to Project</a>'
        f'<a class="ebook-review-btn ebook-review-btn-changes" data-ebook-review-changes '
        f'href="#" aria-label="Request Changes">Request Changes</a>'
        f'<button type="button" class="ebook-review-btn ebook-review-btn-approve" '
        f'data-ebook-review-approve data-review-location="{html.escape(location, quote=True)}" '
        f'aria-label="{html.escape(approve_label, quote=True)}"'
        f"{approve_disabled}{aria_disabled}>{html.escape(approve_label)}</button>"
    )


def _review_bar_html(title: str, *, can_approve: bool, already_approved: bool) -> str:
    buttons = _action_buttons_html(
        can_approve=can_approve, already_approved=already_approved, location="top"
    )
    return (
        '<header class="ebook-preview-review-bar" role="banner" aria-label="Review your ebook">'
        '<div class="ebook-review-copy">'
        f"<p class=\"ebook-review-kicker\">{html.escape(REVIEW_BAR_TITLE)}</p>"
        f"<p class=\"ebook-review-title\">{html.escape(title)}</p>"
        f"<p class=\"ebook-review-help\">{html.escape(REVIEW_BAR_HELP)}</p>"
        "</div>"
        f'<div class="ebook-review-actions" role="group" aria-label="Preview review actions">{buttons}</div>'
        '<p class="ebook-review-status" data-ebook-review-status role="status" aria-live="polite"></p>'
        "</header>"
    )


def _review_footer_html(*, can_approve: bool, already_approved: bool) -> str:
    buttons = _action_buttons_html(
        can_approve=can_approve, already_approved=already_approved, location="bottom"
    )
    return (
        '<footer class="ebook-preview-review-footer" role="contentinfo" aria-label="Preview review actions">'
        f'<div class="ebook-review-actions">{buttons}</div>'
        "</footer>"
    )


def _review_dialog_html() -> str:
    return (
        '<dialog class="ebook-review-dialog" data-ebook-review-dialog aria-labelledby="ebook-review-dialog-title">'
        '<form method="dialog" class="ebook-review-dialog-form">'
        f'<p id="ebook-review-dialog-title" class="ebook-review-dialog-copy">{html.escape(APPROVE_CONFIRM_PROMPT)}</p>'
        '<div class="ebook-review-dialog-actions">'
        '<button type="submit" value="cancel" class="ebook-review-btn ebook-review-btn-back" data-ebook-review-cancel>Cancel</button>'
        '<button type="button" class="ebook-review-btn ebook-review-btn-approve" data-ebook-review-confirm>Approve and Continue</button>'
        "</div></form></dialog>"
    )


_REVIEW_CSS = """
html.ebook-preview-viewer,
html.ebook-preview-viewer body {
  margin: 0 !important;
  padding: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: hidden;
  box-sizing: border-box;
  background: #64748b !important;
}
html.ebook-preview-viewer *,
html.ebook-preview-viewer *::before,
html.ebook-preview-viewer *::after {
  box-sizing: border-box;
}
.ebook-preview-review-bar,.ebook-preview-review-footer,.ebook-review-dialog {
  font-family: Georgia, "Times New Roman", serif;
}
.ebook-preview-review-bar {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  max-width: 100%;
  z-index: 4000;
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: flex-start;
  justify-content: space-between;
  box-sizing: border-box;
  padding: 12px 16px;
  background: #0f172a;
  color: #f8fafc;
  border-bottom: 3px solid #0f766e;
}
.ebook-review-copy {
  flex: 1 1 16rem;
  min-width: 0;
  max-width: 100%;
}
.ebook-review-kicker {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #99f6e4;
}
.ebook-review-title {
  margin: 4px 0 0;
  font-size: 18px;
  font-weight: 800;
  line-height: 1.25;
  color: #ffffff;
  overflow-wrap: anywhere;
}
.ebook-review-help {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.4;
  color: #e2e8f0;
}
.ebook-review-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: stretch;
  justify-content: flex-end;
  flex: 1 0 auto;
  flex-shrink: 0;
  min-width: 0;
  max-width: 100%;
}
.ebook-review-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  min-width: 0;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.2;
  text-decoration: none;
  cursor: pointer;
  border: 2px solid transparent;
  flex: 1 0 auto;
  flex-shrink: 0;
  white-space: nowrap;
  max-width: 100%;
}
.ebook-review-btn:focus {
  outline: 3px solid #fbbf24;
  outline-offset: 2px;
}
.ebook-review-btn-back {
  background: #ffffff;
  color: #0f172a;
  border-color: #ffffff;
}
.ebook-review-btn-changes {
  background: #fef3c7;
  color: #78350f;
  border-color: #f59e0b;
}
.ebook-review-btn-approve {
  background: #0f766e;
  color: #ffffff;
  border-color: #99f6e4;
}
.ebook-review-btn-approve:disabled,
.ebook-review-btn[disabled] {
  opacity: 0.55;
  cursor: not-allowed;
}
.ebook-review-status {
  flex: 1 1 100%;
  margin: 0;
  min-height: 1.2em;
  font-size: 14px;
  color: #fde68a;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.ebook-preview-stage {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 160px 16px 28px;
  overflow-x: hidden;
  display: flex;
  justify-content: center;
  box-sizing: border-box;
  background: #64748b;
}
.ebook-preview-frame {
  width: 100%;
  max-width: 8.5in;
  margin: 0 auto;
  overflow-x: hidden;
}
.ebook-preview-book {
  width: 100%;
  max-width: 100%;
  margin: 0 auto;
  overflow-x: hidden;
  overflow-wrap: anywhere;
  word-wrap: break-word;
}
html.ebook-preview-viewer .ebook-preview-book .title-page,
html.ebook-preview-viewer .ebook-preview-book .legal-page,
html.ebook-preview-viewer .ebook-preview-book .toc-page,
html.ebook-preview-viewer .ebook-preview-book .chapter-page,
html.ebook-preview-viewer .ebook-preview-book .back-matter-page {
  display: block;
  width: 100%;
  max-width: 100%;
  margin: 0 0 18px;
  padding: clamp(18px, 5%, 0.8in);
  background: #ffffff;
  border: 1px solid #94a3b8;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.18);
  overflow-x: hidden;
  overflow-wrap: anywhere;
}
html.ebook-preview-viewer .ebook-preview-page-break {
  display: none;
}
html.ebook-preview-viewer .ebook-preview-book img,
html.ebook-preview-viewer .ebook-preview-book table,
html.ebook-preview-viewer .ebook-preview-book pre,
html.ebook-preview-viewer .ebook-preview-book svg {
  max-width: 100% !important;
}
html.ebook-preview-viewer .ebook-preview-book table {
  width: 100% !important;
}
.ebook-preview-review-footer {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 20px 16px 28px;
  background: #0f172a;
  color: #f8fafc;
  border-top: 3px solid #0f766e;
  box-sizing: border-box;
  overflow-x: hidden;
}
.ebook-preview-review-footer .ebook-review-actions {
  width: 100%;
  max-width: 100%;
}
.ebook-review-dialog {
  border: 3px solid #0f172a;
  border-radius: 12px;
  padding: 20px;
  width: min(32rem, calc(100% - 24px));
  max-width: calc(100% - 24px);
  color: #0f172a;
  background: #ffffff;
  box-sizing: border-box;
}
.ebook-review-dialog::backdrop { background: rgba(15, 23, 42, 0.55); }
.ebook-review-dialog-copy {
  margin: 0 0 16px;
  font-size: 16px;
  line-height: 1.45;
}
.ebook-review-dialog-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  max-width: 100%;
}
@media (max-width: 1365px) {
  .ebook-preview-review-bar { padding: 12px; }
  .ebook-preview-stage { padding-left: 16px; padding-right: 16px; }
}
@media (max-width: 768px) {
  .ebook-preview-review-bar {
    flex-direction: column;
    align-items: stretch;
    padding: 10px 12px;
  }
  .ebook-review-copy,
  .ebook-review-actions,
  .ebook-review-status {
    flex: 1 1 100%;
    width: 100%;
    max-width: 100%;
  }
  .ebook-review-actions { justify-content: stretch; }
  .ebook-review-btn { flex: 1 1 100%; width: 100%; flex-shrink: 0; }
  .ebook-preview-stage { padding-top: 320px; padding-left: 12px; padding-right: 12px; }
  .ebook-preview-review-footer .ebook-review-btn { flex: 1 1 100%; width: 100%; flex-shrink: 0; }
}
@media (max-width: 320px) {
  .ebook-preview-review-bar { padding: 8px; }
  .ebook-preview-stage { padding-top: 330px; padding-left: 8px; padding-right: 8px; }
  .ebook-review-title { font-size: 16px; }
  .ebook-review-btn { font-size: 14px; }
}
@media print {
  .ebook-preview-review-bar,
  .ebook-preview-review-footer,
  .ebook-review-dialog { display: none !important; }
  html.ebook-preview-viewer,
  html.ebook-preview-viewer body { background: #ffffff; }
  .ebook-preview-stage { padding: 0; }
}
"""

_REVIEW_JS = r"""
(function () {
  var cfgEl = document.getElementById("ebook-preview-review-config");
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent || "{}");
  var bar = document.querySelector(".ebook-preview-review-bar");
  var stage = document.querySelector(".ebook-preview-stage");
  var statusEl = document.querySelector("[data-ebook-review-status]");
  var dialog = document.querySelector("[data-ebook-review-dialog]");
  var stale = false;

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg || "";
  }
  function sizeBar() {
    if (!bar || !stage) return;
    var extra = window.innerWidth <= 768 ? 16 : 16;
    stage.style.paddingTop = (Math.max(bar.offsetHeight, 72) + extra) + "px";
  }
  function disableApprove(message) {
    stale = true;
    document.querySelectorAll("[data-ebook-review-approve], [data-ebook-review-confirm]").forEach(function (btn) {
      btn.disabled = true;
    });
    if (message) setStatus(message);
  }
  function go(url) {
    window.location.assign(url);
  }
  document.querySelectorAll("[data-ebook-review-back]").forEach(function (el) {
    el.setAttribute("href", cfg.backUrl);
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      go(cfg.backUrl);
    });
  });
  document.querySelectorAll("[data-ebook-review-changes]").forEach(function (el) {
    el.setAttribute("href", cfg.changesUrl);
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      go(cfg.changesUrl);
    });
  });
  function openDialog() {
    if (stale || !cfg.canApprove) return;
    if (dialog && typeof dialog.showModal === "function") dialog.showModal();
    else if (dialog) dialog.setAttribute("open", "open");
  }
  document.querySelectorAll("[data-ebook-review-approve]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (btn.disabled) return;
      openDialog();
    });
  });
  var confirmBtn = document.querySelector("[data-ebook-review-confirm]");
  if (confirmBtn) {
    confirmBtn.addEventListener("click", function () {
      if (confirmBtn.disabled || stale || !cfg.canApprove) return;
      confirmBtn.disabled = true;
      fetch(cfg.approveUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: "preview", preview_digest: cfg.digest || "" })
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) throw new Error(data.error || "Could not approve this preview.");
          go(cfg.preflightUrl);
        });
      }).catch(function (err) {
        confirmBtn.disabled = false;
        if (dialog && typeof dialog.close === "function") dialog.close();
        setStatus(err.message || String(err));
      });
    });
  }
  function checkDigest() {
    fetch(cfg.workspaceUrl, { headers: { "Accept": "application/json" } })
      .then(function (res) { return res.json().catch(function () { return {}; }); })
      .then(function (data) {
        var design = (data.workspace || {}).design || {};
        var current = String(design.preview_digest || "");
        if (cfg.digest && current && current !== cfg.digest) {
          disableApprove(cfg.staleMessage);
        }
      })
      .catch(function () {});
  }
  sizeBar();
  window.addEventListener("resize", sizeBar);
  if (typeof ResizeObserver === "function" && bar) {
    new ResizeObserver(sizeBar).observe(bar);
  }
  if (cfg.digest) setInterval(checkDigest, 8000);
})();
"""
