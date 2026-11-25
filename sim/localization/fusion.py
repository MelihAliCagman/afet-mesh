import math
import os
import random
import statistics

from sim.localization.multilat import anchor_set, multilaterate
from sim.localization.ranging import audible, distance_from_rssi
from sim.mesh_sim import Node, rssi

SIDE = 900.0
SPEED = 1.4
WAYPOINTS = [(150.0, 150.0), (750.0, 150.0), (750.0, 750.0), (150.0, 750.0), (150.0, 150.0)]
PERIMETER = 2400.0
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "olcumler")


def truth_at(t):
    # sabit hızla bir dikdörtgeni tekrar tekrar dolaşan gerçek yürüyüş yolu (1 sn = SPEED metre)
    left = (t * SPEED) % PERIMETER
    for (x0, y0), (x1, y1) in zip(WAYPOINTS, WAYPOINTS[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if left <= seg:
            f = left / seg
            return x0 + f * (x1 - x0), y0 + f * (y1 - y0)
        left -= seg
    return WAYPOINTS[-1]


def simulate(sigma, seed, duration=600, q=1.0, rho=0.95, head_white=math.radians(2.0),
             bias_walk=math.radians(0.2), speed_noise=0.05):
    rng = random.Random(seed)
    anchors = anchor_set("5 çapa", SIDE)
    shadow = [rng.gauss(0.0, sigma) for _ in anchors]
    r_meas = 30.0 * sigma + 30.0
    truth = [truth_at(t) for t in range(duration + 1)]

    dr = list(truth[0])
    kf = list(truth[0])
    p = 10.0 ** 2
    raw = None
    bias = 0.0
    out = {"truth": truth, "dr": [tuple(dr)], "raw": [], "kf": [tuple(kf)],
           "err_dr": [0.0], "err_raw": [None], "err_kf": [0.0]}

    for t in range(1, duration + 1):
        dx, dy = truth[t][0] - truth[t - 1][0], truth[t][1] - truth[t - 1][1]
        step = math.hypot(dx, dy)
        heading = math.atan2(dy, dx) + bias + rng.gauss(0.0, head_white)
        bias += rng.gauss(0.0, bias_walk)
        step_meas = step * (1.0 + rng.gauss(0.0, speed_noise))
        ux, uy = step_meas * math.cos(heading), step_meas * math.sin(heading)

        dr[0] += ux
        dr[1] += uy
        kf[0] += ux
        kf[1] += uy
        p += q ** 2

        node = Node(1, truth[t][0], truth[t][1])
        pts, dists = [], []
        for i, a in enumerate(anchors):
            shadow[i] = rho * shadow[i] + math.sqrt(1.0 - rho * rho) * rng.gauss(0.0, sigma)
            r = rssi(a, node) + shadow[i]
            if audible(r):
                pts.append((a.x, a.y))
                dists.append(distance_from_rssi(r))
        if len(pts) >= 3:
            raw = multilaterate(pts, dists)
            k = p / (p + r_meas ** 2)
            kf[0] += k * (raw[0] - kf[0])
            kf[1] += k * (raw[1] - kf[1])
            p = (1.0 - k) * p

        out["dr"].append(tuple(dr))
        out["kf"].append(tuple(kf))
        out["raw"].append(raw)
        out["err_dr"].append(math.hypot(dr[0] - truth[t][0], dr[1] - truth[t][1]))
        out["err_kf"].append(math.hypot(kf[0] - truth[t][0], kf[1] - truth[t][1]))
        out["err_raw"].append(None if raw is None else math.hypot(raw[0] - truth[t][0], raw[1] - truth[t][1]))
    return out


def average(sigma, seeds, duration=600, **kw):
    runs = [simulate(sigma, s, duration, **kw) for s in range(seeds)]
    res = {}
    for name in ("err_dr", "err_raw", "err_kf"):
        series = []
        for t in range(duration + 1):
            vals = [r[name][t] for r in runs if r[name][t] is not None]
            series.append(statistics.mean(vals) if vals else None)
        res[name] = series
    return res


def mean_of(series, lo=0, hi=None):
    vals = [v for v in series[lo:hi] if v is not None]
    return statistics.mean(vals) if vals else float("nan")


def plots(sigma=4):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BLUE, ORANGE, AQUA, INK, MUTED, GRIDC = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e6e5e1"
    kay = math.radians(0.5)
    one = simulate(sigma, 3, 600, bias_walk=kay)
    avg = average(sigma, 12, 3600, bias_walk=kay)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.8, 4.2), facecolor="#fcfcfb")
    for ax in (a1, a2):
        ax.set_facecolor("#fcfcfb")
        ax.grid(color=GRIDC, linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#b9b8b2")
        ax.tick_params(colors=MUTED, labelsize=9)

    tx, ty = zip(*one["truth"])
    a1.plot(tx, ty, color=INK, linewidth=2.2, linestyle="--", label="gerçek yol")
    raw = [r for r in one["raw"] if r is not None]
    a1.scatter([r[0] for r in raw], [r[1] for r in raw], s=4, color=ORANGE, alpha=0.45, linewidths=0, label="RSSI konumu")
    dx, dy = zip(*one["dr"])
    kx, ky = zip(*one["kf"])
    a1.plot(dx, dy, color=BLUE, linewidth=1.6, label="yalnız IMU")
    a1.plot(kx, ky, color=AQUA, linewidth=1.8, label="Kalman")
    for a in anchor_set("5 çapa", SIDE):
        a1.plot(a.x, a.y, marker="s", color=MUTED, markersize=6)
    a1.set_aspect("equal")
    a1.set_xlim(-50, SIDE + 50)
    a1.set_ylim(-50, SIDE + 50)
    a1.set_xlabel("x (m)", color=MUTED, fontsize=9)
    a1.set_ylabel("y (m)", color=MUTED, fontsize=9)
    a1.set_title(f"İlk 600 sn, tek koşu (sigma {sigma} dB); kareler = çapalar", color=INK, fontsize=10.5, loc="left")
    a1.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=4)

    def smooth(v, w=60):
        out = []
        for i in range(len(v)):
            win = [x for x in v[max(0, i - w + 1):i + 1] if x is not None]
            out.append(statistics.mean(win) if win else None)
        return out

    for name, color, label, dy in (("err_dr", BLUE, "yalnız IMU", 8), ("err_raw", ORANGE, "yalnız RSSI", 8), ("err_kf", AQUA, "Kalman", -14)):
        v = smooth(avg[name])
        pts = [(t, x) for t, x in enumerate(v) if x is not None]
        a2.plot([q[0] for q in pts], [q[1] for q in pts], color=color, linewidth=2)
        a2.annotate(label, pts[-1], textcoords="offset points", xytext=(-4, dy), ha="right", color=INK, fontsize=9)
    a2.set_xlabel("zaman (sn)", color=MUTED, fontsize=9)
    a2.set_ylabel("konum hatası (m), 12 koşu ve 60 sn ortalaması", color=MUTED, fontsize=9)
    a2.set_title("Kalman hatayı sınırda tutar, IMU kayar (60 dk)", color=INK, fontsize=10.5, loc="left")
    a2.set_ylim(bottom=0)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "sekil-konum-hatasi.png")
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


if __name__ == "__main__":
    SEEDS = 30
    print(f"== A: Yürüyen düğüm, 600 sn, 1,4 m/s, {SEEDS} koşu ortalaması; başlangıç noktası biliniyor (IMU ve Kalman için)")
    print("   IMU: adım uzunluğu %5 gürültü, yön gürültüsü 2 derece + yavaş kayan sapma (0,2 derece/adım); gölgeleme zamanla ilişkili (rho 0,95)")
    for sigma in (2, 4, 6, 8):
        a = average(sigma, SEEDS)
        print(f"sigma {sigma} dB | ortalama hata: IMU {mean_of(a['err_dr']):6.1f} m, RSSI {mean_of(a['err_raw']):6.1f} m, "
              f"Kalman {mean_of(a['err_kf']):6.1f} m")
    print("== B: IMU sapması ve süre taraması (sigma 4 dB, 10 koşu); Kalman iki ayarla: q = 0,3 (IMU'ya güvenir) ve q = 1,0")
    for dur in (600, 1800, 3600):
        for drift in (0.2, 1.0):
            kw = {"bias_walk": math.radians(drift)}
            a1 = average(4, 10, dur, q=0.3, **kw)
            a2 = average(4, 10, dur, q=1.0, **kw)
            print(f"süre {dur:4d} sn, sapma {drift} derece/adım | IMU {mean_of(a1['err_dr']):6.1f} m | RSSI {mean_of(a1['err_raw']):6.1f} m | "
                  f"Kalman(q=0,3) {mean_of(a1['err_kf']):6.1f} m | Kalman(q=1) {mean_of(a2['err_kf']):6.1f} m")
    print("grafik:", plots(4))
