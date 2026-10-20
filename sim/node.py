import random

from sim.routing import RoutingTable, encode_hello, decode_hello, seq_newer, SEQ_MOD
from sim.neighbor import NeighborTable
from sim.packet import Packet, PacketType, BROADCAST


class MeshNode:
    def __init__(self, node, sim, radio, hello_period=5.0, timeout=15.0, seed=0):
        self.node = node
        self.sim = sim
        self.radio = radio
        self.hello_period = hello_period
        self.table = NeighborTable(timeout)
        self.seq = 0
        self.routes = RoutingTable()
        self.gw_seq = 0
        self.rng = random.Random(seed + node.node_id)
        radio.attach(node.node_id, self.on_receive)

    def start(self):
        self.sim.schedule(self.rng.uniform(0.0, self.hello_period), self.send_hello)

    def send_hello(self):
        self.table.expire(self.sim.now)
        self.seq += 1
        if self.node.is_gateway:
            self.gw_seq = (self.gw_seq + 1) % SEQ_MOD
            payload = encode_hello(self.gw_seq, 0)
        elif self.routes.route is not None:
            r = self.routes.route
            payload = encode_hello(r.gw_seq, r.metric)
        else:
            payload = b""
        hello = Packet(self.node.node_id, BROADCAST, BROADCAST, PacketType.HELLO, self.seq, 1, payload)
        self.radio.transmit(self.node, hello)
        self.sim.schedule(self.hello_period, self.send_hello)


    def on_receive(self, packet, rssi):
        if packet.ptype == PacketType.HELLO:
            self.table.update(packet.src, rssi, self.sim.now)
            if packet.payload and not self.node.is_gateway:
                gw_seq, metric = decode_hello(packet.payload)
                self.routes.update(packet.src, gw_seq, metric, rssi, self.sim.now)



if __name__ == "__main__":
    from sim.engine import Simulator
    from sim.mesh_sim import Node
    from sim.radio import Radio

    sim = Simulator()
    nodes = [Node(i + 1, 700.0 * i, 0.0, is_gateway=(i == 0)) for i in range(4)]
    radio = Radio(sim, nodes)
    mesh = [MeshNode(n, sim, radio) for n in nodes]
    for m in mesh:
        m.start()
    sim.run(until=40)

    for m in mesh:
        print(m.node.node_id, m.table.ids(), m.routes.route)

