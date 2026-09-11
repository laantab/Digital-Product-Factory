# Digital Product Factory Command Center

One page that answers, every morning, without opening anything else:
where you stopped, what finished, what's still open, the one next step,
which Claude to use for it, and the exact version/commit this checkout is
on.

## How to open it

Double-click **`command_center\Open Command Center.bat`** (in this
folder). It opens `http://127.0.0.1:5090/` in your browser and starts the
Command Center's own tiny server on port 5090 — separate from the
owner's Factory window (5055, `Desktop\Open Factory.bat`) and Claude's
Factory window (5077), so it never competes with either and can be left
running alongside them.

Or, from Claude Code, use the `.claude/launch.json` entry named
`command-center`.

Close the console window (or Ctrl+C in it) to stop it. As with the main
Factory, the server does not auto-reload — if you edit a `command_center`
file, close and reopen it.

## What it is (and is not)

- It is **read-only toward the Factory**: it never writes to
  `projects.db`, never touches the `exports/` directory, and never calls
  OpenAI, Tavily, Pexels, or any paid API. It cannot generate a product.
  `command_center/server.py` and `command_center/status.py` do not import
  anything from `services/product.py`, `services/ad.py`,
  `services/ebook.py`, `database.py`, or any AI client — there is nothing
  in this folder capable of triggering those paths.
- Its **only write** is its own status record,
  `command_center/handoff_status.json`, and only when you use the
  "Update handoff" form on the page (or hand-edit the file yourself).
- It is **not part of `app.py`** and is never deployed to Render. It is a
  local tool for the owner, checked into this repo the same way
  `SESSION_HANDOFF_*.md` and `VERSION` are, so it travels with the
  Factory and survives a fresh checkout.

## Where its state lives (durability)

- **`command_center/handoff_status.json`** — the one canonical current
  handoff: what you're working on, where you stopped, what finished
  today (and a short history before that), what's open, the one next
  step, and which Claude to use for it. This is a plain file in the repo,
  git-tracked exactly like `SESSION_HANDOFF_*.md` and `VERSION` already
  are — it survives an app restart, a machine restart, and a fresh
  checkout on another machine, because it survives the same way every
  other file in this repo does.
- **`command_center/component_versions.json`** — the durable
  per-component version manifest (Word Search engine, Crossword engine,
  shared topic/vocabulary resolver): version, status (good / regression /
  unknown), last-known-good commit, and a one-line note. Update it by
  hand at release time, the same discipline as `VERSION` and
  `CHANGELOG.md`.

Both files are small, plain JSON, reviewable in any diff — not a
throwaway temp file, and not a new database.

## What is read automatically vs. typed by hand

**Automatic**, every time the page loads:
- Git branch and commit (`git rev-parse`, read-only)
- Whether this checkout matches the expected folder name (`Factory-v1.3`)
  and branch (`main`)
- The Factory's overall version (`VERSION`, via
  `services/factory_version.py` — the module the rest of the app already
  uses)
- The most recent full-gate result, by reading
  `test-results/factory-junit.xml` if it exists (no test is run to
  populate this — it reads whatever the last gate run already wrote)
- The list of `SESSION_HANDOFF_*.md` files present, newest first

**Typed by hand, once per session**, via the "Update handoff" form (or by
editing `handoff_status.json` directly):
- Current task, where you stopped, what you finished today, the one open
  issue, the one next step, which Claude environment for it, and any
  notes
- The per-component version manifest (`component_versions.json`) — bump
  it yourself at release time

## Tests

`tests/test_command_center.py` (registered in
`tests/acceptance_manifest.json`) proves this module identifies
`Factory-v1.3`/`main` as the source of truth, reads a real git commit,
reads version/component information, loads the handoff record with safe
fallbacks when data is missing, exposes exactly one next step, tells
completed/open/blocked apart, survives a restart (state lives in the
file, not memory), and — the important one — cannot generate a product or
call a paid API, because it imports nothing that can.
