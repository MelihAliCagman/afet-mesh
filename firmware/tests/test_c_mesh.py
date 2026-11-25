import os
import statistics
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import c_mesh  # noqa: E402
from c_mesh import build_c_mesh, c_path  # noqa: E402

from sim.experiment import GRID, build  # noqa: E402
from sim.node import route_path  # noqa: E402
from sim.packet import PacketType  # noqa: E402
from sim.security import PersistentCounter, Sender  # noqa: E402
from sim.wire import decode, encode  # noqa: E402

KEY = bytes(range(16))  # yalnızca test anahtarı
CHAIN400 = [(0, 0), (400, 0), (800, 0), (1200, 0)]


@pytest.fixture(scope="module")
def L(lib):
    import c_api
    c_api.setup(lib)
    return c_mesh.setup_node_api(lib)


def test_node_state_fits_in_ram(L):
    size = L.afet_sizeof_node()
    print("afet_node_t boyutu:", size, "bayt")
    assert size < 40 * 1024  # STM32F407'de 192 KB RAM var; düğüm başına 40 KB sınırı


def test_routes_and_metrics_match_python_nodes(L):
    for positions in (CHAIN400, GRID):
        sim, mesh, _ = build_c_mesh(L, positions, 1, KEY)
        sim.run(until=80)
        psim, pmesh = build(positions, 1, collide=False, csma=False)
        psim.run(until=80)
        for cm, pm in zip(mesh[1:], pmesh[1:]):
            path, status = c_path(mesh, cm.id)
            ppath, pstatus = route_path(pmesh, pm.node.node_id)
            assert status == "tamam" and pstatus == "tamam"
            assert cm.info()["route"][1] == pm.routes.route.metric
            assert len(path) == len(ppath)


def test_data_reaches_gateway_end_to_end_with_security(L):
    sim, mesh, _ = build_c_mesh(L, CHAIN400, 2, KEY)
    sim.run(until=40)
    sender, gw = mesh[3], mesh[0]
    for i in range(10):
        sim.schedule(i * 2.0, lambda i=i: sender.send_data(b"rapor-%d" % i))
    sim.run(until=sim.now + 40)
    got = [p for s, p, c, t in gw.delivered if s == 4]
    assert got == [b"rapor-%d" % i for i in range(10)]
    assert [m.info()["stats"].acked for m in mesh[1:]] != [0, 0, 0]
    assert gw.info()["stats"].delivered == 10
    assert all(m.info()["stats"].drop_security == 0 for m in mesh)


def mean_pdr_c(L, loss, seeds, retries):
    got = sent = 0
    for seed in range(seeds):
        sim, mesh, _ = build_c_mesh(L, CHAIN400, seed, KEY, loss=loss, max_retry=retries)
        sim.run(until=60)
        for i in range(20):
            sim.schedule(i * 2.0, lambda i=i: mesh[3].send_data(b"x%d" % i))
        sim.run(until=sim.now + 60)
        got += len(mesh[0].delivered)
        sent += 20
    return 100.0 * got / sent


def mean_pdr_py(loss, seeds, retries):
    got = 0
    for seed in range(seeds):
        sim, mesh = build(CHAIN400, seed, loss=loss, collide=False, csma=False, max_retry=retries)
        sim.run(until=60)
        for i in range(20):
            sim.schedule(i * 2.0, lambda: mesh[3].send_data(b"x"))
        sim.run(until=sim.now + 60)
        got += len(mesh[0].delivered)
    return 100.0 * got / (20 * seeds)


def test_ack_and_retry_behave_like_python_under_loss(L):
    c0, p0 = mean_pdr_c(L, 0.0, 4, 3), mean_pdr_py(0.0, 4, 3)
    assert c0 == 100.0 and p0 == 100.0
    c_no, p_no = mean_pdr_c(L, 0.2, 10, 0), mean_pdr_py(0.2, 10, 0)
    c_re, p_re = mean_pdr_c(L, 0.2, 10, 3), mean_pdr_py(0.2, 10, 3)
    print(f"kayıp %20: C yeniden denemesiz {c_no:.1f}, C 3 deneme {c_re:.1f} | Python {p_no:.1f}, {p_re:.1f}")
    assert c_re > c_no + 25          # yeniden deneme C'de de büyük fark yaratır
    assert abs(c_re - p_re) < 15     # Python ile aynı düzeyde
    assert abs(c_no - p_no) < 20


def recovery_time(L, fast_detect, seed):
    sim, mesh, _ = build_c_mesh(L, GRID, seed, KEY, collide=True, csma=True, fast_detect=fast_detect)
    sim.run(until=60)
    path, status = c_path(mesh, 9)
    assert status == "tamam"
    victim = next(m for m in mesh if m.id == path[-2])
    t0 = sim.now
    fail_t = t0 + 30.0
    sender = mesh[8]
    sent_at = {}

    def send(i):
        if sender.send_data(b"%d" % i):
            sent_at[i] = sim.now

    for i in range(90):
        sim.schedule(float(i), lambda i=i: send(i))
    sim.schedule(30.0, victim.kill)
    sim.run(until=t0 + 120)
    after = {int(p): t for s, p, c, t in sender_delivered(mesh) if s == 9}
    ok = [t / 1000.0 for i, t in after.items() if i in sent_at and sent_at[i] >= fail_t]
    return (min(ok) - fail_t) if ok else None


def sender_delivered(mesh):
    return mesh[0].delivered


def test_self_healing_recovery_like_python(L):
    fast = [recovery_time(L, 1, s) for s in range(4)]
    slow = [recovery_time(L, 0, s) for s in range(4)]
    assert None not in fast and None not in slow
    print("iyileşme (C): ACK tespitiyle", [round(x, 1) for x in fast], "yalnız HELLO", [round(x, 1) for x in slow])
    assert statistics.mean(fast) < 9.0
    assert statistics.mean(slow) > 10.0
    assert statistics.mean(slow) > 2 * statistics.mean(fast)


def test_attacks_on_gateway_are_rejected(L):
    sim, mesh, radio = build_c_mesh(L, CHAIN400, 3, KEY)
    captured = []
    gw = mesh[0]
    orig = gw._on_air

    def tap(packet, rssi):
        if packet.ptype == PacketType.DATA and packet.next_hop == 1:
            captured.append(encode(packet))
        orig(packet, rssi)

    radio.attach(1, tap)
    sim.run(until=40)
    for i in range(6):
        sim.schedule(i * 3.0, lambda i=i: mesh[1].send_data(b"gercek-%d" % i))
    sim.run(until=sim.now + 30)
    n = gw.info()["stats"].delivered
    assert n == 6 and captured
    sec0 = gw.info()["stats"].drop_security

    sim.run(until=sim.now + 60)  # kopya penceresi (30 sn) geçsin
    gw.inject(captured[0])  # tekrar oynatma
    forged = Sender(2, os.urandom(16), PersistentCounter({"ctr": 900}, block=64)).seal(1, 1, PacketType.DATA, b"sahte")
    gw.inject(encode(forged))  # anahtarı bilmeyen sahtecilik
    f = decode(captured[-1])
    gw.inject(encode(replace(f, payload=bytes([f.payload[0] ^ 1]) + f.payload[1:])))  # değiştirilmiş yük
    assert gw.info()["stats"].delivered == n
    assert gw.info()["stats"].drop_security == sec0 + 3
