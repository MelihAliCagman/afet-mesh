from dataclasses import dataclass
from enum import Enum


class PacketType(Enum):
    HELLO = 1
    DATA = 2
    ACK = 3
    RERR = 4


BROADCAST = 255
HEADER_BYTES = 7
TAG_BYTES = 4


@dataclass
class Packet:
    src: int
    dst: int
    next_hop: int
    ptype: PacketType
    seq: int
    ttl: int
    payload: bytes = b""

    def size(self) -> int:
        return HEADER_BYTES + len(self.payload) + TAG_BYTES


if __name__ == "__main__":
    from sim.lora import airtime

    p = Packet(1, BROADCAST, BROADCAST, PacketType.HELLO, seq=1, ttl=1, payload=b"\x00\x01")
    print(p)
    print(p.size())
    print(round(airtime(p.size(), 7), 6))
