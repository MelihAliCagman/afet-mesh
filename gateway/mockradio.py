import os
import random
import threading
import time
from dataclasses import replace

from gateway.receiver.report import KIND_SENSOR, KIND_SOS, KIND_STATUS, encode_report
from gateway.receiver.service import Gateway
from sim.experiment import GRID, build
from sim.packet import BROADCAST, PacketType
from sim.security import PersistentCounter, Sender
from sim.wire import encode


class MockRadio:
    """Simülasyondaki ağı gerçek bir LoRa radyosu gibi kullanır: gateway düğümünün duyduğu her paketi,
    sanki kaynağı mühürlemiş gibi güvenli kareye çevirip alıcı servise (Gateway) ham bayt olarak verir."""

    def __init__(self, db, key=None, positions=GRID, seed=0, report_period=20.0, sos_prob=0.03,
                 loss=0.0, hello_period=5.0, timeout=15.0):
        self.key = key or os.urandom(16)
        self.lock = threading.RLock()
        self.sim, self.mesh = build(positions, seed, hello_period=hello_period, timeout=timeout, loss=loss)
        self.gw_node = self.mesh[0]
        self.rng = random.Random(seed + 1000)
        self.wall0 = time.time()
        self.gateway = Gateway(db, self.key, clock=self.clock)
        self.senders = {m.node.node_id: Sender(m.node.node_id, self.key, PersistentCounter({}, block=64))
                        for m in self.mesh if not m.node.is_gateway}
        self.cache = {}
        self.sent_frames = []
        self.battery = {m.node.node_id: self.rng.randint(70, 100) for m in self.mesh}
        self.report_period = report_period
        self.sos_prob = sos_prob
        self.reports_sent = 0
        self.frames_fed = 0
        self.gw_node.tap = self._tap
        for m in self.mesh[1:]:
            self.sim.schedule(self.rng.uniform(10.0, 10.0 + report_period), lambda m=m: self._report(m))

    def clock(self):
        return self.wall0 + self.sim.now

    # ---- uygulama trafiği ----
    def _report(self, m):
        if m.alive:
            nid = m.node.node_id
            self.battery[nid] = max(5, self.battery[nid] - self.rng.choice([0, 0, 0, 1]))
            gw = self.gw_node.node
            x, y = int(m.node.x - gw.x), int(m.node.y - gw.y)
            r = self.rng.random()
            if r < self.sos_prob:
                payload = encode_report(KIND_SOS, x, y, self.battery[nid], self.rng.randint(1, 9), "yardim")
            elif r < 0.35:
                payload = encode_report(KIND_SENSOR, x, y, self.battery[nid], 0, f"sicaklik {self.rng.randint(18, 34)}")
            else:
                payload = encode_report(KIND_STATUS, x, y, self.battery[nid], 0, "")
            if m.send_data(payload):
                self.reports_sent += 1
        self.sim.schedule(self.report_period * self.rng.uniform(0.8, 1.2), lambda: self._report(m))

    # ---- gateway'in duyduğu her paket ----
    def _tap(self, pkt, rssi):
        if pkt.ptype == PacketType.HELLO:
            src = pkt.src
            ptype, dst, nh, payload, ttl = PacketType.HELLO, BROADCAST, BROADCAST, b"", 1
        elif pkt.ptype == PacketType.DATA and pkt.next_hop == self.gw_node.node.node_id:
            src = pkt.src
            ptype, dst, nh, payload, ttl = PacketType.DATA, pkt.dst, pkt.next_hop, pkt.payload, pkt.ttl
        else:
            return
        key = (src, pkt.seq, ptype)
        if key not in self.cache:  # aynı paketin yeniden gönderimi aynı kareyi üretir (çift bastırma bunu yakalar)
            frame = self.senders[src].seal(dst, nh, ptype, payload, ttl)
            self.cache[key] = encode(replace(frame, last_hop=pkt.last_hop))
            self.sent_frames.append(self.cache[key])
        self.feed(self.cache[key], rssi)

    def feed(self, raw, rssi=-100.0):
        self.frames_fed += 1
        return self.gateway.on_frame(raw, rssi)

    # ---- saldırı denemeleri ----
    def inject_replay(self, count=1):
        with self.lock:
            self._inject_replay(count)

    def _inject_replay(self, count):
        data = [f for f in self.sent_frames if f[3] == PacketType.DATA.value]
        for _ in range(count):
            self.feed(self.rng.choice(data[: max(1, len(data) // 2)]))

    def inject_forgery(self, src, count=1):
        with self.lock:
            self._inject_forgery(src, count)

    def _inject_forgery(self, src, count):
        fake = Sender(src, os.urandom(16))
        for _ in range(count):
            self.feed(encode(fake.seal(1, 1, PacketType.DATA, encode_report(KIND_SOS, 0, 0, 50, 9, "sahte"))))

    def inject_clone(self, src, count=4):
        with self.lock:
            self._inject_clone(src, count)

    def _inject_clone(self, src, count):
        clone = Sender(src, self.key, PersistentCounter({}, block=64))
        for _ in range(count):
            self.sim.run(until=self.sim.now + 1.0)
            self.feed(encode(clone.seal(1, 1, PacketType.DATA, encode_report(KIND_SOS, 0, 0, 50, 9, "klon"))))

    # ---- çalıştırma ----
    def run(self, until, realtime=False, speed=1.0):
        end = self.sim.now + until
        if not realtime:
            self.sim.run(until=end)
            return
        while self.sim.now < end:
            with self.lock:
                self.sim.run(until=self.sim.now + 1.0 * speed)
            time.sleep(1.0)

    def kill_node(self, node_id):
        with self.lock:
            next(m for m in self.mesh if m.node.node_id == node_id).kill()


if __name__ == "__main__":
    from gateway.receiver.db import Database

    db = Database()
    radio = MockRadio(db, seed=3)
    radio.run(300)
    print("== 1. Normal akış (3x3 ızgara, 300 sn, her düğüm ~20 sn'de bir rapor)")
    print(f"gönderilen rapor: {radio.reports_sent} | gateway'e ulaşan mesaj (veritabanı): {db.message_count()} | "
          f"simülasyon gateway DATA: {len(radio.gw_node.delivered)}")
    print("düğümler:", [(n["node_id"], n["msg_count"], n["battery"]) for n in db.nodes()])
    print("istatistik:", db.rx_stats())
    kinds = {}
    for m in db.messages(1000):
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    print("türlere göre mesaj (1 durum, 2 SOS, 3 sensör):", kinds)
    print("== 2. Saldırı denemeleri")
    before = db.message_count()
    radio.inject_replay(5)
    radio.inject_forgery(4, 5)
    radio.inject_clone(6, 4)
    print("yeni mesaj eklendi mi:", db.message_count() - before, "(0 beklenir)")
    print("alarm türleri:", sorted({a["kind"] for a in db.alarms(100)}))
    print("istatistik:", db.rx_stats())
    print("== 3. Düğüm arızası: düğüm 5 kapatıldı, 120 sn daha")
    radio.kill_node(5)
    n0 = db.message_count()
    radio.run(120)
    print("arıza sonrası gelen mesaj:", db.message_count() - n0, "| düğüm 5 son görülme (sn önce):",
          round(radio.clock() - next(n for n in db.nodes() if n["node_id"] == 5)["last_seen"]))
