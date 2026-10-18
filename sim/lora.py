import math

def symbol_time(sf,bw):
    return (2**sf)/bw

def preamble_time(sf, bw, n_preamble=8):
    return (n_preamble + 4.25) * symbol_time(sf, bw)

def payload_symbols(payload_bytes, sf, bw, cr=1, crc=True, implicit_header=False):
    de = 1 if symbol_time(sf, bw) > 0.016 else 0
    ih = 1 if implicit_header else 0
    pay = 8 * payload_bytes - 4 * sf + 28 + 16 * int(crc) - 20 * ih
    return 8 + max(math.ceil(pay / (4 * (sf - 2 * de))) * (cr + 4), 0)

def airtime(payload_bytes, sf, bw=125000, cr=1, n_preamble=8, crc=True, implicit_header=False):
    n = payload_symbols(payload_bytes, sf, bw, cr, crc, implicit_header)
    return preamble_time(sf, bw, n_preamble) + n * symbol_time(sf, bw)

class DutyCycle:
    def __init__(self, limit=0.01, window=3600.0):
        self.limit = limit
        self.window = window
        self._log = []

    def used(self, now):
        start = now - self.window
        return sum(d for t, d in self._log if t > start)

    def can_send(self, now, duration):
        return self.used(now) + duration <= self.limit * self.window

    def record(self, now, duration):
        self._log.append((now, duration))


if __name__ == "__main__":
    dc = DutyCycle()
    t = 0.0
    sent = 0
    d = airtime(20, 12)
    while dc.can_send(t, d):
        dc.record(t, d)
        sent += 1
        t += d
    print(sent, round(dc.used(t), 3))
    print(dc.can_send(t, d))
    print(dc.can_send(t + 3600, d))
