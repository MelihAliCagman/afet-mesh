import os
from dataclasses import replace

import pytest

from gateway.receiver.db import Database
from gateway.receiver.report import KIND_SOS, KIND_STATUS, decode_report, encode_report
from gateway.receiver.service import Gateway
from sim.packet import PacketType
from sim.security import PersistentCounter, Sender
from sim.wire import decode, encode

KEY = bytes(range(16))  # yalnızca test anahtarı


def make():
    db = Database()
    return db, Gateway(db, KEY), Sender(5, KEY, PersistentCounter({}, block=64))


def data_frame(node, kind=KIND_STATUS, text="x"):
    return encode(node.seal(1, 1, PacketType.DATA, encode_report(kind, 10, -20, 77, 3, text)))


def test_wire_roundtrip():
    n = Sender(5, KEY)
    p = n.seal(1, 1, PacketType.DATA, b"abc")
    assert decode(encode(p)) == p


def test_wire_rejects_garbage():
    with pytest.raises(ValueError):
        decode(b"\x01\x02")
    with pytest.raises(ValueError):
        decode(bytes([1, 1, 1, 99, 0, 1, 8, 5]) + b"\x00" * 6)


def test_report_roundtrip_and_validation():
    r = decode_report(encode_report(KIND_SOS, -300, 410, 41, 7, "yaralı"))
    assert (r["kind"], r["x"], r["y"], r["battery"], r["code"], r["text"]) == (KIND_SOS, -300, 410, 41, 7, "yaralı")
    with pytest.raises(ValueError):
        decode_report(b"\x01")
    with pytest.raises(ValueError):
        decode_report(encode_report(9, 0, 0, 50))
    with pytest.raises(ValueError):
        decode_report(encode_report(KIND_STATUS, 0, 0, 101))


def test_data_stored_and_acked():
    db, gw, node = make()
    acks = gw.on_frame(data_frame(node, text="devriye"), rssi=-100.0)
    assert len(acks) == 1
    ack = decode(acks[0])
    assert ack.ptype == PacketType.ACK and ack.next_hop == 5 and ack.payload != bytes([5])
    m = db.messages()
    assert len(m) == 1 and m[0]["text"] == "devriye" and m[0]["src"] == 5
    assert db.nodes()[0]["battery"] == 77
    assert db.pending_count() == 1


def test_duplicate_not_stored_twice_but_acked():
    db, gw, node = make()
    f = data_frame(node)
    gw.on_frame(f)
    acks = gw.on_frame(f)
    assert len(acks) == 1
    assert db.message_count() == 1 and db.pending_count() == 1
    assert db.rx_stats()["dup"] == 1


def test_tampered_and_forged_rejected():
    db, gw, node = make()
    f = decode(data_frame(node))
    bad = replace(f, payload=bytes([f.payload[0] ^ 1]) + f.payload[1:])
    assert gw.on_frame(encode(bad)) == []
    forged = Sender(5, os.urandom(16)).seal(1, 1, PacketType.DATA, encode_report(KIND_STATUS, 0, 0, 50))
    assert gw.on_frame(encode(forged)) == []
    assert db.message_count() == 0
    assert db.rx_stats()["bad_tag"] == 2
    assert {a["kind"] for a in db.alarms()} == {"bad_tag"}


def test_replay_raises_alarm_and_is_not_stored():
    db, gw, node = make()
    old = data_frame(node)
    gw.on_frame(old)
    for _ in range(3):
        gw.on_frame(data_frame(node))
    gw.on_frame(old)
    assert any(a["kind"] == "replay" for a in db.alarms())
    assert db.message_count() == 4


def test_not_for_gateway_and_malformed_ignored():
    db, gw, node = make()
    p = node.seal(1, 9, PacketType.DATA, encode_report(KIND_STATUS, 0, 0, 50))
    assert gw.on_frame(encode(replace(p, next_hop=9))) == []
    assert gw.on_frame(b"\x00") == []
    assert db.message_count() == 0 and db.rx_stats()["malformed"] == 1


def test_hello_updates_node_only():
    db, gw, node = make()
    gw.on_frame(encode(node.seal(255, 255, PacketType.HELLO, b"", ttl=1)), rssi=-105.0)
    n = db.nodes()[0]
    assert n["hello_count"] == 1 and n["last_rssi"] == -105.0 and n["msg_count"] == 0


def test_clone_alarm_in_db():
    t = [0.0]
    db = Database()
    gw = Gateway(db, KEY, clock=lambda: t[0])
    good = Sender(5, KEY, PersistentCounter({}, block=64))
    for _ in range(200):
        gw.on_frame(data_frame(good))
    clone = Sender(5, KEY, PersistentCounter({}, block=64))
    for _ in range(4):
        t[0] += 1
        gw.on_frame(data_frame(clone))
    assert any(a["kind"] == "klon_alarmi" for a in db.alarms())
