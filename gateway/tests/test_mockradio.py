from gateway.mockradio import MockRadio
from gateway.receiver.db import Database

KEY = bytes(range(16))  # yalnızca test anahtarı


def run(seed=3, until=300):
    db = Database()
    radio = MockRadio(db, key=KEY, seed=seed)
    radio.run(until)
    return db, radio


def test_db_matches_simulation_gateway_and_has_no_false_alarms():
    db, radio = run()
    assert db.message_count() == len(radio.gw_node.delivered) > 50
    assert db.alarms() == []
    assert {n["node_id"] for n in db.nodes()} == set(range(2, 10))


def test_retransmissions_do_not_create_duplicate_messages():
    db, radio = run()
    uids = [m["uid"] for m in db.messages(10000)]
    assert len(uids) == len(set(uids))
    assert db.pending_count() == db.message_count()


def test_attacks_add_no_messages_and_raise_alarms():
    db, radio = run()
    n = db.message_count()
    radio.inject_replay(5)
    radio.inject_forgery(4, 5)
    radio.inject_clone(6, 4)
    assert db.message_count() == n
    kinds = {a["kind"] for a in db.alarms(200)}
    assert {"bad_tag", "klon_alarmi"} <= kinds


def test_dead_node_stops_reporting():
    db, radio = run()
    radio.kill_node(5)
    before = {n["node_id"]: n["msg_count"] for n in db.nodes()}
    radio.run(120)
    after = {n["node_id"]: n["msg_count"] for n in db.nodes()}
    assert after[5] == before[5]
    assert after[9] > before[9]


def test_deterministic():
    a, _ = run(seed=5, until=120)
    b, _ = run(seed=5, until=120)
    assert [m["uid"] for m in a.messages(1000)] == [m["uid"] for m in b.messages(1000)]
