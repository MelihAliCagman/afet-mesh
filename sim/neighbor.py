from dataclasses import dataclass


@dataclass
class NeighborEntry:
    node_id: int
    rssi: float
    last_seen: float


class NeighborTable:
    def __init__(self, timeout):
        self.timeout = timeout
        self._entries = {}

    def update(self, node_id, rssi, now):
        self._entries[node_id] = NeighborEntry(node_id, rssi, now)

    def get(self, node_id):
        return self._entries.get(node_id)

    def ids(self):
        return sorted(self._entries)

    def expire(self, now):
        dead = [i for i, e in self._entries.items() if now - e.last_seen > self.timeout]
        for i in dead:
            del self._entries[i]
        return dead


if __name__ == "__main__":
    nt = NeighborTable(timeout=15.0)
    nt.update(2, -80.0, 0.0)
    nt.update(3, -110.0, 1.0)
    print(nt.ids())
    nt.update(2, -78.0, 10.0)
    print(nt.get(2))
    print(nt.expire(17.0))
    print(nt.ids())
