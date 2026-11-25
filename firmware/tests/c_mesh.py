"""C protokol düğümlerini Python simülasyon ortamına (olay motoru + radyo ortamı) bağlayan köprü."""
import ctypes as C
import random

from sim.mesh_sim import Node
from sim.radio import Radio
from sim.engine import Simulator
from sim.wire import decode, encode

NEVER = 0xFFFFFFFF
u8, u16, u32, vp = C.c_uint8, C.c_uint16, C.c_uint32, C.c_void_p


class NodeCfg(C.Structure):
    _fields_ = [("gateway_id", u8), ("hello_period_ms", u32), ("timeout_ms", u32), ("ack_timeout_ms", u32),
                ("max_retry", u8), ("csma", u8), ("fast_detect", u8), ("rerr_on", u8), ("data_ttl", u8),
                ("backoff_slot_ms", u32), ("max_backoff", u8), ("counter_block", u32)]


TX = C.CFUNCTYPE(None, vp, C.POINTER(u8), C.c_size_t)
BUSY = C.CFUNCTYPE(C.c_int, vp)
RAND = C.CFUNCTYPE(u32, vp)
DELIVER = C.CFUNCTYPE(None, vp, u8, C.POINTER(u8), C.c_size_t, u32, u32)
PERSIST = C.CFUNCTYPE(None, vp, u32)


class RadioIf(C.Structure):
    _fields_ = [("tx", TX), ("channel_busy", BUSY), ("rand32", RAND), ("ctx", vp)]


class Stats(C.Structure):
    _fields_ = [(n, u32) for n in ("tx_frames", "rx_frames", "acked", "retx", "backoffs", "drop_ttl", "drop_no_route",
                                   "drop_retry", "drop_pending_full", "drop_security", "delivered", "sec_alarms")]


def setup_node_api(lib):
    lib.afet_sizeof_node.restype = C.c_size_t
    lib.afet_sizeof_node_cfg.restype = C.c_size_t
    lib.afet_node_default_cfg.argtypes = [C.POINTER(NodeCfg)]
    lib.afet_node_init.argtypes = [vp, u8, u8, C.POINTER(NodeCfg), C.POINTER(RadioIf), C.c_char_p, u32, PERSIST, vp, u32]
    lib.afet_node_set_deliver.argtypes = [vp, DELIVER, vp]
    lib.afet_node_on_rx.argtypes = [vp, C.c_char_p, C.c_size_t, C.c_float, u32]
    lib.afet_node_tick.argtypes = [vp, u32]
    lib.afet_node_send_data.argtypes = [vp, C.c_char_p, C.c_size_t, u32]
    lib.afet_node_send_data.restype = C.c_int
    lib.afet_node_next_wakeup.argtypes = [vp]
    lib.afet_node_next_wakeup.restype = u32
    lib.afet_node_kill.argtypes = [vp]
    lib.afet_node_get.argtypes = [vp, C.POINTER(u8), C.POINTER(u8), C.POINTER(u16), C.POINTER(u32), C.POINTER(Stats)]
    return lib


class CNode:
    def __init__(self, lib, node, sim, radio, key, seed, **cfg_over):
        self.lib, self.node, self.sim, self.radio = lib, node, sim, radio
        self.id = node.node_id
        self.rng = random.Random(seed * 1000 + self.id)
        self.buf = C.create_string_buffer(lib.afet_sizeof_node())
        self.delivered = []
        self.flash = {}
        self.armed = set()
        cfg = NodeCfg()
        lib.afet_node_default_cfg(C.byref(cfg))
        for k, v in cfg_over.items():
            setattr(cfg, k, v)
        self._tx = TX(self._on_tx)
        self._busy = BUSY(lambda _c: 1 if self.radio.busy(self.node) else 0)
        self._rand = RAND(lambda _c: self.rng.getrandbits(32))
        self._deliver = DELIVER(self._on_deliver)
        self._persist = PERSIST(lambda _c, r: self.flash.__setitem__("ctr", r))
        rif = RadioIf(self._tx, self._busy, self._rand, None)
        lib.afet_node_init(self.buf, self.id, 1 if node.is_gateway else 0, C.byref(cfg), C.byref(rif), key, 0,
                           self._persist, None, 0)
        lib.afet_node_set_deliver(self.buf, self._deliver, None)
        radio.attach(self.id, self._on_air)
        self._arm()

    # --- zaman ---
    def now_ms(self):
        return int(round(self.sim.now * 1000))

    def _arm(self):
        t = self.lib.afet_node_next_wakeup(self.buf)
        if t != NEVER and t not in self.armed:
            self.armed.add(t)
            self.sim.schedule(max(0, t - self.now_ms()) / 1000.0, lambda t=t: self._fire(t))

    def _fire(self, t):
        self.armed.discard(t)
        self.lib.afet_node_tick(self.buf, self.now_ms())
        self._arm()

    # --- radyo ---
    def _on_tx(self, _ctx, frame, length):
        raw = C.string_at(frame, length)
        self.radio.transmit(self.node, decode(raw))

    def _on_air(self, packet, rssi):
        raw = encode(packet)
        self.lib.afet_node_on_rx(self.buf, raw, len(raw), rssi, self.now_ms())
        self._arm()

    def _on_deliver(self, _ctx, src, payload, length, counter, now_ms):
        self.delivered.append((src, C.string_at(payload, length), counter, now_ms))

    def inject(self, raw, rssi=-100.0):
        """Radyoyu atlayıp doğrudan düğüme ham bayt verir (saldırı denemeleri için)."""
        self.lib.afet_node_on_rx(self.buf, raw, len(raw), rssi, self.now_ms())
        self._arm()

    # --- uygulama ---
    def send_data(self, payload):
        ok = self.lib.afet_node_send_data(self.buf, payload, len(payload), self.now_ms())
        self._arm()
        return bool(ok)

    def kill(self):
        self.lib.afet_node_kill(self.buf)

    def info(self):
        v, nh, m, sw, st = u8(), u8(), u16(), u32(), Stats()
        self.lib.afet_node_get(self.buf, C.byref(v), C.byref(nh), C.byref(m), C.byref(sw), C.byref(st))
        return {"route": (nh.value, m.value) if v.value else None, "switches": sw.value, "stats": st}


def build_c_mesh(lib, positions, seed, key, loss=0.0, collide=False, csma=False, **cfg):
    sim = Simulator()
    nodes = [Node(i + 1, x, y, is_gateway=(i == 0)) for i, (x, y) in enumerate(positions)]
    radio = Radio(sim, nodes, loss=loss, seed=seed, collide=collide)
    mesh = [CNode(lib, n, sim, radio, key, seed, csma=1 if csma else 0, **cfg) for n in nodes]
    return sim, mesh, radio


def c_path(mesh, start):
    by_id = {m.id: m for m in mesh}
    path = [start]
    while not by_id[path[-1]].node.is_gateway:
        r = by_id[path[-1]].info()["route"]
        if r is None:
            return path, "yol yok"
        if r[0] in path:
            return path + [r[0]], "DONGU"
        path.append(r[0])
    return path, "tamam"
