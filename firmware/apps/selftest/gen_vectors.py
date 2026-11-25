"""Karttaki öz-sınama için Python'dan referans vektörleri üretir: python firmware/apps/selftest/gen_vectors.py
Çıktı: firmware/apps/selftest/vectors.h (C dizileri). Sabit tohumla üretilir, her çalıştırmada aynıdır."""
import os
import random
import sys
from dataclasses import replace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from cryptography.hazmat.primitives.ciphers.aead import AESCCM  # noqa: E402

from sim.packet import PacketType  # noqa: E402
from sim.routing import RoutingTable  # noqa: E402
from sim.security import PersistentCounter, Receiver, Sender  # noqa: E402
from sim.wire import encode  # noqa: E402

KEY = bytes(range(16))  # yalnızca sınama anahtarı
STATUS = {"ok": 0, "dup": 1, "replay": 2, "regression": 3, "jump": 4, "bad_tag": 5}


def arr(name, data, typ="uint8_t"):
    body = ", ".join(str(b) for b in data)
    return f"static const {typ} {name}[{max(1, len(data))}] = {{{body}}};\n"


def main():
    rng = random.Random(2026)
    out = ["/* OTOMATİK ÜRETİLDİ: gen_vectors.py. Elle değiştirmeyin. */\n#include <stdint.h>\n\n"]

    # --- CCM vektörleri ---
    out.append(f"#define CCM_N 6\n")
    lens = [0, 1, 13, 20, 47, 64]
    keys, nonces, aads, pts, cts = b"", b"", b"", b"", b""
    ct_off, pt_len = [], []
    for n in lens:
        k, no, aad, pt = rng.randbytes(16), rng.randbytes(12), rng.randbytes(5), rng.randbytes(n)
        ref = AESCCM(k, tag_length=4).encrypt(no, pt, aad)
        keys += k; nonces += no; aads += aad; pts += pt; cts += ref
        pt_len.append(n)
    out += [arr("ccm_keys", keys), arr("ccm_nonces", nonces), arr("ccm_aads", aads), arr("ccm_pts", pts),
            arr("ccm_cts", cts), arr("ccm_lens", pt_len)]

    # --- paket biçimi vektörü ---
    s = Sender(7, KEY, PersistentCounter({}, block=64))
    pkt = replace(s.seal(1, 3, PacketType.DATA, b"\x01\x00\x0a\x00\x14\x50\x00hello"), ttl=6, last_hop=4)
    raw = encode(pkt)
    out.append(arr("wire_raw", raw))
    out.append(f"static const uint8_t wire_fields[8] = {{{pkt.src}, {pkt.dst}, {pkt.next_hop}, {pkt.ptype.value}, {pkt.seq >> 8}, {pkt.seq & 255}, {pkt.ttl}, {pkt.last_hop}}};\n")

    # --- yönlendirme dizisi ---
    py = RoutingTable(me=1, timeout=15.0)
    ops, exp = [], []
    now = 0
    for _ in range(80):
        now += rng.choice([0, 1, 2, 5, 9, 16])
        nb = rng.randint(2, 7)
        op = rng.random()
        if op < 0.7:
            seq = rng.randrange(65500, 65536) if rng.random() < 0.3 else rng.randrange(0, 40)
            met, nh = rng.randint(0, 8), rng.choice([0, 1, 2, 3, 9])
            rssi = rng.choice([-125, -119, -118, -112, -110, -100, -90]) + 0.25
            py.update(nb, seq, met, nh, rssi, float(now))
            ops.append((0, nb, seq, met, nh, int(rssi * 100), now * 1000))
        elif op < 0.85:
            py.remove_neighbor(nb, float(now))
            ops.append((1, nb, 0, 0, 0, 0, now * 1000))
        else:
            py.select(float(now))
            ops.append((2, nb, 0, 0, 0, 0, now * 1000))
        r = py.route
        exp.append((1, r.next_hop, r.metric, r.gw_seq, py.switches) if r else (0, 0, 0, 0, py.switches))
    out.append(f"#define ROUTE_N {len(ops)}\n")
    out.append("typedef struct { uint8_t op, nb; uint16_t seq; uint8_t metric, nh; int32_t rssi_x100; uint32_t t_ms; } route_op_t;\n")
    out.append("static const route_op_t route_ops[ROUTE_N] = {" + ", ".join(
        "{%d, %d, %d, %d, %d, %d, %du}" % o for o in ops) + "};\n")
    out.append("typedef struct { uint8_t valid, nh; uint16_t metric, gw_seq; uint32_t switches; } route_exp_t;\n")
    out.append("static const route_exp_t route_exp[ROUTE_N] = {" + ", ".join("{%d, %d, %d, %d, %du}" % e for e in exp) + "};\n")

    # --- güvenlik alıcısı dizisi ---
    t = [0.0]
    rx = Receiver(KEY, clock=lambda: t[0])
    a = Sender(5, KEY, PersistentCounter({}, block=64))
    clone = Sender(5, KEY, PersistentCounter({}, block=64))
    forger = Sender(5, bytes(16), PersistentCounter({}, block=64))
    far = Sender(5, KEY, PersistentCounter({"ctr": 5000}, block=64))
    frames = [a.seal(1, 1, PacketType.DATA, b"veri%d" % i) for i in range(12)]
    events = []

    def feed(p, dt):
        t[0] += dt
        n0 = len(rx.alarms)
        st, _ = rx.open(p)
        events.append((p, int(t[0] * 1000), STATUS[st], 1 if len(rx.alarms) > n0 else 0))

    for i in (0, 1, 2, 3):
        feed(frames[i], 1)
    feed(frames[3], 1)                                       # kopya
    feed(frames[5], 1)                                       # kare 4 atlandı
    feed(frames[4], 1)                                       # geç gelen (pencere içinde)
    feed(frames[4], 1)                                       # geç gelenin kopyası
    feed(frames[1], 60)                                      # uzun süre sonra eski kare: replay
    feed(forger.seal(1, 1, PacketType.DATA, b"sahte"), 1)    # yanlış anahtar
    for _ in range(3):
        feed(clone.seal(1, 1, PacketType.DATA, b"klon"), 1)  # geriden sayaç: regression x3, 3. alarm
    feed(far.seal(1, 1, PacketType.DATA, b"ileri"), 1)       # çok ileri sayaç: jump
    feed(frames[6], 1)
    blob, offs = b"", []
    for p, _, _, _ in events:
        raw = encode(p)
        offs.append((len(blob), len(raw)))
        blob += raw
    out.append(arr("sec_blob", blob))
    out.append(f"#define SEC_N {len(events)}\n")
    out.append("typedef struct { uint16_t off; uint8_t len; uint32_t t_ms; uint8_t status, alarm; } sec_ev_t;\n")
    out.append("static const sec_ev_t sec_ev[SEC_N] = {" + ", ".join(
        "{%d, %d, %du, %d, %d}" % (o[0], o[1], e[1], e[2], e[3]) for o, e in zip(offs, events)) + "};\n")
    out.append("static const uint8_t sec_key[16] = {" + ", ".join(str(b) for b in KEY) + "};\n")

    path = os.path.join(os.path.dirname(__file__), "vectors.h")
    open(path, "w", newline="\n").write("".join(out))
    print("yazıldı:", path, len(blob), "bayt güvenlik verisi,", len(ops), "yönlendirme işlemi,", len(events), "güvenlik olayı")


if __name__ == "__main__":
    main()
