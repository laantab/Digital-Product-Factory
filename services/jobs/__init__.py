"""Durable execution for long-running Factory work.

The browser must not own execution. See services/jobs/store.py for why,
and services/jobs/executor.py for what actually drives a build forward.
"""
