import ctypes as C
import os
import random

import pytest

MAX_FRAME = 8 + 64 + 4


class Deframer(C.Structure):
    _fields_ = [("buf", C.c_uint8 * MAX_FRAME), ("n", C.c_size_t), ("esc", C.c_uint8), ("overflow", C.c_uint8)]


@pytest.fixture(scope="module")
def L(lib):
    lib.afet_frame_encode.argtypes = [C.c_char_p, C.c_size_t, C.c_char_p, C.c_size_t]
    lib.afet_frame_encode.restype = C.c_size_t
    lib.afet_deframer_init.argtypes = [C.POINTER(Deframer)]
    lib.afet_deframer_push.argtypes = [C.POINTER(Deframer), C.c_uint8, C.POINTER(C.POINTER(C.c_uint8)), C.POINTER(C.c_size_t)]
    lib.afet_deframer_push.restype = C.c_int
    return lib


def encode(L, data, cap=400):
    out = C.create_string_buffer(cap)
    n = L.afet_frame_encode(data, len(data), out, cap)
    return out.raw[:n]


def feed(L, stream):
    d = Deframer()
    L.afet_deframer_init(C.byref(d))
    frames = []
    for b in stream:
        fp, ln = C.POINTER(C.c_uint8)(), C.c_size_t()
        if L.afet_deframer_push(C.byref(d), b, C.byref(fp), C.byref(ln)):
            frames.append(bytes(fp[i] for i in range(ln.value)))
    return frames


def slip_ref(data):
    out = bytearray([0xC0])
    for b in data:
        out += {0xC0: b"\xdb\xdc", 0xDB: b"\xdb\xdd"}.get(b, bytes([b]))
    out.append(0xC0)
    return bytes(out)


def test_encode_matches_reference_and_roundtrips(L):
    rng = random.Random(1)
    for _ in range(300):
        data = bytes(rng.choice([0xC0, 0xDB, 0xDC, 0xDD, rng.randrange(256)]) for _ in range(rng.randint(1, 76)))
        enc = encode(L, data)
        assert enc == slip_ref(data)
        assert feed(L, enc) == [data]


def test_back_to_back_frames_and_shared_delimiters(L):
    a, b, c = b"\x01\x02\x03", bytes([0xC0, 0xDB, 0x00]), b"\xff" * 20
    stream = encode(L, a) + encode(L, b) + b"\xc0\xc0" + encode(L, c)
    assert feed(L, stream) == [a, b, c]


def test_noise_between_frames_does_not_break_resync(L):
    rng = random.Random(2)
    frames = [os.urandom(rng.randint(12, 60)) for _ in range(40)]
    stream = b""
    for f in frames:
        stream += bytes(rng.choice([0x00, 0x55, 0xAA]) for _ in range(rng.randint(0, 5))) + b"\xc0" + encode(L, f)
    got = feed(L, stream)
    assert [g for g in got if g in frames] == frames  # her gerçek kare kurtarıldı (gürültü eklenmiş kareler atılabilir)


def test_overflow_and_bad_escape_are_dropped_then_recover(L):
    big = bytes([0x11]) * 200
    good = b"\x01\x02\x03\x04"
    assert feed(L, encode(L, big, 500) + encode(L, good)) == [good]
    bad_escape = b"\xc0\x01\xdb\x99\x02\xc0"
    assert feed(L, bad_escape + encode(L, good)) == [good]
    assert feed(L, b"\xc0\x01\x02\xdb\xc0" + encode(L, good)) == [good]  # kare ESC ile bitti


def test_encode_reports_overflow_of_output_buffer(L):
    assert L.afet_frame_encode(b"\xc0" * 10, 10, C.create_string_buffer(10), 10) == 0
