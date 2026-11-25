import os
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "remote-server"))
import server  # noqa: E402

from gateway.bridge.bridge import Bridge, ConnectivityMonitor, SimulatedCrash  # noqa: E402
from gateway.receiver.db import Database  # noqa: E402

KEY = "test-anahtari"  # yalnızca test


class Net:
    """İnterneti kesip açabilen sahte ağ: kapalıyken bağlantı hatası verir."""

    def __init__(self, client):
        self.client = client
        self.up = True
        self.fail_status = None

    def get(self, url, **kw):
        if not self.up:
            raise httpx.ConnectError("internet yok")
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        if not self.up:
            raise httpx.ConnectError("internet yok")
        return self.client.post(url, **kw)


def body(i, src=5):
    return {"uid": f"{src}:{i}", "src": src, "counter": i, "kind": "durum", "x": 1, "y": 2, "battery": 80,
            "code": 0, "text": "", "received_at": 1000.0 + i}


def fill(db, n, start=1):
    for i in range(start, start + n):
        db.enqueue(f"5:{i}", body(i), 1000.0 + i)


def make(tmp=":memory:"):
    app = server.create_app(":memory:", KEY)
    client = TestClient(app)
    net = Net(client)
    t = [0.0]
    db = Database(tmp)
    br = Bridge(db, net, KEY, clock=lambda: t[0])
    return db, br, net, client, t


def remote_total(client):
    return client.get("/api/stats", headers={"X-API-Key": KEY}).json()["total"]


def test_server_requires_key_and_dedups():
    client = TestClient(server.create_app(":memory:", KEY))
    b = {"gateway": "gw", "messages": [body(1), body(2)]}
    assert client.post("/ingest", json=b).status_code == 401
    assert client.post("/ingest", json=b, headers={"X-API-Key": "yanlis"}).status_code == 401
    assert client.post("/ingest", json=b, headers={"X-API-Key": KEY}).json() == {"accepted": 2, "duplicates": 0}
    assert client.post("/ingest", json=b, headers={"X-API-Key": KEY}).json() == {"accepted": 0, "duplicates": 2}
    assert remote_total(client) == 2
    assert client.get("/health").json() == {"ok": True}


def test_server_refuses_to_start_without_key(monkeypatch):
    monkeypatch.delenv("REMOTE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        server.create_app(":memory:")


def test_monitor_hysteresis():
    seq = iter([True, True, False, True, False, False, True, True])
    m = ConnectivityMonitor(lambda: next(seq), up_after=2, down_after=2)
    states = [m.check() for _ in range(8)]
    assert states == ["OFFLINE", "ONLINE", "ONLINE", "ONLINE", "ONLINE", "OFFLINE", "OFFLINE", "ONLINE"]


def test_online_drains_queue():
    db, br, net, client, t = make()
    fill(db, 120)
    br.step()
    br.step()  # ilk tur yalnızca ONLINE'a geçişi doğrular
    assert db.pending_count() == 0 and db.sent_count() == 120
    assert remote_total(client) == 120
    assert br.stats["batches"] == 3  # 50 + 50 + 20


def test_offline_accumulates_then_drains_without_loss():
    db, br, net, client, t = make()
    net.up = False
    fill(db, 30)
    for _ in range(5):
        t[0] += 10
        assert br.step() == "OFFLINE"
    assert db.pending_count() == 30 and remote_total(client) == 0
    net.up = True
    fill(db, 10, start=31)
    for _ in range(3):
        t[0] += 10
        br.step()
    assert db.pending_count() == 0 and remote_total(client) == 40


def test_crash_after_post_causes_resend_but_no_duplicate_record():
    db, br, net, client, t = make()
    fill(db, 20)
    br.step()
    br.crash_after_post = lambda: True
    with pytest.raises(SimulatedCrash):
        br.step()
    assert remote_total(client) == 20 and db.pending_count() == 20  # sunucuda var, istemci işaretlememiş
    br2 = Bridge(db, net, KEY, clock=lambda: t[0])
    br2.step()
    br2.step()
    assert db.pending_count() == 0 and remote_total(client) == 20
    assert br2.stats["duplicates_reported"] == 20


def test_backoff_grows_on_server_errors():
    db, br, net, client, t = make()
    fill(db, 5)
    br.step()  # ONLINE olmadan yükleme yok
    real_post = net.post
    net.post = lambda url, **kw: httpx.Response(500, request=httpx.Request("POST", url))
    waits = []
    for _ in range(4):
        t[0] = max(t[0], br.next_try) + 0.001
        br.step()
        waits.append(round(br.next_try - t[0]))
    assert waits == [2, 4, 8, 16] and db.pending_count() == 5
    assert br.stats["failures"] == 4
    net.post = real_post
    t[0] = br.next_try + 1
    br.step()
    assert db.pending_count() == 0 and br.fails == 0


def test_outbox_survives_restart(tmp_path):
    path = str(tmp_path / "gw.db")
    db = Database(path)
    fill(db, 15)
    db.close()
    db2 = Database(path)
    assert db2.pending_count() == 15
    app = server.create_app(":memory:", KEY)
    net = Net(TestClient(app))
    br = Bridge(db2, net, KEY)
    br.step()
    br.step()
    assert db2.pending_count() == 0
