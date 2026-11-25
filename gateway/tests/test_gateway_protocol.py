from gateway.receiver.db import Database
from gateway.receiver.report import KIND_STATUS, encode_report
from gateway.receiver.service import Gateway
from sim.packet import PacketType
from sim.routing import decode_hello
from sim.security import PersistentCounter, Receiver, Sender
from sim.wire import decode, encode

KEY = bytes(range(16))  # yalnızca test anahtarı


def data_frame(node):
    return encode(node.seal(1, 1, PacketType.DATA, encode_report(KIND_STATUS, 1, 2, 80, 0, "x")))


def test_ack_payload_matches_firmware_format():
    gw = Gateway(Database(), KEY)
    node = Sender(5, KEY, PersistentCounter({}, block=64))
    pkt = node.seal(1, 1, PacketType.DATA, encode_report(KIND_STATUS, 1, 2, 80, 0, "x"))
    acks = gw.on_frame(encode(pkt))
    ack = decode(acks[0])
    status, payload = Receiver(KEY).open(ack)
    assert status == "ok" and ack.ptype == PacketType.ACK and ack.next_hop == pkt.last_hop
    assert payload == bytes([5, (pkt.seq >> 8) & 0xFF, pkt.seq & 0xFF])


def test_hello_is_sealed_and_sequence_survives_restart(tmp_path):
    path = str(tmp_path / "gw.db")
    rx = Receiver(KEY)
    gw = Gateway(Database(path), KEY)
    seqs = []
    for _ in range(3):
        h = decode(gw.hello_frame())
        status, payload = rx.open(h)
        assert status == "ok" and h.ptype == PacketType.HELLO and h.ttl == 1
        seqs.append(decode_hello(payload))
    assert seqs == [(1, 0, 0), (2, 0, 0), (3, 0, 0)]
    gw.close()
    gw2 = Gateway(Database(path), KEY)
    status, payload = rx.open(decode(gw2.hello_frame()))
    assert status == "ok" and decode_hello(payload)[0] == 4   # geri dönmedi: düğümler yeni ilanı kabul eder
