import ctypes as C

MAX_PAYLOAD = 64


class Packet(C.Structure):
    _fields_ = [("src", C.c_uint8), ("dst", C.c_uint8), ("next_hop", C.c_uint8), ("ptype", C.c_uint8),
                ("seq", C.c_uint16), ("ttl", C.c_uint8), ("last_hop", C.c_uint8), ("payload_len", C.c_uint8),
                ("payload", C.c_uint8 * MAX_PAYLOAD), ("tag", C.c_uint8 * 4)]


PERSIST = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32)
STATUS = ["ok", "dup", "replay", "regression", "jump", "bad_tag", "no_space"]


def setup(lib):
    vp, u8, u16, u32 = C.c_void_p, C.c_uint8, C.c_uint16, C.c_uint32
    lib.afet_wire_encode.argtypes = [C.POINTER(Packet), C.c_char_p, C.c_size_t]
    lib.afet_wire_decode.argtypes = [C.c_char_p, C.c_size_t, C.POINTER(Packet)]
    lib.afet_ccm_init.argtypes = [vp, C.c_char_p]
    for f in ("afet_ccm_seal", "afet_ccm_open"):
        getattr(lib, f).restype = C.c_int
    lib.afet_ccm_seal.argtypes = [vp, C.c_char_p, C.c_char_p, C.c_size_t, C.c_char_p, C.c_size_t, C.c_char_p, C.c_char_p]
    lib.afet_ccm_open.argtypes = [vp, C.c_char_p, C.c_char_p, C.c_size_t, C.c_char_p, C.c_size_t, C.c_char_p, C.c_char_p]
    lib.afet_sender_init.argtypes = [vp, C.c_char_p, u8, u32, u32, PERSIST, vp]
    lib.afet_sender_seal.argtypes = [vp, C.POINTER(Packet), C.POINTER(u32)]
    lib.afet_receiver_init.argtypes = [vp, C.c_char_p]
    lib.afet_receiver_open.argtypes = [vp, C.POINTER(Packet), u32, C.POINTER(u8), C.POINTER(u32)]
    lib.afet_receiver_open.restype = C.c_int
    for n in ("sender", "receiver", "routing", "duty"):
        getattr(lib, f"afet_sizeof_{n}").restype = C.c_size_t
    lib.afet_routing_init.argtypes = [vp, u8, u32]
    lib.afet_routing_update.argtypes = [vp, u8, u16, u8, u8, C.c_float, u32]
    lib.afet_routing_remove_neighbor.argtypes = [vp, u8, u32]
    lib.afet_routing_select.argtypes = [vp, u32]
    lib.afet_routing_get.argtypes = [vp, C.POINTER(u8), C.POINTER(u8), C.POINTER(u16), C.POINTER(u16), C.POINTER(u32)]
    lib.afet_seq_newer.argtypes = [u16, u16]
    lib.afet_link_cost.argtypes = [C.c_float]
    lib.afet_link_cost.restype = u8
    lib.afet_lora_airtime.argtypes = [C.c_int] * 7
    lib.afet_lora_airtime.restype = C.c_double
    lib.afet_duty_init.argtypes = [vp, u32, u32]
    lib.afet_duty_used_us.argtypes = [vp, u32]
    lib.afet_duty_used_us.restype = C.c_uint64
    lib.afet_duty_can_send.argtypes = [vp, u32, u32]
    lib.afet_duty_record.argtypes = [vp, u32, u32]
    return lib


def buf(lib, kind):
    return C.create_string_buffer(getattr(lib, f"afet_sizeof_{kind}")())


def to_c(p):
    """sim.packet.Packet -> C yapısı"""
    c = Packet(p.src, p.dst, p.next_hop, p.ptype.value, p.seq, p.ttl, p.last_hop, len(p.payload))
    C.memmove(c.payload, p.payload, len(p.payload))
    C.memmove(c.tag, p.tag.ljust(4, b"\x00"), 4)
    return c


def payload_of(c):
    return bytes(c.payload[: c.payload_len])


def tag_of(c):
    return bytes(c.tag)
