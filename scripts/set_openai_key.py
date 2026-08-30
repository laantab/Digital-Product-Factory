"""Write the OpenAI API key into .env, then prove it actually works.

Driven by Set_OpenAI_Key.bat, which puts the key in FACTORY_NEW_OPENAI_KEY
rather than passing it as an argument (arguments are visible in the process
list to anything running on the machine; an env var of a child process is not).

Two things this does that hand-editing .env does not:

  * Writes BOTH names. app.py reads OPENAI_API_KEY and the integrations layer
    reads AI_INTEGRATIONS_OPENAI_API_KEY -- they are always the same key, and
    when only one gets updated the app half-works in a way that is genuinely
    hard to diagnose.
  * Calls OpenAI once, for real, before declaring success. A key that is
    revoked, truncated by a bad paste, or from the wrong account is otherwise
    only discovered later, mid-generation, as a 401 in a log nobody is reading.
"""
from __future__ import annotations

import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(APP_DIR, ".env")
KEY_NAMES = ("OPENAI_API_KEY", "AI_INTEGRATIONS_OPENAI_API_KEY")


def mask(value: str) -> str:
    return f"{value[:7]}...{value[-4:]}" if len(value) > 11 else "(too short to mask)"


def set_key(lines: list[str], name: str, value: str) -> list[str]:
    out, found = [], False
    for line in lines:
        if line.strip().startswith(f"{name}="):
            out.append(f"{name}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{name}={value}")
    return out


def verify(key: str) -> tuple[bool, str]:
    """One real call. /models is the cheapest endpoint that still checks auth."""
    try:
        import requests
    except ImportError:
        return True, "  (requests not installed - skipped the live check)"
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=25,
        )
    except Exception as exc:  # noqa: BLE001
        return True, f"  Could not reach OpenAI to check the key ({type(exc).__name__})."
    if resp.status_code == 200:
        return True, "  Verified with OpenAI: the key works."
    if resp.status_code == 401:
        return False, "  OpenAI rejected this key (401 Unauthorized)."
    if resp.status_code == 429:
        return False, "  OpenAI says this key is out of quota or rate limited (429)."
    return False, f"  OpenAI returned {resp.status_code}."


def main() -> int:
    key = (os.environ.get("FACTORY_NEW_OPENAI_KEY") or "").strip()
    if not key:
        print("  No key was passed in. Nothing changed.")
        return 1
    if not os.path.exists(ENV_PATH):
        print(f"  Could not find .env at {ENV_PATH}. Nothing changed.")
        return 1

    # utf-8-sig strips a leading BOM if one is there. Windows PowerShell 5.1's
    # `Set-Content -Encoding UTF8` writes one, and a BOM silently corrupts the
    # NAME of the first variable -- .env's first line becomes
    # "﻿AI_INTEGRATIONS_OPENAI_API_KEY", which python-dotenv then never
    # matches, so the key reads as unset while looking perfectly fine in an
    # editor. Reading with utf-8-sig and writing without a BOM repairs it.
    with open(ENV_PATH, "r", encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()

    # Check the key BEFORE writing it, so a bad paste never replaces a
    # working key with a broken one.
    ok, detail = verify(key)
    print(detail)
    if not ok:
        print()
        print("  .env was NOT changed - your previous key is still in place.")
        print("  Create a fresh key at platform.openai.com and run this again.")
        return 1

    for name in KEY_NAMES:
        lines = set_key(lines, name, key)

    with open(ENV_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    print()
    print(f"  Saved {mask(key)} ({len(key)} characters) to:")
    for name in KEY_NAMES:
        print(f"    {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
