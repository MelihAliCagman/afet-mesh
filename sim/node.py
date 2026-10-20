import random

from sim.routing import RoutingTable, encode_hello, decode_hello, SEQ_MOD
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


def route_path(mesh, start):
    by_id = {m.node.node_id: m for m in mesh}
    path = [start]
    while True:
        m = by_id[path[-1]]
        if m.node.is_gateway:
            return path, "tamam"
        r = m.routes.route
        if r is None:
            return path, "yol yok"
        if r.next_hop in path:
            return path + [r.next_hop], "DÖNGÜ"
        path.append(r.next_hop)


if __name__ == "__main__":
    from sim.engine import Simulator
    from sim.mesh_sim import Node
    from sim.radio import Radio

    def build_mesh(positions, seed=0):
        sim = Simulator()
        nodes = [Node(i + 1, x, y, is_gateway=(i == 0)) for i, (x, y) in enumerate(positions)]
        radio = Radio(sim, nodes)
        mesh = [MeshNode(n, sim, radio, seed=seed) for n in nodes]
        for m in mesh:
            m.start()
        return sim, mesh

    def run_demo(title, positions, until):
        sim, mesh = build_mesh(positions)
        sim.run(until=until)
        print("==", title)
        for m in mesh:
            r = m.routes.route
            path, durum = route_path(mesh, m.node.node_id)
            print(m.node.node_id, "yol:", " -> ".join(map(str, path)), f"({durum})",
                  "maliyet", None if r is None else r.metric, "| hop değişimi", m.routes.switches)

    def loop_scan(positions, until, seeds):
        total = 0
        bad = 0
        for seed in range(seeds):
            sim, mesh = build_mesh(positions, seed)
            sim.run(until=until)
            for m in mesh:
                if m.node.is_gateway:
                    continue
                total += 1
                if route_path(mesh, m.node.node_id)[1] != "tamam":
                    bad += 1
        print(f"== D: döngü taraması: {seeds} tohum, {total} yol, sorunlu {bad}")

    grid = [(x * 500.0, y * 500.0) for y in range(3) for x in range(3)]
    run_demo("A: 400 m zincir", [(0, 0), (400, 0), (800, 0), (1200, 0)], 60)
    run_demo("B: 3 düğüm", [(0, 0), (200, 0), (400, 0)], 40)
    run_demo("C: 3x3 ızgara", grid, 80)
    loop_scan(grid, 80, 12)

