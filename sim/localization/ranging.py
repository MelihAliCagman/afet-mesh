import random

from sim.mesh_sim import PATH_EXPONENT, PATH_LOSS_D0_DB, SENSITIVITY_DBM, TX_POWER_DBM, Node, distance, rssi


def distance_from_rssi(r, n=PATH_EXPONENT, p_tx=TX_POWER_DBM, pl0=PATH_LOSS_D0_DB):
    return 10 ** ((p_tx - pl0 - r) / (10 * n))


def measure_rssi(a, b, sigma, rng):
    return rssi(a, b) + (rng.gauss(0.0, sigma) if sigma else 0.0)


def audible(r):
    return r >= SENSITIVITY_DBM


if __name__ == "__main__":
    a, b = Node(1, 0.0, 0.0), Node(2, 300.0, 0.0)
    r = rssi(a, b)
    print("gerçek mesafe", distance(a, b), "RSSI", round(r, 2), "tersten mesafe", round(distance_from_rssi(r), 2))

    rng = random.Random(1)
    print("== 300 m'de gölgeleme gürültüsü (sigma, dB) ve tahmin edilen mesafe")
    for sigma in (0, 2, 4, 6, 8):
        est = sorted(distance_from_rssi(measure_rssi(a, b, sigma, rng)) for _ in range(2000))
        carpan = 10 ** (sigma / (10 * PATH_EXPONENT))
        print(f"sigma {sigma} dB | tahmin: %5-%95 aralığı {est[100]:6.0f} - {est[1900]:6.0f} m | "
              f"medyan {est[1000]:6.0f} m | 1 sigma çarpanı x{carpan:.2f}")
