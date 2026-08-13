"""Global safety fixtures for the Factory test suite."""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(autouse=True)
def block_paid_and_external_network(monkeypatch):
    """Fail every external network call; local Flask test traffic is allowed."""
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_API_KEY", "")
    monkeypatch.setenv("PEXELS_API_KEY", "")

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def checked_connect(sock, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host).lower() not in _LOCAL_HOSTS:
            raise RuntimeError(f"External network blocked during tests: {host}")
        return original_connect(sock, address)

    def checked_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host).lower() not in _LOCAL_HOSTS:
            raise RuntimeError(f"External network blocked during tests: {host}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", checked_connect)
    monkeypatch.setattr(socket, "create_connection", checked_create_connection)

    try:
        import requests.sessions

        original_request = requests.sessions.Session.request

        def checked_request(session, method, url, *args, **kwargs):
            host = (urlparse(str(url)).hostname or "").lower()
            if host not in _LOCAL_HOSTS:
                raise RuntimeError(f"External HTTP blocked during tests: {url}")
            return original_request(session, method, url, *args, **kwargs)

        monkeypatch.setattr(requests.sessions.Session, "request", checked_request)
    except ImportError:
        pass
