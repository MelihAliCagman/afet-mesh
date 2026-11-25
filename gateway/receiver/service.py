import time

from gateway.receiver.db import Database
from gateway.receiver.report import KIND_NAMES, decode_report
from sim.packet import BROADCAST, Packet, PacketType
from sim.routing import encode_hello
from sim.security import PersistentCounter, Receiver, Sender
from sim.wire import decode, encode

GATEWAY_ID = 1
FLUSH_SECONDS = 5.0


class DbDict:
    """PersistentCounter'ın beklediği sözlük arayüzü; değerleri veritabanındaki kv tablosunda saklar."""

    def __init__(self, db, prefix):
        self.db = db
        self.prefix = prefix

    def get(self, key, default=0):
        v = self.db.kv_get(f"{self.prefix}:{key}")
        return int(v) if v is not None else default

    def __setitem__(self, key, value):
        self.db.kv_set(f"{self.prefix}:{key}", value)


class Gateway:
    """Havadan gelen ham baytı doğrular, çözer, veritabanına yazar ve gerekirse ACK üretir."""

    def __init__(self, db, key, gw_id=GATEWAY_ID, clock=time.time, persist=True, flush_s=FLUSH_SECONDS):
        self.db = db
        self.gw_id = gw_id
        self.clock = clock
        self.persist = persist
        self.flush_s = flush_s
        self._last_flush = clock()
        self.rx = Receiver(key, clock=clock)
        if persist:
            # Yeniden başlatmada her düğümün son sayacı ve son kareleri yüklenir: tekrar oynatma penceresi açılmaz.
            for src, last, hist in db.load_peer_states():
                self.rx.import_peer(src, last, hist)
            # Gateway'in kendi (ACK) sayacı da geri dönmemeli; yoksa düğümler ACK'leri "eski" sayıp reddeder.
            self.tx = Sender(gw_id, key, PersistentCounter(DbDict(db, "gw_counter"), block=64))
        else:
            self.tx = Sender(gw_id, key)
        self._alarm_seen = 0

    def flush(self):
        """Değişen güvenlik durumlarını tek işlemde yazar."""
        if not self.persist or not self.rx.dirty:
            return
        rows = []
        for src in sorted(self.rx.dirty):
            last, hist = self.rx.export_peer(src)
            rows.append((src, last, hist))
        self.rx.dirty.clear()
        self.db.save_peer_states(rows, self.clock())
        self._last_flush = self.clock()

    def close(self):
        self.flush()

    def _ack(self, pkt):
        # Güvenli protokolde ACK yükü 3 bayt: onaylanan paketin kaynağı ve sıra numarası (docs/protokol.md)
        payload = bytes([pkt.src, (pkt.seq >> 8) & 0xFF, pkt.seq & 0xFF])
        ack = self.tx.seal(pkt.last_hop, pkt.last_hop, PacketType.ACK, payload, ttl=1)
        return encode(ack)

    def hello_frame(self):
        """Gateway'in periyodik HELLO'su: düğümler bundan gateway'e giden yolu öğrenir. Sıra numarası kalıcıdır
        (yeniden başlatmada geri dönerse düğümler yeni ilanları 'eski' sayıp yok sayar)."""
        seq = (int(self.db.kv_get("gw_seq", 0)) + 1) % 65536
        self.db.kv_set("gw_seq", seq)
        hello = self.tx.seal(BROADCAST, BROADCAST, PacketType.HELLO, encode_hello(seq, 0, 0), ttl=1)
        return encode(hello)

    def on_frame(self, raw, rssi=None):
        """Bir kare işler. Dönüş: gönderilmesi gereken kareler (ACK) listesi."""
        now = self.clock()
        if self.persist and now - self._last_flush >= self.flush_s:
            self.flush()
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
