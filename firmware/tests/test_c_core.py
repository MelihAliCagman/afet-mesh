import ctypes as C
import os
import random
import sys
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

sys.path.insert(0, os.path.dirname(__file__))
import c_api  # noqa: E402
from c_api import Packet, buf, payload_of, tag_of, to_c  # noqa: E402

from sim.lora import DutyCycle, airtime  # noqa: E402
from sim.packet import PacketType  # noqa: E402
from sim.routing import RoutingTable, link_cost, seq_newer  # noqa: E402
from sim.security import PersistentCounter, Receiver, Sender  # noqa: E402
from sim.wire import decode, encode  # noqa: E402

KEY = bytes(range(16))  # yalnızca test anahtarı


@pytest.fixture(scope="module")
def L(lib):
    return c_api.setup(lib)


def open_c(L, rx, pkt, t_ms):
    c = to_c(pkt)
    alarm, cnt = C.c_uint8(), C.c_uint32()
    st = L.afet_receiver_open(rx, C.byref(c), t_ms, C.byref(alarm), C.byref(cnt))
    return c_api.STATUS[st], c, bool(alarm.value)


# ---------------- paket biçimi ----------------
def test_wire_matches_python(L):
    rng = random.Random(1)
    for _ in range(300):
        n = rng.randint(0, 64)
        p = Sender(rng.randint(1, 250), os.urandom(16)).seal(rng.randint(1, 255), rng.randint(1, 255),
                                                            rng.choice(list(PacketType)), os.urandom(n))
        p = replace(p, ttl=rng.randint(0, 255), last_hop=rng.randint(0, 255))
        py = encode(p)
        out = C.create_string_buffer(128)
        assert L.afet_wire_encode(C.byref(to_c(p)), out, 128) == len(py)
        assert out.raw[: len(py)] == py
        c = Packet()
        assert L.afet_wire_decode(py, len(py), C.byref(c)) == 0
        q = decode(py)
        assert (c.src, c.dst, c.next_hop, c.ptype, c.seq, c.ttl, c.last_hop) == \
            (q.src, q.dst, q.next_hop, q.ptype.value, q.seq, q.ttl, q.last_hop)
        assert payload_of(c) == q.payload and tag_of(c) == q.tag


def test_wire_errors(L):
    c = Packet()
    assert L.afet_wire_decode(b"\x01\x02", 2, C.byref(c)) < 0
    assert L.afet_wire_decode(bytes([1, 1, 1, 99, 0, 1, 8, 5]) + b"\x00" * 4, 12, C.byref(c)) < 0
    assert L.afet_wire_decode(bytes(12 + 65), 77, C.byref(c)) < 0


# ---------------- AES-128-CCM ----------------
def test_ccm_matches_python_library(L):
    rng = random.Random(2)
    ctx = buf(L, "sender")  # içinde ccm bağlamı var, ilk alan
    for _ in range(400):
        key, nonce = os.urandom(16), os.urandom(12)
        aad = os.urandom(rng.choice([0, 1, 5, 14, 15, 16, 17, 31]))
        pt = os.urandom(rng.randint(0, 64))
        L.afet_ccm_init(ctx, key)
        ct, tag = C.create_string_buffer(max(1, len(pt))), C.create_string_buffer(4)
        assert L.afet_ccm_seal(ctx, nonce, aad, len(aad), pt, len(pt), ct, tag) == 0
        ref = AESCCM(key, tag_length=4).encrypt(nonce, pt, aad or None)
        assert ct.raw[: len(pt)] == ref[:-4] and tag.raw == ref[-4:]
        out = C.create_string_buffer(max(1, len(pt)))
        assert L.afet_ccm_open(ctx, nonce, aad, len(aad), ref[:-4], len(pt), ref[-4:], out) == 0
        assert out.raw[: len(pt)] == pt
        bad_tag = ref[-4:-1] + bytes([ref[-1] ^ 1])
        assert L.afet_ccm_open(ctx, nonce, aad, len(aad), ref[:-4], len(pt), bad_tag, out) == -1


# ---------------- gönderen: sayaç ve kare üretimi ----------------
def test_sender_matches_python(L):
    key = os.urandom(16)
    writes_c, flash = [], {}
    s = buf(L, "sender")
    cb = c_api.PERSIST(lambda _ctx, reserved: writes_c.append(reserved))
    L.afet_sender_init(s, key, 9, 0, 64, cb, None)
    py = Sender(9, key, PersistentCounter(flash, block=64))
    rng = random.Random(3)
    for _ in range(300):
        payload = os.urandom(rng.randint(0, 40))
        ref = py.seal(1, 2, PacketType.DATA, payload)
        c = Packet(0, 1, 2, PacketType.DATA.value, 0, 8, 0, len(payload))
        C.memmove(c.payload, payload, len(payload))
        cnt = C.c_uint32()
        assert L.afet_sender_seal(s, C.byref(c), C.byref(cnt)) == 0
        assert (c.src, c.seq, c.last_hop) == (ref.src, ref.seq, ref.last_hop)
        assert payload_of(c) == ref.payload and tag_of(c) == ref.tag
    assert writes_c[-1] == flash["ctr"]  # kalıcı rezerv sınırı aynı değere ulaştı
    assert len(writes_c) >= 2


def test_sender_counter_never_goes_back_after_reboot(L):
    flash = {}
    s = buf(L, "sender")
    cb = c_api.PERSIST(lambda _c, r: flash.__setitem__("ctr", r))
    L.afet_sender_init(s, KEY, 4, flash.get("ctr", 0), 64, cb, None)
    last = 0
    for _ in range(100):
        c = Packet(0, 1, 1, PacketType.DATA.value, 0, 8, 0, 0)
        cnt = C.c_uint32()
        L.afet_sender_seal(s, C.byref(c), C.byref(cnt))
        last = cnt.value
    s2 = buf(L, "sender")
    L.afet_sender_init(s2, KEY, 4, flash["ctr"], 64, cb, None)
    c = Packet(0, 1, 1, PacketType.DATA.value, 0, 8, 0, 0)
    cnt = C.c_uint32()
    L.afet_sender_seal(s2, C.byref(c), C.byref(cnt))
    assert cnt.value > last


# ---------------- alıcı: rastgele olay dizisinde Python ile aynı karar ----------------
def run_differential(L, rng, steps):
    key = os.urandom(16)
    t = [0]
    py = Receiver(key, clock=lambda: float(t[0]))
    rx = buf(L, "receiver")
    L.afet_receiver_init(rx, key)
    senders = {n: Sender(n, key, PersistentCounter({}, block=64)) for n in (2, 3, 4)}
    clone = Sender(3, key, PersistentCounter({}, block=64))
    pool, held, mism = [], [], []
    for step in range(steps):
        t[0] += rng.choice([0, 1, 1, 2, 5, 20, 45])
        r = rng.random()
        if r < 0.45 or not pool:
            n = rng.choice(list(senders))
            f = senders[n].seal(1, 1, rng.choice([PacketType.DATA, PacketType.HELLO]), os.urandom(rng.randint(0, 20)))
            if rng.random() < 0.15:
                held.append(f)
                continue
            pkt = f
            pool.append(f)
        elif r < 0.6:
            pkt = rng.choice(pool)
        elif r < 0.7 and held:
            pkt = held.pop(rng.randrange(len(held)))
        elif r < 0.78:
            f = rng.choice(pool)
            pkt = replace(f, payload=bytes([f.payload[0] ^ 1]) + f.payload[1:]) if f.payload else replace(f, tag=os.urandom(4))
        elif r < 0.84:
            pkt = replace(rng.choice(pool), tag=os.urandom(4))
        elif r < 0.92:
            pkt = clone.seal(1, 1, PacketType.DATA, b"klon")
        elif r < 0.96:
            pkt = replace(rng.choice(pool), ttl=1, next_hop=9)
        else:
            far = Sender(2, key, PersistentCounter({"ctr": rng.choice([3000, 70000, 10 ** 6])}, block=64))
            pkt = far.seal(1, 1, PacketType.DATA, b"ileri")
        n_alarm = len(py.alarms)
        st_py, data_py = py.open(pkt)
        st_c, c, alarm_c = open_c(L, rx, pkt, t[0] * 1000)
        good = st_c == st_py and alarm_c == (len(py.alarms) > n_alarm)
        if good and st_py == "ok":
            good = payload_of(c) == data_py
        if not good:
            mism.append((step, st_py, st_c))
    return mism


def test_receiver_differential_vs_python(L):
    for seed in range(15):
        assert run_differential(L, random.Random(seed), 500) == []


def test_receiver_alarm_once_like_python(L):
    t = [0]
    py = Receiver(KEY, clock=lambda: float(t[0]))
    rx = buf(L, "receiver")
    L.afet_receiver_init(rx, KEY)
    good, clone = Sender(5, KEY, PersistentCounter({}, block=64)), Sender(5, KEY, PersistentCounter({}, block=64))
    for _ in range(250):
        pkt = good.seal(1, 1, PacketType.DATA, b"x")
        py.open(pkt)
        open_c(L, rx, pkt, 0)
    alarms_c = 0
    for _ in range(8):
        t[0] += 1
        pkt = clone.seal(1, 1, PacketType.DATA, b"klon")
        py.open(pkt)
        alarms_c += open_c(L, rx, pkt, t[0] * 1000)[2]
    assert alarms_c == 1 == len(py.alarms)


def test_forged_frames_do_not_fill_peer_table(L):
    rx = buf(L, "receiver")
    L.afet_receiver_init(rx, KEY)
    forged = Sender(7, os.urandom(16)).seal(1, 1, PacketType.DATA, b"x")
    for src in range(1, 60):
        assert open_c(L, rx, replace(forged, src=src), 0)[0] == "bad_tag"
    assert open_c(L, rx, Sender(8, KEY).seal(1, 1, PacketType.DATA, b"x"), 0)[0] == "ok"


# ---------------- yönlendirme tablosu ----------------
def test_seq_and_link_cost_match(L):
    rng = random.Random(4)
    for _ in range(2000):
        a, b = rng.randrange(65536), rng.randrange(65536)
        assert bool(L.afet_seq_newer(a, b)) == seq_newer(a, b)
    for r in [-130, -123, -119.9, -118.0, -117.9, -110.0, -109.9, -90]:
        assert L.afet_link_cost(r) == link_cost(r)


def route_c(L, t):
    v, nh, m, s, sw = C.c_uint8(), C.c_uint8(), C.c_uint16(), C.c_uint16(), C.c_uint32()
    L.afet_routing_get(t, C.byref(v), C.byref(nh), C.byref(m), C.byref(s), C.byref(sw))
    return ((nh.value, m.value, s.value) if v.value else None), sw.value


def test_routing_differential_vs_python(L):
    for seed in range(30):
        rng = random.Random(seed)
        py = RoutingTable(me=1, timeout=15.0)
        t = buf(L, "routing")
        L.afet_routing_init(t, 1, 15000)
        now = 0
        for step in range(300):
            now += rng.choice([0, 1, 2, 5, 9, 16])
            op = rng.random()
            nb = rng.randint(2, 7)
            if op < 0.7:
                seq = rng.randrange(65500, 65536) if rng.random() < 0.3 else rng.randrange(0, 40)
                met, nh = rng.randint(0, 8), rng.choice([0, 1, 2, 3, 9])
                rssi = rng.choice([-125, -119, -118, -112, -110, -100, -90]) + 0.25
                ch_py = py.update(nb, seq, met, nh, rssi, float(now))
                ch_c = L.afet_routing_update(t, nb, seq, met, nh, rssi, now * 1000)
            elif op < 0.85:
                ch_py = py.remove_neighbor(nb, float(now))
                ch_c = L.afet_routing_remove_neighbor(t, nb, now * 1000)
            else:
                ch_py = py.select(float(now))
                ch_c = L.afet_routing_select(t, now * 1000)
            cur = py.route
            expected = (cur.next_hop, cur.metric, cur.gw_seq) if cur else None
            got, switches = route_c(L, t)
            assert got == expected, (seed, step)
            assert bool(ch_c) == bool(ch_py), (seed, step)
            assert switches == py.switches, (seed, step)


# ---------------- airtime ve duty cycle ----------------
def test_airtime_matches_python(L):
    for sf in range(7, 13):
        for bw in (125000, 250000, 500000):
            for pl in (0, 1, 13, 20, 51, 64, 100, 255):
                for cr in (1, 4):
                    assert L.afet_lora_airtime(pl, sf, bw, cr, 8, 1, 0) == pytest.approx(airtime(pl, sf, bw, cr), abs=1e-12)


def test_duty_cycle_matches_python(L):
    rng = random.Random(5)
    py = DutyCycle()
    d = buf(L, "duty")
    L.afet_duty_init(d, 3600000, 10000)
    t_ms, sent = 0, 0
    for _ in range(4000):
        t_ms += rng.choice([20, 50, 100, 900, 2000, 7000])
        dur_us = int(airtime(rng.choice([13, 20, 40]), 7) * 1e6)
        ok_py = py.can_send(t_ms / 1000, dur_us / 1e6)
        assert ok_py == bool(L.afet_duty_can_send(d, t_ms, dur_us)), t_ms
        if ok_py:
            py.record(t_ms / 1000, dur_us / 1e6)
            assert L.afet_duty_record(d, t_ms, dur_us) == 1
            sent += 1
    assert sent > 100
    assert L.afet_duty_used_us(d, t_ms) / 1e6 == pytest.approx(py.used(t_ms / 1000), abs=1e-3)
