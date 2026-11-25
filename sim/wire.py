import struct

from sim.packet import HEADER_BYTES, TAG_BYTES, Packet, PacketType

HEADER_FORMAT = ">BBBBHBB"


def encode(pkt):
    # Havadaki bayt dizisi: 8 bayt başlık + yük + 4 bayt etiket
    if len(pkt.tag) != TAG_BYTES:
        raise ValueError("etiket 4 bayt olmalı (paket mühürlenmemiş)")
    head = struct.pack(HEADER_FORMAT, pkt.src, pkt.dst, pkt.next_hop, pkt.ptype.value,
                       pkt.seq, pkt.ttl, pkt.last_hop)
    return head + pkt.payload + pkt.tag


def decode(raw):
    if len(raw) < HEADER_BYTES + TAG_BYTES:
        raise ValueError("paket çok kısa")
    src, dst, nh, pt, seq, ttl, last = struct.unpack(HEADER_FORMAT, raw[:HEADER_BYTES])
    try:
        ptype = PacketType(pt)
    except ValueError:
        raise ValueError(f"bilinmeyen paket türü {pt}")
    return Packet(src, dst, nh, ptype, seq, ttl, raw[HEADER_BYTES:-TAG_BYTES], last, raw[-TAG_BYTES:])


if __name__ == "__main__":
    import os

    from sim.security import Sender

    s = Sender(5, os.urandom(16))
    p = s.seal(1, 1, PacketType.DATA, b"merhaba")
    raw = encode(p)
    print(len(raw), raw.hex())
    print(decode(raw) == p)
