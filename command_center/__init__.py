"""The Digital Product Factory Command Center.

A small, standalone, read-only-to-the-Factory status page. It answers,
every morning, without opening any other file: where work stopped, what
finished, what is still open, the one next step, which Claude to use for
it, and the exact version/commit this checkout is on.

It is deliberately NOT part of ``app.py``. It imports nothing from
``services/*`` or ``database.py`` (see ``command_center/status.py`` and
``command_center/server.py``), runs on its own port, and cannot generate a
product, call a paid API, or touch customer data. See
``command_center/README.md``.
"""
