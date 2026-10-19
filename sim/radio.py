from functools import partial

from sim.lora import airtime
from sim.mesh_sim import can_hear, rssi


class Radio:
    def __init__(self, sim, nodes, sf=7):
        self.sim = sim
        self.nodes = nodes
        self.sf = sf
        self._handlers = {}

    def attach(self, node_id, handler):
        self._handlers[node_id] = handler

    def transmit(self, tx, packet):
        t = airtime(packet.size(), self.sf)
        for rx in self.nodes:
            if rx.node_id != tx.node_id and can_hear(tx, rx):
                self.sim.schedule(t, partial(self._deliver, rx.node_id, packet, rssi(tx, rx)))
        return t

    def _deliver(self, rx_id, packet, rx_rssi):
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
