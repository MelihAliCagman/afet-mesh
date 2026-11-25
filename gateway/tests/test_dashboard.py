from fastapi.testclient import TestClient

from gateway.dashboard.app import build_health, create_app, events_since, node_status
from gateway.mockradio import MockRadio
from gateway.receiver.db import Database

KEY = bytes(range(16))  # yalnızca test anahtarı


def setup(until=300):
    db = Database()
    mock = MockRadio(db, key=KEY, seed=3)
    mock.run(until)
    return db, mock, TestClient(create_app(db, mock.clock, mock))


def test_node_status_thresholds():
    assert node_status(10) == "canli" and node_status(100) == "gecikmis" and node_status(500) == "kayip"


def test_nodes_and_messages_endpoints():
    db, mock, c = setup()
    nodes = c.get("/api/nodes").json()
    assert len(nodes) == 8 and all(n["status"] == "canli" for n in nodes)
    msgs = c.get("/api/messages?limit=5").json()
    assert len(msgs) == 5 and msgs[0]["id"] > msgs[-1]["id"] and "kind_name" in msgs[0]
    after = c.get(f"/api/messages?after_id={msgs[0]['id']}").json()
    assert after == []


def test_health_counts_and_dead_node():
    db, mock, c = setup()
    h = c.get("/api/health").json()
    assert h["nodes_total"] == 8 and h["canli"] == 8 and h["messages_total"] == db.message_count()
    assert h["outbox_pending"] == db.message_count()
    c.post("/api/demo/kill/5")
    mock.run(200)
    h = c.get("/api/health").json()
    assert h["canli"] == 7 and h["gecikmis"] + h["kayip"] == 1
    st = {n["node_id"]: n["status"] for n in c.get("/api/nodes").json()}
    assert st[5] != "canli"


def test_attack_endpoints_create_alarms_without_messages():
    db, mock, c = setup()
    n = db.message_count()
    assert c.post("/api/demo/attack/forgery").status_code == 200
    assert c.post("/api/demo/attack/clone").status_code == 200
    assert c.post("/api/demo/attack/bilinmeyen").status_code == 404
    assert c.post("/api/demo/kill/99").status_code == 404
    assert db.message_count() == n
    kinds = {a["kind"] for a in c.get("/api/alarms").json()}
    assert "bad_tag" in kinds and "klon_alarmi" in kinds


def test_events_since_returns_new_items_in_order():
    db, mock, c = setup(120)
    ev, lm, la = events_since(db, 0, 0)
    assert [e["type"] for e in ev].count("message") == db.message_count() or len(ev) >= 50
    mock.run(60)
    ev2, lm2, la2 = events_since(db, lm, la)
    ids = [e["data"]["id"] for e in ev2 if e["type"] == "message"]
    assert ids == sorted(ids) and lm2 > lm
    ev3, _, _ = events_since(db, lm2, la2)
    assert ev3 == []


def test_index_served():
    db, mock, c = setup(60)
    assert c.get("/").status_code == 200
