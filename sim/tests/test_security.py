import os
from dataclasses import replace

from sim.packet import PacketType
from sim.security import MAX_JUMP, PersistentCounter, Receiver, Sender

KEY = bytes(range(16))  # yalnızca test anahtarı
GW = 1


def make(node_id=5, flash=None):
    return Sender(node_id, KEY, PersistentCounter(flash if flash is not None else {}, block=64))


def test_roundtrip():
    rx, tx = Receiver(KEY), make()
    f = tx.seal(GW, GW, PacketType.DATA, b"merhaba")
    assert f.payload != b"merhaba"
    assert rx.open(f) == ("ok", b"merhaba")


def test_tamper_payload_src_and_key():
    rx, tx = Receiver(KEY), make()
    f = tx.seal(GW, GW, PacketType.DATA, b"merhaba")
    assert rx.open(replace(f, payload=bytes([f.payload[0] ^ 1]) + f.payload[1:]))[0] == "bad_tag"
    assert rx.open(replace(f, src=6))[0] == "bad_tag"
    assert rx.open(replace(f, tag=bytes(4)))[0] == "bad_tag"
    assert rx.open(Sender(5, os.urandom(16)).seal(GW, GW, PacketType.DATA, b"merhaba"))[0] == "bad_tag"


def test_hop_fields_not_authenticated():
    rx, tx = Receiver(KEY), make()
    f = tx.seal(GW, GW, PacketType.DATA, b"x")
    assert rx.open(replace(f, ttl=1, next_hop=9))[0] == "ok"


def test_duplicate_and_replay():
    t = [0.0]
    rx, tx = Receiver(KEY, clock=lambda: t[0]), make()
    frames = [tx.seal(GW, GW, PacketType.DATA, b"x") for _ in range(5)]
    for f in frames:
        assert rx.open(f)[0] == "ok"
    assert rx.open(frames[-1])[0] == "dup"
    assert rx.open(frames[1])[0] == "dup"  # kısa süre içinde: yeniden gönderim
    t[0] += 120
    assert rx.open(frames[1])[0] == "replay"  # uzun süre sonra: tekrar oynatma


def test_counter_rollover():
    rx, tx = Receiver(KEY), make(flash={"ctr": 65450})
    seqs = []
    for _ in range(40):
        f = tx.seal(GW, GW, PacketType.DATA, b"x")
        seqs.append(f.seq)
        assert rx.open(f)[0] == "ok"
    assert min(seqs) < 100 and max(seqs) > 65000


def test_reboot_without_persistence_is_flagged():
    t = [0.0]
    rx = Receiver(KEY, clock=lambda: t[0])
    flash = {}
    a = make(flash=flash)
    for _ in range(100):
        rx.open(a.seal(GW, GW, PacketType.DATA, b"x"))
    from sim.security import Sender as S
    reset = S(5, KEY)
    res = [rx.open(reset.seal(GW, GW, PacketType.DATA, b"x"))[0] for _ in range(3)]
    assert res == ["regression"] * 3
    assert rx.alarms and rx.alarms[0][0] == 5


def test_reboot_with_persistence_is_accepted():
    rx = Receiver(KEY)
    flash = {}
    a = make(flash=flash)
    for _ in range(100):
        rx.open(a.seal(GW, GW, PacketType.DATA, b"x"))
    b = make(flash=flash)
    assert [rx.open(b.seal(GW, GW, PacketType.DATA, b"x"))[0] for _ in range(3)] == ["ok"] * 3


def test_far_jump_rejected():
    rx = Receiver(KEY)
    a = make()
    rx.open(a.seal(GW, GW, PacketType.DATA, b"x"))
    far = Sender(5, KEY, PersistentCounter({"ctr": 10 * MAX_JUMP}, block=64))
    assert rx.open(far.seal(GW, GW, PacketType.DATA, b"x"))[0] == "jump"


def test_different_types_do_not_confuse():
    rx, tx = Receiver(KEY), make()
    h = tx.seal(255, 255, PacketType.HELLO, b"")
    d = tx.seal(GW, GW, PacketType.DATA, b"x")
    assert rx.open(h)[0] == "ok" and rx.open(d)[0] == "ok"
    assert rx.open(replace(d, ptype=PacketType.ACK))[0] == "bad_tag"


def test_late_frame_within_window_accepted_once():
    t = [0.0]
    rx, tx = Receiver(KEY, clock=lambda: t[0]), make()
    frames = [tx.seal(GW, GW, PacketType.DATA, b"x") for _ in range(6)]
    for i in (0, 1, 2, 4, 5):
        assert rx.open(frames[i])[0] == "ok"
    assert rx.open(frames[3])[0] == "ok"      # geç gelen, pencere içinde
    assert rx.open(frames[3])[0] == "dup"     # ikinci kez gelirse kopya
    assert not rx.alarms


def test_old_unseen_frame_beyond_window_is_regression():
    rx, tx = Receiver(KEY), make()
    frames = [tx.seal(GW, GW, PacketType.DATA, b"x") for _ in range(100)]
    for f in frames[50:]:
        rx.open(f)
    assert rx.open(frames[0])[0] == "regression"
