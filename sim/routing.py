import struct

from dataclasses import dataclass

INFINITY = 255
HELLO_FORMAT = ">HB"


def encode_hello(gw_seq, metric):
    return struct.pack(HELLO_FORMAT, gw_seq, metric)


def decode_hello(payload):
    return struct.unpack(HELLO_FORMAT, payload)

SEQ_MOD = 65536


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


class RoutingTable:
    def __init__(self):
        self.route = None
        self.switches = 0

    def update(self, neighbor_id, adv_seq, adv_metric, rssi, now):
        metric = adv_metric + link_cost(rssi)
        r = self.route
        if metric >= INFINITY:
            if r is not None and r.next_hop == neighbor_id:
                self.route = None
                return True
            return False
        if r is None or seq_newer(adv_seq, r.gw_seq) or (adv_seq == r.gw_seq and metric < r.metric):
            if r is not None and r.next_hop != neighbor_id:
                self.switches += 1
            self.route = Route(neighbor_id, metric, adv_seq, now)
            return True
        return False


if __name__ == "__main__":
    rt = RoutingTable()
    print(rt.route)
    print(rt.update(3, 5, 1, -110.0, 10.0))
    print(rt.route)
    print(rt.update(2, 5, 3, -100.0, 11.0))
    print(rt.update(2, 5, 0, -100.0, 12.0))
    print(rt.update(4, 4, 0, -100.0, 13.0))
    print(rt.update(4, 6, 9, -120.0, 14.0))
    print(rt.route)
    print(seq_newer(0, 65535), seq_newer(65535, 0))

