import heapq

from dataclasses import dataclass, field
from typing import Callable

@dataclass(order=True)
class Event:
    time: float
    seq: int
    action: Callable = field(compare=False)

class Simulator:
    def __init__(self):
        self.now = 0.0
        self._queue = []
        self._seq = 0

    def schedule(self, delay, action):
        self._seq += 1
        heapq.heappush(self._queue, Event(self.now + delay, self._seq, action))

    def run(self, until):
        while self._queue and self._queue[0].time <= until:
            event = heapq.heappop(self._queue)
            self.now = event.time
            event.action()


if __name__ == "__main__":
    sim = Simulator()

    def hello(node_id):
        print(f"t={sim.now:.1f}: düğüm {node_id} HELLO gönderdi")
        sim.schedule(5.0, lambda: hello(node_id))

    sim.schedule(0.0, lambda: hello(1))
    sim.schedule(1.0, lambda: hello(2))
    sim.run(until=30)
