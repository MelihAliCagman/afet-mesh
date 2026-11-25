import math
import random
import statistics

import numpy as np

from sim.localization.ranging import audible, distance_from_rssi, measure_rssi
from sim.mesh_sim import Node


def multilaterate(anchors, dists):
    # En yakın çapa referans alınır; diğer çember denklemlerinden çıkarılınca denklemler doğrusal olur.
    k = min(range(len(dists)), key=lambda i: dists[i])
    xk, yk = anchors[k]
    rows, rhs = [], []
    for i, ((xi, yi), di) in enumerate(zip(anchors, dists)):
        if i == k:
            continue
        rows.append([2 * (xk - xi), 2 * (yk - yi)])
        rhs.append(di ** 2 - dists[k] ** 2 - xi ** 2 + xk ** 2 - yi ** 2 + yk ** 2)
    sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
    return float(sol[0]), float(sol[1])


def estimate(node, anchor_nodes, sigma, rng):
    pts, dists = [], []
    for a in anchor_nodes:
        r = measure_rssi(a, node, sigma, rng)
        if audible(r):
            pts.append((a.x, a.y))
            dists.append(distance_from_rssi(r))
    if len(pts) < 3:
        return None
    return multilaterate(pts, dists)


def anchor_set(name, side):
    corners = [(0.0, 0.0), (side, 0.0), (0.0, side), (side, side)]
    pts = {"3 çapa": corners[:3], "4 çapa": corners, "5 çapa": corners + [(side / 2, side / 2)]}[name]
    return [Node(100 + i, x, y) for i, (x, y) in enumerate(pts)]


def evaluate(anchors, side, sigma, trials, seed):
    rng = random.Random(seed)
    errs, missed = [], 0
    for _ in range(trials):
        n = Node(1, rng.uniform(0, side), rng.uniform(0, side))
        est = estimate(n, anchors, sigma, rng)
        if est is None:
            missed += 1
        else:
            errs.append(math.hypot(est[0] - n.x, est[1] - n.y))
    return errs, missed


if __name__ == "__main__":
    SIDE = 900.0
    TRIALS = 2000
    print(f"== Alan {SIDE:.0f} x {SIDE:.0f} m, her ayarda {TRIALS} rastgele konum; yalnızca duyulan çapalar (RSSI >= -123 dBm) kullanılır")
    for name in ("3 çapa", "4 çapa", "5 çapa"):
        anchors = anchor_set(name, SIDE)
        for sigma in (0, 2, 4, 6, 8):
            errs, missed = evaluate(anchors, SIDE, sigma, TRIALS, seed=7)
            if errs:
                e = sorted(errs)
                print(f"{name} | sigma {sigma} dB | konum bulunan %{100 * len(errs) / TRIALS:5.1f} | "
                      f"hata ort {statistics.mean(e):6.1f} m, medyan {e[len(e) // 2]:6.1f} m, p90 {e[int(0.9 * (len(e) - 1))]:6.1f} m")
            else:
                print(f"{name} | sigma {sigma} dB | konum bulunamadı")
