"""Dump a short manuscript excerpt and preview HTML heading sample."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
import database

proj = database.get_project(20090)
data = proj["data"]
content = str(data.get("content") or "")
html = str(data.get("preview_html") or "")
print("H2", re.findall(r"(?m)^## .+$", content)[:10])
print("H3 count", len(re.findall(r"(?m)^### ", content)))
print("--- excerpt ---")
print(content[content.find("## Getting Started"):content.find("## Getting Started")+700])
print("--- html h3 sample ---")
h3s = re.findall(r"<h3[^>]*>.*?</h3>", html)[:8]
print("\n".join(h3s))
print("h3 css display", "display" in html)
print("127 in html", "127.0.0.1" in html)
