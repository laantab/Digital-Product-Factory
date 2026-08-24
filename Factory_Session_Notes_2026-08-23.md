# Factory Session Notes — Sunday, 23 August 2026

## What was done today

**Confirmed nothing was lost.**
Spent much of the day looking for "missing" work. It wasn't missing:

- Friday's session (21 Aug) was already committed and pushed to GitHub.
- The local `flask_app` folder showed "No uncommitted changes" — everything saved.
- The Factory app runs fine at `http://127.0.0.1:5000`.

**Ran the full release gate.** Result:

```
885 passed, 78 subtests passed in 302.52s (0:05:02)
PASS: release gate completed
Tests: 963   Failures: 0   Errors: 0   Skipped: 0
Paid API calls permitted: 0
SUCCESS: The full release gate passed.
```

This is the 885/885 that Friday's session was aiming for and couldn't
reach. The Factory is fully working.

**Rotated the OpenAI API key.** Old key deleted at platform.openai.com,
new key written into `.env`.

---

## Key locations

| What | Where |
|------|-------|
| Factory folder | `C:\Users\user\OneDrive\Desktop\Factory_Stabilized_Source_V2_20260809\Factory_Stabilized_V2\flask_app` |
| Live app | `http://127.0.0.1:5000` |
| Main repo | `github.com/laantab/Digital-Product-Factory` |
| Backup repo | `github.com/laantab/The-Digital-Product-Factory` |

---

## Still to do

- [ ] Delete the `.env.backup_...` file in flask_app — it still contains
      the OLD API key.
- [ ] Upload `Update_API_Key_Anywhere.bat` to the GitHub repo
      (Add file → Upload files → Commit changes).
- [ ] **Finish project #20090** — *Beginner's Guide to Container Gardening*.
      This is the closest thing to a sellable product. The agent was
      repairing the Ebook PDF pipeline for it. Open the Factory and check
      whether the PDF is actually finished.

---

## Lessons worth keeping

**Chat is not storage.** Files uploaded to a chat window disappear when
the session ends. The GitHub repo is the real backup.

**The repo is how to share code.** Instead of zipping and uploading the
folder each time, paste the repo URL. It's public, so it can be read
directly. No zip needed — the old `ZIP-FLASK-APP.bat` can be retired.

**Run the preflight before and after any work session.**
Double-click `Run_Factory_Preflight.bat`.
Green (885 passed) = safe to commit and keep building.
Red = fix that before adding anything new.
It answers "what state is my project in?" in five minutes — far faster
than searching through folders.

**Cursor works on the files directly; this chat does not.** Cursor is
installed on the computer with the folder open. A chat window runs on
Anthropic's servers and cannot see local files, the Desktop, or the
browser.

---

## Next session — start here

1. Double-click `Run_Factory_Preflight.bat`. Confirm 885 passed.
2. Open `http://127.0.0.1:5000`.
3. Go to project #20090 and see what state the ebook is in.
4. Update this file at the end of the session.
