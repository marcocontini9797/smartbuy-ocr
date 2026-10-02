import pytest

from api import session


class FakeAuth:
    def __init__(self, ok=True):
        self.calls, self.ok = 0, ok

    def get_user(self, token):
        self.calls += 1
        if not self.ok:
            raise ValueError("expired")
        return type("R", (), {"user": type("U", (), {"id": "user-1"})()})()


class FakeClient:
    def __init__(self, ok=True):
        self.auth = FakeAuth(ok)


def test_verified_token_is_not_checked_again_within_the_window():
    session._VERIFIED.clear()
    client = FakeClient()
    assert session._verified_user(client, "tok") == "user-1"
    assert session._verified_user(client, "tok") == "user-1"
    assert client.auth.calls == 1
    session._verified_user(client, "other")
    assert client.auth.calls == 2


def test_cache_expires_and_never_stores_failures(monkeypatch):
    session._VERIFIED.clear()
    client = FakeClient()
    now = [1000.0]
    monkeypatch.setattr(session.time, "monotonic", lambda: now[0])
    session._verified_user(client, "tok")
    now[0] += session.TOKEN_CACHE_SECONDS + 1
    session._verified_user(client, "tok")
    assert client.auth.calls == 2
    bad = FakeClient(ok=False)
    for _ in range(2):
        with pytest.raises(ValueError):
            session._verified_user(bad, "bad")
    assert bad.auth.calls == 2
