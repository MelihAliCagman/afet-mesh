"""C düğümleri (firmware/core) ile Python gateway servisinin (gateway/receiver) uçtan uca birlikte çalışması."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import c_api  # noqa: E402
import c_mesh  # noqa: E402
from c_mesh import CNode  # noqa: E402

from gateway.receiver.db import Database  # noqa: E402
from gateway.receiver.report import KIND_STATUS, encode_report  # noqa: E402
from gateway.receiver.service import Gateway  # noqa: E402
from sim.engine import Simulator  # noqa: E402
from sim.mesh_sim import Node  # noqa: E402
from sim.radio import Radio  # noqa: E402
from sim.wire import decode, encode  # noqa: E402

KEY = bytes(range(16))  # yalnızca test anahtarı
CHAIN = [(0, 0), (400, 0), (800, 0), (1200, 0)]


@pytest.fixture(scope="module")
def L(lib):
    c_api.setup(lib)
    return c_mesh.setup_node_api(lib)


class GatewayAdapter:
    """Python gateway servisini simülasyon radyosuna bağlar: gelen kareyi servise verir, ACK ve HELLO yayınlar."""

    def __init__(self, sim, radio, node, db, key, persist=True, hello_period=5.0):
        self.sim, self.radio, self.node, self.db, self.key, self.persist = sim, radio, node, db, key, persist
        self.hello_period = hello_period
        self.gw = Gateway(db, key, clock=lambda: sim.now, persist=persist)
        radio.attach(node.node_id, self.on_air)
        sim.schedule(0.5, self.hello)

    def restart(self):
        self.gw.close()
        self.gw = Gateway(self.db, self.key, clock=lambda: self.sim.now, persist=self.persist)

    def on_air(self, packet, rssi):
        for ack in self.gw.on_frame(encode(packet), rssi):
            self.radio.transmit(self.node, decode(ack))

    def hello(self):
        self.radio.transmit(self.node, decode(self.gw.hello_frame()))
        self.sim.schedule(self.hello_period, self.hello)


def build(L, seed, persist=True):
    sim = Simulator()
    nodes = [Node(i + 1, x, y, is_gateway=(i == 0)) for i, (x, y) in enumerate(CHAIN)]
    radio = Radio(sim, nodes, seed=seed)
    db = Database()
    gw = GatewayAdapter(sim, radio, nodes[0], db, KEY, persist=persist)
    cnodes = [CNode(L, n, sim, radio, KEY, seed) for n in nodes[1:]]
    return sim, db, gw, cnodes


def send_reports(sim, cnodes, count, period=3.0):
    for i in range(count):
        for k, c in enumerate(cnodes):
            sim.schedule(i * period + k * 0.7, lambda c=c, i=i: c.send_data(encode_report(KIND_STATUS, c.id * 10, 0, 90, 0, f"r{i}")))


def test_c_nodes_learn_routes_from_python_gateway_hello(L):
    sim, db, gw, cnodes = build(L, 1)
    sim.run(until=40)
    assert [c.info()["route"] is not None for c in cnodes] == [True, True, True]
    assert cnodes[0].info()["route"][0] == 1          # düğüm 2, gateway'e doğrudan
    assert cnodes[2].info()["route"][0] == 3          # düğüm 4, düğüm 3 üzerinden
    assert db.nodes()  # HELLO'lar gateway'e ulaştı


def test_reports_reach_gateway_db_and_acks_stop_retries(L):
    sim, db, gw, cnodes = build(L, 2)
    sim.run(until=40)
    send_reports(sim, cnodes, 8)
    sim.run(until=sim.now + 60)
    assert db.message_count() == 24
    assert {m["src"] for m in db.messages(100)} == {2, 3, 4}
    assert db.alarms() == []
    assert all(c.info()["stats"].retx == 0 for c in cnodes)   # ACK'ler C tarafından tanındı
    assert all(c.info()["stats"].drop_security == 0 for c in cnodes)


def retries_after_gateway_restart(L, persist):
    sim, db, gw, cnodes = build(L, 3, persist=persist)
    sim.run(until=40)
    send_reports(sim, cnodes, 6)
    sim.run(until=sim.now + 25)
    gw.restart()
    before = sum(c.info()["stats"].retx for c in cnodes)
    send_reports(sim, cnodes, 6)
    sim.run(until=sim.now + 60)
    return sum(c.info()["stats"].retx for c in cnodes) - before, db.message_count()


def test_gateway_restart_with_persistent_counters_keeps_acks_valid(L):
    retx, n = retries_after_gateway_restart(L, persist=True)
    assert n == 36 and retx == 0


def test_gateway_restart_without_persistence_breaks_acks(L):
    retx, _ = retries_after_gateway_restart(L, persist=False)
    assert retx > 5      # ACK ve HELLO sayacı geri döndüğü için düğümler yanıtları reddeder, boşuna yeniden dener
