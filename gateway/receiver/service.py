import time

from gateway.receiver.db import Database
from gateway.receiver.report import KIND_NAMES, decode_report
from sim.packet import Packet, PacketType
from sim.security import Receiver, Sender
from sim.wire import decode, encode

GATEWAY_ID = 1


class Gateway:
    """Havadan gelen ham baytı doğrular, çözer, veritabanına yazar ve gerekirse ACK üretir."""

    def __init__(self, db, key, gw_id=GATEWAY_ID, clock=time.time):
        self.db = db
        self.gw_id = gw_id
        self.clock = clock
        self.rx = Receiver(key, clock=clock)
        self.tx = Sender(gw_id, key)
        self._alarm_seen = 0

    def _ack(self, pkt):
        ack = self.tx.seal(pkt.last_hop, pkt.last_hop, PacketType.ACK, bytes([pkt.src]), ttl=1)
        return encode(ack)

    def on_frame(self, raw, rssi=None):
        """Bir kare işler. Dönüş: gönderilmesi gereken kareler (ACK) listesi."""
        now = self.clock()
        try:
            pkt = decode(raw)
        except ValueError:
            self.db.count_status("malformed")
            return []
        if pkt.ptype == PacketType.HELLO:
            status, _ = self.rx.open(pkt)
            self.db.count_status("hello_" + status)
            if status == "ok":
                self.db.touch_node(pkt.src, now, rssi, hello=True)
            self._security_log(pkt, status, now)
            return []
        if pkt.ptype != PacketType.DATA or pkt.next_hop != self.gw_id:
            return []
        status, data = self.rx.open(pkt)
        self.db.count_status(status)
        out = []
        if status == "ok":
            counter = self.rx.last[pkt.src]
            try:
                report = decode_report(data)
            except ValueError as e:
                self.db.add_alarm(now, pkt.src, "rapor_hatasi", str(e))
                return [self._ack(pkt)]
            uid = f"{pkt.src}:{counter}"
            if self.db.insert_message(uid, pkt.src, counter, now, report, rssi):
                self.db.touch_node(pkt.src, now, rssi, report=report)
                self.db.enqueue(uid, {"uid": uid, "src": pkt.src, "counter": counter, "kind": KIND_NAMES[report["kind"]],
                                      "x": report["x"], "y": report["y"], "battery": report["battery"],
                                      "code": report["code"], "text": report["text"], "received_at": now}, now)
            out.append(self._ack(pkt))
        elif status == "dup":
            out.append(self._ack(pkt))
        self._security_log(pkt, status, now)
        return out

    def _security_log(self, pkt, status, now):
        if status not in ("ok", "dup"):
            self.db.add_alarm(now, pkt.src, status, f"tür={pkt.ptype.name} seq={pkt.seq}")
        while self._alarm_seen < len(self.rx.alarms):
            src, _ = self.rx.alarms[self._alarm_seen]
            self.db.add_alarm(now, src, "klon_alarmi", "kısa sürede çok sayıda sayaç anomalisi")
            self._alarm_seen += 1


if __name__ == "__main__":
    import os

    from gateway.receiver.report import KIND_SOS, KIND_STATUS, encode_report

    key = os.urandom(16)
    db = Database()
    gw = Gateway(db, key)
    node = Sender(5, key)
    other = Sender(7, key)
    frames = [
        encode(node.seal(1, 1, PacketType.HELLO, b"", ttl=1)),
        encode(node.seal(1, 1, PacketType.DATA, encode_report(KIND_STATUS, 120, 80, 88, 0, "devriye"))),
        encode(other.seal(1, 1, PacketType.DATA, encode_report(KIND_SOS, -300, 410, 41, 7, "yaralı var"))),
    ]
    for f in frames:
        acks = gw.on_frame(f, rssi=-97.0)
        print("kare", len(f), "bayt -> ACK sayısı", len(acks))
    gw.on_frame(frames[1], rssi=-97.0)
    gw.on_frame(b"\x01\x02", rssi=-97.0)
    print("düğümler :", [(n["node_id"], n["msg_count"], n["battery"]) for n in db.nodes()])
    print("mesajlar :", [(m["uid"], m["kind"], m["text"]) for m in db.messages()])
    print("istatistik:", db.rx_stats())
    print("alarmlar :", [(a["src"], a["kind"]) for a in db.alarms()])
    print("kuyruk   :", db.pending_count())
