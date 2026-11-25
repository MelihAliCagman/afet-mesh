import random
from functools import partial

from sim.lora import airtime
from sim.mesh_sim import can_hear, rssi


class Radio:
    def __init__(self, sim, nodes, sf=7, loss=0.0, seed=0, collide=False):
        self.sim = sim
        self.nodes = nodes
        self.sf = sf
        self._handlers = {}
        self.loss = loss
        self.rng = random.Random(seed)
        self.collide = collide
        self.on_air = []
        self.rx_live = {}
        self.collisions = 0
        self.tx_count = 0

    def attach(self, node_id, handler):
        self._handlers[node_id] = handler

    def busy(self, node):
        now = self.sim.now
        self.on_air = [(n, e) for n, e in self.on_air if e > now]
        return any(n.node_id == node.node_id or can_hear(n, node) for n, e in self.on_air)

    def transmit(self, tx, packet):
        t = airtime(packet.size(), self.sf)
        now = self.sim.now
        self.tx_count += 1
        if self.collide:
            self.on_air.append((tx, now + t))
            for r in self.rx_live.get(tx.node_id, []):
                if r["end"] > now:
                    r["bad"] = True
        for rx in self.nodes:
            if rx.node_id != tx.node_id and can_hear(tx, rx):
                if self.loss and self.rng.random() < self.loss:
                    continue
                rec = None
                if self.collide:
                    rec = {"end": now + t, "bad": False}
                    live = [r for r in self.rx_live.get(rx.node_id, []) if r["end"] > now]
                    for r in live:
                        r["bad"] = True
                        rec["bad"] = True
                    if any(n.node_id == rx.node_id and e > now for n, e in self.on_air):
                        rec["bad"] = True
                    live.append(rec)
                    self.rx_live[rx.node_id] = live
                self.sim.schedule(t, partial(self._deliver, rx.node_id, packet, rssi(tx, rx), rec))
        return t

    def _deliver(self, rx_id, packet, rx_rssi, rec=None):
        if rec is not None and rec["bad"]:
            self.collisions += 1
            return
        handler = self._handlers.get(rx_id)
        if handler:
            handler(packet, rx_rssi)


if __name__ == "__main__":
    from sim.engine import Simulator
    from sim.mesh_sim import Node
    from sim.packet import Packet, PacketType, BROADCAST

    sim = Simulator()
    nodes = [Node(1, 0.0, 0.0), Node(2, 700.0, 0.0), Node(3, 1400.0, 0.0)]
    radio = Radio(sim, nodes)

    def make_handler(node_id):
        def handler(packet, rx_rssi):
            print(f"t={sim.now:.6f}: düğüm {node_id} aldı, kaynak={packet.src}, RSSI={rx_rssi:.1f}")
        return handler

    for n in nodes:
        radio.attach(n.node_id, make_handler(n.node_id))

    p = Packet(1, BROADCAST, BROADCAST, PacketType.HELLO, seq=1, ttl=1)

    sim.schedule(1.0, lambda: radio.transmit(nodes[0], p))

    sim.run(until=5)


    print("== Çarpışma denemesi: 1 ve 3 birbirini duymaz, ikisi de 2'ye aynı anda yollar")
    for collide in (False, True):
        sim = Simulator()
        nodes = [Node(1, 0.0, 0.0), Node(2, 700.0, 0.0), Node(3, 1400.0, 0.0)]
        radio = Radio(sim, nodes, collide=collide)
        alinan = []
        radio.attach(2, lambda pk, rs: alinan.append(pk.src))
        for n in (nodes[0], nodes[2]):
            pk = Packet(n.node_id, BROADCAST, BROADCAST, PacketType.HELLO, seq=1, ttl=1)
            sim.schedule(1.0, lambda n=n, pk=pk: radio.transmit(n, pk))
        sim.run(until=5)
        print("çarpışma modeli", "AÇIK " if collide else "KAPALI", "| düğüm 2'nin aldığı:", alinan, "| çarpışan alım:", radio.collisions)
