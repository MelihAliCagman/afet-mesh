import csv
import os
import random
import statistics
import sys

from sim.engine import Simulator
from sim.lora import airtime
from sim.mesh_sim import Node
from sim.node import MeshNode, route_path
from sim.radio import Radio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "docs", "olcumler", "veri")
PLOT_DIR = os.path.join(ROOT, "docs", "olcumler", "grafikler")
GRID = [(x * 500.0, y * 500.0) for y in range(3) for x in range(3)]
HELLO_BYTES = 16


def build(positions, seed, hello_period=5.0, timeout=15.0, loss=0.0, collide=True,
          csma=True, max_retry=3, fast_detect=True, rerr_on=True, sf=7):
    sim = Simulator()
    nodes = [Node(i + 1, x, y, is_gateway=(i == 0)) for i, (x, y) in enumerate(positions)]
    radio = Radio(sim, nodes, sf=sf, loss=loss, seed=seed, collide=collide)
    mesh = [MeshNode(n, sim, radio, hello_period=hello_period, timeout=timeout, seed=seed,
                     max_retry=max_retry, csma=csma, fast_detect=fast_detect, rerr_on=rerr_on)
            for n in nodes]
    for m in mesh:
        m.start()
    return sim, mesh


def latencies(mesh, src=None):
    sent = {}
    for m in mesh:
        for seq, t in m.sent_at.items():
            sent[(m.node.node_id, seq)] = t
    out = []
    for s, q, t in mesh[0].delivered:
        if src is None or s == src:
            out.append(t - sent[(s, q)])
    return out


def run_recovery(seed, hello_period, timeout, fast_detect, positions=GRID, sender_id=9):
    sim, mesh = build(positions, seed, hello_period, timeout, fast_detect=fast_detect)
    sim.run(until=2 * timeout + 20)
    t0 = sim.now
    sender = mesh[sender_id - 1]
    path, _ = route_path(mesh, sender_id)
    victim = next(m for m in mesh if m.node.node_id == path[-2])
    fail_t = t0 + 30.0
    total = int(30 + timeout + 60)
    for i in range(total):
        sim.schedule(i * 1.0, lambda: sender.send_data(b"x"))
    sim.schedule(30.0, victim.kill)
    sim.run(until=t0 + total + 30)
    got = {q: t for s, q, t in mesh[0].delivered if s == sender_id}
    after = [q for q, t in sender.sent_at.items() if t >= fail_t]
    ok = [q for q in after if q in got]
    rec = min(got[q] for q in ok) - fail_t if ok else None
    lat = latencies(mesh, sender_id)
    return {"recovery_s": rec, "post_pdr": 100.0 * len(ok) / len(after),
            "mean_latency_s": statistics.mean(lat) if lat else None}


def run_load(seed, interval, csma, count=10, positions=GRID):
    sim, mesh = build(positions, seed, csma=csma)
    sim.run(until=60)
    rng = random.Random(seed)
    for m in mesh[1:]:
        off = rng.uniform(0.0, interval)
        for i in range(count):
            sim.schedule(off + i * interval, lambda m=m: m.send_data(b"x"))
    sim.run(until=sim.now + count * interval + 40)
    sent = count * (len(mesh) - 1)
    lat = sorted(latencies(mesh))
    return {"pdr": 100.0 * len(mesh[0].delivered) / sent,
            "mean_latency_s": statistics.mean(lat) if lat else None,
            "p95_latency_s": lat[int(0.95 * (len(lat) - 1))] if lat else None,
            "collisions": mesh[0].radio.collisions,
            "retx": sum(m.retx for m in mesh)}


def write_csv(name, rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def mean_std(values):
    v = [x for x in values if x is not None]
    if not v:
        return None, None
    return statistics.mean(v), (statistics.stdev(v) if len(v) > 1 else 0.0)


def sweep_recovery(seeds):
    rows = []
    for period in (5, 10, 20, 30, 60):
        for fast in (False, True):
            for seed in range(seeds):
                r = run_recovery(seed, float(period), 3.0 * period, fast)
                rows.append({"hello_period_s": period, "timeout_s": 3 * period,
                             "ack_detection": int(fast), "seed": seed, **r})
    return rows


def sweep_load(seeds):
    rows = []
    for interval in (2, 4, 8, 16, 32):
        for csma in (False, True):
            for seed in range(seeds):
                r = run_load(seed, float(interval), csma)
                rows.append({"interval_s": interval, "csma": int(csma), "seed": seed, **r})
    return rows


def summarize(rows, keys, value):
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r[value] if r[value] != "" else None)
    return {k: mean_std(v) for k, v in groups.items()}


def hello_duty(period, sf=7):
    return 100.0 * airtime(HELLO_BYTES, sf) / period


def plots(rec_rows, load_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BLUE, ORANGE, INK, MUTED, GRIDC = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e1"

    def style(ax, xlabel, ylabel, title):
        ax.set_facecolor("#fcfcfb")
        ax.grid(axis="y", color=GRIDC, linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#b9b8b2")
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
        ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
        ax.set_title(title, color=INK, fontsize=10.5, loc="left")

    def series(ax, groups, color, label):
        xs = sorted(groups)
        ys = [groups[x][0] for x in xs]
        es = [groups[x][1] for x in xs]
        ax.errorbar(xs, ys, yerr=es, color=color, linewidth=2, marker="o", markersize=5,
                    markeredgecolor="#fcfcfb", markeredgewidth=1.5, capsize=3, elinewidth=1)
        ax.annotate(label, (xs[-1], ys[-1]), textcoords="offset points", xytext=(-4, 8),
                    ha="right", color=INK, fontsize=9)

    # Şekil 1: iyileşme süresi ve HELLO bedeli
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.6), facecolor="#fcfcfb")
    for fast, color, label in ((0, BLUE, "yalnız HELLO zaman aşımı"), (1, ORANGE, "+ ACK hatası tespiti")):
        g = summarize([r for r in rec_rows if int(r["ack_detection"]) == fast], ["hello_period_s"], "recovery_s")
        series(a1, {k[0]: v for k, v in g.items() if v[0] is not None}, color, label)
    style(a1, "HELLO periyodu (sn); zaman aşımı = 3 x periyot", "iyileşme süresi (sn)", "Arıza tespit yöntemi iyileşmeyi belirler")
    a1.set_ylim(bottom=0)
    periods = sorted({int(r["hello_period_s"]) for r in rec_rows})
    a2.plot(periods, [hello_duty(p) for p in periods], color=BLUE, linewidth=2, marker="o", markersize=5,
            markeredgecolor="#fcfcfb", markeredgewidth=1.5)
    a2.axhline(1.0, color=MUTED, linewidth=1, linestyle="--")
    a2.annotate("yasal sınır %1", (periods[-1], 1.0), textcoords="offset points", xytext=(-4, 5), ha="right", color=MUTED, fontsize=9)
    style(a2, "HELLO periyodu (sn)", "HELLO'nun yayın süresi payı (%)", "HELLO'nun bedeli (SF7, 16 bayt)")
    a2.set_ylim(bottom=0)
    fig.tight_layout()
    os.makedirs(PLOT_DIR, exist_ok=True)
    fig.savefig(os.path.join(PLOT_DIR, "sekil-iyilesme-suresi.png"), dpi=160)
    plt.close(fig)

    # Şekil 2: yük, PDR ve gecikme
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.6), facecolor="#fcfcfb")
    for csma, color, label in ((0, BLUE, "CSMA yok"), (1, ORANGE, "CSMA var")):
        rows = [r for r in load_rows if int(r["csma"]) == csma]
        series(a1, {k[0]: v for k, v in summarize(rows, ["interval_s"], "pdr").items()}, color, label)
        series(a2, {k[0]: v for k, v in summarize(rows, ["interval_s"], "mean_latency_s").items() if v[0] is not None}, color, label)
    for a in (a1, a2):
        a.set_xscale("log", base=2)
        a.set_xticks([2, 4, 8, 16, 32])
        a.set_xticklabels(["2", "4", "8", "16", "32"])
    style(a1, "düğüm başına paket aralığı (sn); sola doğru yük artar", "paket teslim oranı (%)", "CSMA'sız ağ düşük yükte bile kayıp verir")
    a1.set_ylim(0, 105)
    style(a2, "düğüm başına paket aralığı (sn)", "ortalama gecikme (sn)", "Gecikme")
    a2.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOT_DIR, "sekil-yuk-pdr.png"), dpi=160)
    plt.close(fig)


def print_tables(rec_rows, load_rows):
    print("== J: iyileşme süresi (sn), HELLO periyodu taraması; ortalama ± std")
    rec = summarize(rec_rows, ["hello_period_s", "ack_detection"], "recovery_s")
    pdr = summarize(rec_rows, ["hello_period_s", "ack_detection"], "post_pdr")
    for (p, a), (m, s) in sorted(rec.items()):
        none = sum(1 for r in rec_rows if r["hello_period_s"] == p and r["ack_detection"] == a and r["recovery_s"] is None)
        txt = "iyileşmedi" if m is None else f"{m:6.1f} ± {s:5.1f}"
        print(f"periyot {p:2d} sn, zaman aşımı {3*p:3d} sn, ACK tespiti {'var' if a else 'yok'} | "
              f"iyileşme {txt} sn | arıza sonrası PDR %{pdr[(p, a)][0]:5.1f} | iyileşmeyen {none} | HELLO payı %{hello_duty(p):.2f}")
    print("== K: yük taraması (8 düğüm, her biri 10 paket)")
    keys = ["interval_s", "csma"]
    pd = summarize(load_rows, keys, "pdr")
    lt = summarize(load_rows, keys, "mean_latency_s")
    p95 = summarize(load_rows, keys, "p95_latency_s")
    for (i, c), (m, s) in sorted(pd.items()):
        print(f"aralık {i:2d} sn, CSMA {'var' if c else 'yok'} | PDR %{m:5.1f} ± {s:4.1f} | "
              f"gecikme ort {lt[(i, c)][0]:5.2f} sn, p95 {p95[(i, c)][0]:5.2f} sn")


if __name__ == "__main__":
    seeds = 3 if "hizli" in sys.argv else 10
    rec_rows = sweep_recovery(seeds)
    load_rows = sweep_load(seeds)
    print(write_csv("iyilesme_suresi.csv", [{k: ("" if v is None else v) for k, v in r.items()} for r in rec_rows]))
    print(write_csv("yuk_pdr.csv", [{k: ("" if v is None else v) for k, v in r.items()} for r in load_rows]))
    print_tables(rec_rows, load_rows)
    plots(rec_rows, load_rows)
    print("grafikler:", os.path.join(PLOT_DIR, "sekil-iyilesme-suresi.png"), "ve", os.path.join(PLOT_DIR, "sekil-yuk-pdr.png"))
