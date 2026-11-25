import random
from dataclasses import replace

from sim.routing import RoutingTable, encode_hello, decode_hello, SEQ_MOD
from sim.neighbor import NeighborTable
from sim.packet import Packet, PacketType, BROADCAST


DATA_TTL = 8
SEEN_LIMIT = 256
BACKOFF_SLOT = 0.05
MAX_BACKOFF = 6


class MeshNode:
    def __init__(self, node, sim, radio, hello_period=5.0, timeout=15.0, seed=0, max_retry=3, ack_timeout=1.0, csma=False,
                 fast_detect=True, rerr_on=True):
        self.node = node
        self.sim = sim
        self.radio = radio
        self.hello_period = hello_period
        self.table = NeighborTable(timeout)
        self.seq = 0
        self.routes = RoutingTable(node.node_id, timeout)
        self.fast_detect = fast_detect
        self.rerr_on = rerr_on
        self.alive = True
        self.sent_at = {}
        self.tap = None
        self.gw_seq = 0
        self.csma = csma
        self.backoffs = 0
        self.max_retry = max_retry
        self.ack_timeout = ack_timeout
        self.pending = {}
        self.acked = 0
        self.retx = 0
        self.data_seq = 0
        self.seen = []
        self.delivered = []
        self.dropped = {"ttl": 0, "dup": 0, "no_route": 0, "retry": 0}
        self.rng = random.Random(seed + node.node_id)
        radio.attach(node.node_id, self.on_receive)

    def start(self):
        self.sim.schedule(self.rng.uniform(0.0, self.hello_period), self.send_hello)

    def kill(self):
        self.alive = False

    def route_lost(self, had_route):
        if had_route and self.routes.route is None and self.rerr_on:
            self.seq += 1
            rerr = Packet(self.node.node_id, BROADCAST, BROADCAST, PacketType.RERR,
                          self.seq, 1, b"", self.node.node_id)
            self.mac_send(rerr)

    def link_failed(self, neighbor_id):
        had = self.routes.route is not None
        self.routes.remove_neighbor(neighbor_id, self.sim.now)
        self.route_lost(had)

    def send_hello(self):
        if not self.alive:
            return
        had = self.routes.route is not None
        self.routes.select(self.sim.now)
        self.route_lost(had)
        self.table.expire(self.sim.now)
        self.seq += 1
        if self.node.is_gateway:
            self.gw_seq = (self.gw_seq + 1) % SEQ_MOD
            payload = encode_hello(self.gw_seq, 0, 0)
        elif self.routes.route is not None:
            r = self.routes.route
            payload = encode_hello(r.gw_seq, r.metric, r.next_hop)
        else:
            payload = b""
        hello = Packet(self.node.node_id, BROADCAST, BROADCAST, PacketType.HELLO, self.seq, 1, payload)
        self.mac_send(hello)
        self.sim.schedule(self.hello_period, self.send_hello)

    def send_data(self, payload, gateway_id=1):
        r = self.routes.route
        if r is None:
            self.dropped["no_route"] += 1
            return False
        self.data_seq += 1
        self.sent_at[self.data_seq] = self.sim.now
        pkt = Packet(self.node.node_id, gateway_id, r.next_hop,
                     PacketType.DATA, self.data_seq, DATA_TTL, payload)
        self.mark_seen(pkt)
        self.tx_data(pkt)
        return True

    def mark_seen(self, pkt):
        self.seen.append((pkt.src, pkt.seq))
        if len(self.seen) > SEEN_LIMIT:
            self.seen.pop(0)

    def on_data(self, pkt):
        if pkt.next_hop != self.node.node_id:
            return
        self.send_ack(pkt)
        if (pkt.src, pkt.seq) in self.seen:
            self.dropped["dup"] += 1
            return
        self.mark_seen(pkt)
        if self.node.is_gateway:
            self.delivered.append((pkt.src, pkt.seq, self.sim.now))
            return
        if pkt.ttl <= 1:
            self.dropped["ttl"] += 1
            return
        r = self.routes.route
        if r is None:
            self.dropped["no_route"] += 1
            return
        self.tx_data(replace(pkt, next_hop=r.next_hop, ttl=pkt.ttl - 1))

    def mac_send(self, pkt, attempt=0):
        if not self.alive:
            return
        if self.csma and attempt < MAX_BACKOFF and self.radio.busy(self.node):
            self.backoffs += 1
            window = BACKOFF_SLOT * (2 ** min(attempt + 1, 5))
            self.sim.schedule(self.rng.uniform(0.0, window), lambda: self.mac_send(pkt, attempt + 1))
            return
        self.radio.transmit(self.node, pkt)

    def tx_data(self, pkt, tries=0):
        pkt = replace(pkt, last_hop=self.node.node_id)
        key = (pkt.src, pkt.seq)
        self.pending[key] = (pkt, tries)
        self.mac_send(pkt)
        self.sim.schedule(self.ack_timeout, lambda: self.on_timeout(key, tries))

    def on_timeout(self, key, tries):
        entry = self.pending.get(key)
        if not self.alive:
            return
        if entry is None or entry[1] != tries:
            return
        pkt = entry[0]
        if tries >= self.max_retry:
            del self.pending[key]
            self.dropped["retry"] += 1
            if self.fast_detect:
                self.link_failed(pkt.next_hop)
            return
        r = self.routes.route
        if r is None:
            del self.pending[key]
            self.dropped["no_route"] += 1
            return
        self.retx += 1
        self.tx_data(replace(pkt, next_hop=r.next_hop), tries + 1)

    def send_ack(self, pkt):
        ack = Packet(self.node.node_id, pkt.last_hop, pkt.last_hop, PacketType.ACK,
                     pkt.seq, 1, bytes([pkt.src]), self.node.node_id)
        self.mac_send(ack)

    def on_ack(self, pkt):
        if pkt.next_hop != self.node.node_id:
            return
        if self.pending.pop((pkt.payload[0], pkt.seq), None) is not None:
            self.acked += 1

    def on_receive(self, packet, rssi):
        if not self.alive:
            return
        if self.tap is not None:
            self.tap(packet, rssi)
        if packet.ptype == PacketType.HELLO:
            self.table.update(packet.src, rssi, self.sim.now)
            if packet.payload and not self.node.is_gateway:
                gw_seq, metric, next_hop = decode_hello(packet.payload)
                had = self.routes.route is not None
                self.routes.update(packet.src, gw_seq, metric, next_hop, rssi, self.sim.now)
                self.route_lost(had)
        elif packet.ptype == PacketType.RERR:
            if not self.node.is_gateway:
                self.link_failed(packet.src)
        elif packet.ptype == PacketType.DATA:
            self.on_data(packet)
        elif packet.ptype == PacketType.ACK:
            self.on_ack(packet)


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

    def build_mesh(positions, seed=0, loss=0.0, max_retry=3, collide=False, csma=False,
                   fast_detect=True, rerr_on=True):
        sim = Simulator()
        nodes = [Node(i + 1, x, y, is_gateway=(i == 0)) for i, (x, y) in enumerate(positions)]
        radio = Radio(sim, nodes, loss=loss, seed=seed, collide=collide)
        mesh = [MeshNode(n, sim, radio, seed=seed, max_retry=max_retry, csma=csma,
                           fast_detect=fast_detect, rerr_on=rerr_on) for n in nodes]
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


    def data_demo(title, positions, until=60, count=10):
        sim, mesh = build_mesh(positions)
        sim.run(until=30)
        sender = mesh[-1]
        for i in range(count):
            sim.schedule(i * 2.0, lambda: sender.send_data(b"x"))
        sim.run(until=until)
        gw = mesh[0]
        print("==", title, "| gönderilen:", sender.data_seq, "ulaşan:", len(gw.delivered))
        print("   atılanlar (gönderen):", sender.dropped, "| ara düğümler:", [m.dropped for m in mesh[1:-1]])

    data_demo("E: 400 m zincirde veri", [(0, 0), (400, 0), (800, 0), (1200, 0)])

    def ack_demo(loss, max_retry, seeds=10, count=20):
        sent = got = retx = dups = 0
        for seed in range(seeds):
            sim, mesh = build_mesh([(0, 0), (400, 0), (800, 0), (1200, 0)], seed, loss, max_retry)
            sim.run(until=60)
            sender = mesh[-1]
            before = sender.data_seq
            for i in range(count):
                sim.schedule(i * 2.0, lambda: sender.send_data(b"x"))
            sim.run(until=60 + count * 2 + 20)
            sent += count
            got += len(mesh[0].delivered)
            retx += sum(m.retx for m in mesh)
            dups += sum(m.dropped["dup"] for m in mesh)
        print(f"kayıp %{int(loss*100):>2} | yeniden deneme {max_retry} | PDR %{100*got/sent:5.1f} | "
              f"yeniden gönderim {retx:4d} | bastırılan çift {dups:3d}")

    print("== F: hop-hop ACK, 400 m zincir, 10 tohum x 20 paket")
    for loss in (0.0, 0.2, 0.4):
        for retry in (0, 3):
            ack_demo(loss, retry)

    def mac_demo(collide, csma, max_retry, seeds=8, count=10):
        grid = [(x * 500.0, y * 500.0) for y in range(3) for x in range(3)]
        sent = got = retx = back = col = giveup = 0
        for seed in range(seeds):
            sim, mesh = build_mesh(grid, seed, 0.0, max_retry, collide, csma)
            sim.run(until=60)
            rng = random.Random(seed)
            for m in mesh[1:]:
                off = rng.uniform(0.0, 4.0)
                for i in range(count):
                    sim.schedule(off + i * 4.0, lambda m=m: m.send_data(b"x"))
            sim.run(until=60 + count * 4 + 30)
            sent += count * 8
            got += len(mesh[0].delivered)
            retx += sum(m.retx for m in mesh)
            back += sum(m.backoffs for m in mesh)
            giveup += sum(m.dropped["retry"] for m in mesh)
            col += mesh[0].radio.collisions
        print(f"çarpışma {'var ' if collide else 'yok'} | CSMA {'var ' if csma else 'yok'} | deneme {max_retry} | "
              f"PDR %{100*got/sent:5.1f} | çarpışan alım {col:5d} | backoff {back:5d} | yeniden gönderim {retx:5d} | vazgeçilen {giveup:3d}")

    print("== G: 3x3 ızgara, 8 düğüm eşzamanlı veri (4 sn arayla 10 paket), 8 tohum")
    mac_demo(False, False, 3)
    mac_demo(True, False, 0)
    mac_demo(True, False, 3)
    mac_demo(True, True, 0)
    mac_demo(True, True, 3)

    def heal_demo(positions, sender_id, fast_detect, rerr_on, seeds=10):
        rec, post_sent, post_got, failed = [], 0, 0, 0
        for seed in range(seeds):
            sim, mesh = build_mesh(positions, seed, 0.0, 3, True, True, fast_detect, rerr_on)
            sim.run(until=60)
            t0 = sim.now
            sender = mesh[sender_id - 1]
            path, _ = route_path(mesh, sender_id)
            victim = next(m for m in mesh if m.node.node_id == path[-2])
            fail_t = t0 + 30.0
            for i in range(90):
                sim.schedule(i * 1.0, lambda: sender.send_data(b"x"))
            sim.schedule(30.0, victim.kill)
            sim.run(until=t0 + 120)
            got = {seq: t for src, seq, t in mesh[0].delivered if src == sender_id}
            after = [q for q, t in sender.sent_at.items() if t >= fail_t]
            ok = [q for q in after if q in got]
            post_sent += len(after)
            post_got += len(ok)
            if ok:
                rec.append(min(got[q] for q in ok) - fail_t)
            else:
                failed += 1
        r = sorted(rec)
        print(f"ACK hatası {'var' if fast_detect else 'yok'} | RERR {'var' if rerr_on else 'yok'} | "
              f"iyileşme ort {sum(r)/len(r):5.1f} sn, en kötü {r[-1]:5.1f} sn | "
              f"arıza sonrası PDR %{100*post_got/post_sent:5.1f} | iyileşmeyen {failed}")

    grid = [(x * 500.0, y * 500.0) for y in range(3) for x in range(3)]
    print("== H: 3x3 ızgara, düğüm 9 saniyede 1 paket, 30. sn'de yolundaki gateway'e komşu düğüm ölür (arıza kaynağa yakın), 10 tohum")
    heal_demo(grid, 9, False, False)
    heal_demo(grid, 9, True, False)
    heal_demo(grid, 9, True, True)

    ayri = [(0, 0), (450, 450), (900, 450), (450, -450), (900, -450), (1350, 0)]
    print("== I: iki ayrık zincir (gateway-2-3-6 ve gateway-4-5-6), düğüm 6 yolundaki gateway'e komşu düğüm ölür (arıza kaynaktan uzak, ara düğümün alternatifi yok), 10 tohum")
    heal_demo(ayri, 6, False, False)
    heal_demo(ayri, 6, True, False)
    heal_demo(ayri, 6, True, True)
