import hashlib
import os
import struct
import time
from collections import deque
from dataclasses import replace

from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from sim.packet import TAG_BYTES, Packet, PacketType

MAX_JUMP = 1024
HISTORY = 64
ALARM_COUNT = 3
ALARM_WINDOW = 60.0
DUP_WINDOW = 30.0
LATE_WINDOW = 32


def load_key():
    # Anahtar repoda tutulmaz: ortam değişkeninden okunur, yoksa süreç için rastgele üretilir.
    h = os.environ.get("MESH_AES_KEY")
    return bytes.fromhex(h) if h else os.urandom(16)


def nonce_for(src, ptype, counter):
    # 12 bayt: kaynak (1) + tür (1) + 32 bit sayaç (4) + 6 sıfır. (anahtar, nonce) çifti asla tekrar etmemeli.
    return struct.pack(">BBI", src, ptype.value, counter) + b"\x00" * 6


def aad_for(pkt):
    # Hop'ta değişen alanlar (next_hop, ttl, last_hop) hariç; değişmeyen başlık alanları doğrulanır.
    return struct.pack(">BBBH", pkt.src, pkt.dst, pkt.ptype.value, pkt.seq)


class PersistentCounter:
    # Sayaç, yeniden başlatmada geri dönmemeli. Flash'a her BLOCK karede bir "rezerv sınır" yazılır;
    # açılışta sayaç rezerv sınırdan başlar (kaybolan en fazla BLOCK numara atlanır).
    def __init__(self, flash, block=64):
        self.flash = flash
        self.block = block
        self.value = flash.get("ctr", 0)
        self.reserved = self.value + block
        flash["ctr"] = self.reserved
        self.value = self.reserved
        self.reserved = self.value + block
        flash["ctr"] = self.reserved
        self.writes = 2

    def next(self):
        self.value += 1
        if self.value >= self.reserved:
            self.reserved += self.block
            self.flash["ctr"] = self.reserved
            self.writes += 1
        return self.value


class Sender:
    def __init__(self, node_id, key, counter=None):
        self.node_id = node_id
        self.aead = AESCCM(key, tag_length=TAG_BYTES)
        self.counter = counter if counter is not None else PersistentCounter({})

    def seal(self, dst, next_hop, ptype, payload, ttl=8):
        c = self.counter.next()
        pkt = Packet(self.node_id, dst, next_hop, ptype, c & 0xFFFF, ttl, b"", self.node_id)
        out = self.aead.encrypt(nonce_for(self.node_id, ptype, c), payload, aad_for(pkt))
        return replace(pkt, payload=out[:-TAG_BYTES], tag=out[-TAG_BYTES:])


class Receiver:
    def __init__(self, key, clock=None):
        self.aead = AESCCM(key, tag_length=TAG_BYTES)
        self.clock = clock or time.monotonic
        self.last = {}
        self.seen = {}
        self.events = {}
        self.alarms = []

    def _try(self, pkt, counter):
        try:
            data = self.aead.decrypt(nonce_for(pkt.src, pkt.ptype, counter), pkt.payload + pkt.tag, aad_for(pkt))
            return data
        except Exception:
            return None

    def _note(self, src, kind):
        now = self.clock()
        ev = self.events.setdefault(src, deque())
        ev.append((now, kind))
        while ev and now - ev[0][0] > ALARM_WINDOW:
            ev.popleft()
        bad = sum(1 for _, k in ev if k in ("regression", "jump"))
        if bad >= ALARM_COUNT and not any(a[0] == src and now - a[1] < ALARM_WINDOW for a in self.alarms):
            self.alarms.append((src, now))

    def open(self, pkt):
        # Dönüş: (durum, açık yük). Durumlar: ok, dup, replay, regression, jump, bad_tag
        last = self.last.get(pkt.src)
        base = (last or 0) & ~0xFFFF
        cands = [base | pkt.seq, (base | pkt.seq) + 0x10000]
        if base:
            cands.append((base | pkt.seq) - 0x10000)
        for c in cands:
            data = self._try(pkt, c)
            if data is None:
                continue
            hist = self.seen.setdefault(pkt.src, {})
            if last is None or c > last:
                if last is not None and c - last > MAX_JUMP:
                    self._note(pkt.src, "jump")
                    return "jump", None
                self.last[pkt.src] = c
                hist[c] = (pkt.tag, self.clock())
                if len(hist) > HISTORY:
                    hist.pop(min(hist))
                return "ok", data
            seen = hist.get(c)
            if seen is not None and seen[0] == pkt.tag:
                # Özdeş kare: kısa süre içindeyse yeniden gönderim (dup), değilse tekrar oynatma (replay)
                return ("dup" if c == last or self.clock() - seen[1] <= DUP_WINDOW else "replay"), None
            if c >= last - LATE_WINDOW and c not in hist:
                # Çok sekmeli ağda paketler sıra dışı gelebilir: pencere içindeki görülmemiş sayaç kabul edilir
                hist[c] = (pkt.tag, self.clock())
                return "ok", data
            self._note(pkt.src, "regression")
            return "regression", None
        return "bad_tag", None


if __name__ == "__main__":
    key = load_key()
    t = [0.0]
    rx = Receiver(key, clock=lambda: t[0])
    node = Sender(5, key)
    GW = 1

    print("== 1. Normal akış: düğüm 5, 5 kare")
    frames = [node.seal(GW, GW, PacketType.DATA, b"yangin-" + bytes([65 + i])) for i in range(5)]
    for f in frames:
        t[0] += 5
        print("  ", rx.open(f), "| yük", len(f.payload), "bayt + etiket", len(f.tag), "bayt | şifreli:", f.payload.hex())

    print("== 2. Sahtecilik denemeleri")
    f = node.seal(GW, GW, PacketType.DATA, b"normal")
    bozuk = replace(f, payload=bytes([f.payload[0] ^ 1]) + f.payload[1:])
    print("  yükte 1 bit değişti       :", rx.open(bozuk)[0])
    print("  kaynak adresi değişti     :", rx.open(replace(f, src=6))[0])
    yabanci = Sender(5, os.urandom(16)).seal(GW, GW, PacketType.DATA, b"normal")
    print("  yanlış anahtar            :", rx.open(yabanci)[0])
    print("  doğru kare                :", rx.open(f)[0])
    g = node.seal(GW, GW, PacketType.DATA, b"normal")
    print("  hop alanı (ttl) değişti   :", rx.open(replace(g, ttl=1))[0], "(hop alanları doğrulanmaz; bilinen sınır)")

    print("== 3. Tekrar oynatma (replay)")
    print("  aynı kare tekrar (hemen)  :", rx.open(g)[0])
    print("  eski kare, 2 sn sonra     :", rx.open(frames[1])[0], "(yeniden gönderim sayılır)")
    t[0] += 120
    print("  eski kare, 2 dk sonra     :", rx.open(frames[1])[0])

    print("== 4. 16 bit sıra numarası taşması (sayaç 32 bit)")
    n2 = Sender(7, key, counter=PersistentCounter({"ctr": 65450}, block=64))
    rx2 = Receiver(key, clock=lambda: t[0])
    sonuc = []
    for i in range(40):
        fr = n2.seal(GW, GW, PacketType.DATA, b"x")
        sonuc.append((fr.seq, rx2.open(fr)[0]))
    print("  ilk seq", sonuc[0][0], "-> son seq", sonuc[-1][0], "(65535'ten sonra 0'a döndü) | durumlar:", {s for _, s in sonuc})

    print("== 5. Yeniden başlatma: sayaç geri dönerse ne olur?")
    flash = {}
    a = Sender(8, key, counter=PersistentCounter(flash, block=64))
    rx3 = Receiver(key, clock=lambda: t[0])
    for _ in range(100):
        rx3.open(a.seal(GW, GW, PacketType.DATA, b"x"))
    gecici = Sender(8, key, counter=None)
    print("  kalıcı sayaç olmadan yeniden başlama:", [rx3.open(gecici.seal(GW, GW, PacketType.DATA, b"x"))[0] for _ in range(3)],
          "| alarm:", [al[0] for al in rx3.alarms])
    flash2 = {}
    b = Sender(9, key, counter=PersistentCounter(flash2, block=64))
    rx4 = Receiver(key, clock=lambda: t[0])
    for _ in range(100):
        rx4.open(b.seal(GW, GW, PacketType.DATA, b"x"))
    b2 = Sender(9, key, counter=PersistentCounter(flash2, block=64))
    print("  kalıcı sayaçla yeniden başlama      :", [rx4.open(b2.seal(GW, GW, PacketType.DATA, b"x"))[0] for _ in range(3)],
          "| flash yazma sayısı:", b.counter.writes, "(100 karede)")

    print("== 6. Klon (anahtar çalınmış) senaryoları")
    rx5 = Receiver(key, clock=lambda: t[0])
    meşru = Sender(10, key, counter=PersistentCounter({}, block=64))
    for _ in range(200):
        rx5.open(meşru.seal(GW, GW, PacketType.DATA, b"x"))
    klon = Sender(10, key, counter=PersistentCounter({}, block=64))
    sonuc = []
    for _ in range(4):
        t[0] += 1
        sonuc.append(rx5.open(klon.seal(GW, GW, PacketType.DATA, b"klon"))[0])
    print("  klon geriden başlıyor (sayaç < meşru):", sonuc, "| alarm:", [al[0] for al in rx5.alarms])
    ileri = Sender(10, key, counter=PersistentCounter({"ctr": 5000}, block=64))
    sonuc = []
    for _ in range(4):
        t[0] += 1
        sonuc.append(rx5.open(ileri.seal(GW, GW, PacketType.DATA, b"klon"))[0])
    print("  klon çok ileriden başlıyor (> 1024)  :", sonuc)
    yakin = Sender(10, key, counter=PersistentCounter({"ctr": 700}, block=64))
    print("  klon biraz ileriden (< 1024)         :", rx5.open(yakin.seal(GW, GW, PacketType.DATA, b"klon"))[0],
          "-> meşru düğümün sonraki kareleri:", rx5.open(meşru.seal(GW, GW, PacketType.DATA, b"x"))[0], "(DoS riski, bilinen sınır)")

    print("== 7. Anahtarsız sahtecilik: 20000 rastgele etiket")
    rx6 = Receiver(key, clock=lambda: t[0])
    f0 = node.seal(GW, GW, PacketType.DATA, b"normal")
    kabul = 0
    for _ in range(20000):
        sahte = replace(f0, tag=os.urandom(TAG_BYTES))
        if rx6.open(sahte)[0] == "ok":
            kabul += 1
    print("  kabul edilen:", kabul, "(beklenen ≈ 20000 / 2^32 ≈ 0)")

    print("== 8. Hız (bilgisayarda, yaklaşık)")
    fr = node.seal(GW, GW, PacketType.DATA, b"x" * 20)
    t0 = time.perf_counter()
    for _ in range(2000):
        node.seal(GW, GW, PacketType.DATA, b"x" * 20)
    print(f"  mühürleme: {(time.perf_counter() - t0) / 2000 * 1e6:.0f} mikrosaniye/kare (STM32'de ayrıca ölçülecek)")
