import struct

from dataclasses import dataclass

INFINITY = 255
HELLO_FORMAT = ">HBB"
SEQ_MOD = 65536


def encode_hello(gw_seq, metric, next_hop):
    return struct.pack(HELLO_FORMAT, gw_seq, metric, next_hop)


def decode_hello(payload):
    return struct.unpack(HELLO_FORMAT, payload)


def seq_newer(a, b):
    return 0 < (a - b) % SEQ_MOD < SEQ_MOD // 2


def link_cost(rssi):
    if rssi >= -110.0:
        return 1
    if rssi >= -118.0:
        return 2
    return 3


@dataclass
class Route:
    next_hop: int
    metric: int
    gw_seq: int
    updated: float


@dataclass
class Candidate:
    gw_seq: int
    metric: int
    updated: float


class RoutingTable:
    def __init__(self, me=0, timeout=15.0):
        self.me = me
        self.timeout = timeout
        self.cands = {}
        self.route = None
        self.switches = 0

    def update(self, neighbor_id, adv_seq, adv_metric, adv_next_hop, rssi, now):
        metric = adv_metric + link_cost(rssi)
        if adv_next_hop == self.me or metric >= INFINITY:
            self.cands.pop(neighbor_id, None)
        else:
            old = self.cands.get(neighbor_id)
            if old is None or not seq_newer(old.gw_seq, adv_seq):
                self.cands[neighbor_id] = Candidate(adv_seq, metric, now)
        return self.select(now)

    def remove_neighbor(self, neighbor_id, now):
        self.cands.pop(neighbor_id, None)
        return self.select(now)

    def select(self, now):
        self.cands = {n: c for n, c in self.cands.items() if now - c.updated <= self.timeout}
        cur = self.route
        if not self.cands:
            self.route = None
            return cur is not None
        best = min(self.cands, key=lambda n: (self.cands[n].metric, n))
        if cur is not None and cur.next_hop in self.cands \
                and self.cands[best].metric >= self.cands[cur.next_hop].metric:
            best = cur.next_hop
        c = self.cands[best]
        changed = cur is None or cur.next_hop != best or cur.metric != c.metric
        if cur is not None and cur.next_hop != best:
            self.switches += 1
        self.route = Route(best, c.metric, c.gw_seq, c.updated)
        return changed


if __name__ == "__main__":
    rt = RoutingTable(me=1, timeout=15.0)
    print(rt.route)
    print(rt.update(3, 5, 1, 9, -110.0, 10.0), rt.route)
    print(rt.update(2, 5, 3, 9, -100.0, 11.0), rt.route.next_hop)
    print(rt.update(2, 5, 0, 9, -100.0, 12.0), rt.route.next_hop, rt.switches)
    print(rt.update(5, 6, 0, 1, -100.0, 13.0), 5 in rt.cands)
    print(rt.remove_neighbor(2, 14.0), rt.route.next_hop)
    print(rt.remove_neighbor(3, 14.5), rt.route)
    rt.update(4, 7, 0, 9, -100.0, 20.0)
    print(rt.select(34.0), rt.select(36.0), rt.route)
    print(seq_newer(0, 65535), seq_newer(65535, 0))
