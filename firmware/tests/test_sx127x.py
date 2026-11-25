"""SX127x sürücüsü: sahte çip (yazmaç düzeyinde) ile bilgisayarda sınanır."""
import ctypes as C
import glob
import os
import subprocess

import pytest

from conftest import BUILD, CORE, HERE, find_gcc

DRV = os.path.join(HERE, "..", "drivers", "sx127x")


@pytest.fixture(scope="module")
def m():
    gcc = find_gcc()
    if not gcc:
        pytest.skip("gcc bulunamadı")
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "libsx127x.dll" if os.name == "nt" else "libsx127x.so")
    cmd = [gcc, "-shared", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I", CORE, "-I", DRV, "-o", out,
           os.path.join(DRV, "sx127x.c"), os.path.join(HERE, "sx127x_mock.c"), os.path.join(CORE, "lora_time.c"), "-lm"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    lib = C.CDLL(out)
    lib.mock_inject_rx.argtypes = [C.c_char_p, C.c_int, C.c_int, C.c_int, C.c_int]
    lib.t_init.argtypes = [C.c_uint32, C.c_int, C.c_uint32, C.c_int, C.c_int]
    lib.t_send.argtypes = [C.c_char_p, C.c_int]
    lib.t_poll.argtypes = [C.c_char_p, C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_float)]
    lib.t_airtime.restype = C.c_uint
    return lib


OK, ERR_CHIP, ERR_PARAM, ERR_BUSY = 0, -1, -2, -3
F = 433175000


def poll(m, cap=255):
    buf = C.create_string_buffer(cap)
    n = C.c_int()
    r = C.c_float()
    ev = m.t_poll(buf, cap, C.byref(n), C.byref(r))
    return ev, buf.raw[: n.value], r.value


def test_init_writes_registers(m):
    m.mock_set_version(-1)
    assert m.t_init(F, 7, 125000, 5, 10) == OK
    assert m.mock_reset_count() >= 1
    # Frf = 433,175e6 * 2^19 / 32e6
    frf = int(F * 2**19 / 32e6)
    assert (m.mock_reg(6), m.mock_reg(7), m.mock_reg(8)) == (frf >> 16, (frf >> 8) & 255, frf & 255)
    assert m.mock_reg(0x01) & 0x80  # LoRa modu
    assert m.mock_reg(0x1D) == (7 << 4) | (1 << 1)  # 125 kHz, 4/5, açık başlık
    assert m.mock_reg(0x1E) == (7 << 4) | 0x04  # SF7, CRC açık
    assert m.mock_reg(0x39) == 0x12


def test_low_data_rate_optimize_for_sf12(m):
    m.t_init(F, 12, 125000, 5, 10)
    assert m.mock_reg(0x26) & 0x08  # SF12/125 kHz: sembol 32 ms > 16 ms
    m.t_init(F, 7, 125000, 5, 10)
    assert not (m.mock_reg(0x26) & 0x08)


def test_power_is_clamped_to_legal_limit(m):
    m.t_init(F, 7, 125000, 5, 18)  # istenen 18 dBm (modülün azami gücü), yasal sınır 10 dBm
    assert m.mock_reg(0x09) == 0x80 | (10 - 2)
    assert m.t_power(20) == 10
    assert m.t_power(-5) == 2
    assert m.mock_reg(0x09) == 0x80 | 0


def test_chip_not_found(m):
    m.mock_set_version(0x00)  # kablo/besleme hatası: sürüm yazmacı okunamıyor
    assert m.t_init(F, 7, 125000, 5, 10) == ERR_CHIP
    m.mock_set_version(-1)


@pytest.mark.parametrize("freq,sf,bw,cr", [
    (433050000, 7, 125000, 5),  # alt kenar: bandın yarısı 433,05'in altına taşar
    (434790000, 7, 125000, 5),  # üst kenar
    (868100000, 7, 125000, 5),  # başka bant
    (F, 6, 125000, 5),          # SF6 desteklenmiyor
    (F, 13, 125000, 5),
    (F, 7, 100000, 5),          # geçersiz bant genişliği
    (F, 7, 125000, 4),          # geçersiz kodlama oranı
])
def test_invalid_params_rejected(m, freq, sf, bw, cr):
    assert m.t_init(freq, sf, bw, cr, 10) == ERR_PARAM


def test_legal_band_edges_accepted(m):
    assert m.t_init(433050000 + 62500, 7, 125000, 5, 10) == OK
    assert m.t_init(434790000 - 62500, 7, 125000, 5, 10) == OK


def test_send_and_tx_done(m):
    m.t_init(F, 7, 125000, 5, 10)
    frame = bytes(range(1, 33))
    assert m.t_send(frame, len(frame)) == OK
    assert m.mock_tx_len() == 32
    assert bytes(m.mock_tx_byte(i) for i in range(32)) == frame
    assert m.mock_reg(0x01) & 0x07 == 3  # TX modu
    assert m.t_send(frame, len(frame)) == ERR_BUSY  # yayın bitmeden ikinci yayın reddedilir
    ev, _, _ = poll(m)
    assert ev == 1  # TX_DONE
    assert m.mock_reg(0x01) & 0x07 == 5  # sürekli alıma döndü
    assert m.t_send(frame, len(frame)) == OK  # artık yeniden yayınlanabilir


def test_send_rejects_empty_and_oversize(m):
    m.t_init(F, 7, 125000, 5, 10)
    assert m.t_send(b"x", 0) == ERR_PARAM
    assert m.t_send(b"x" * 256, 256) == ERR_PARAM


def test_receive_packet_and_rssi(m):
    m.t_init(F, 7, 125000, 5, 10)
    m.t_rx()
    assert poll(m)[0] == 0
    pkt = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE])
    m.mock_inject_rx(pkt, len(pkt), 60, 20, 1)  # PktRssi 60 -> -157 + 60 = -97 dBm; SNR +5 dB
    ev, data, rssi = poll(m)
    assert ev == 2 and data == pkt
    assert rssi == pytest.approx(-97.0)
    assert poll(m)[0] == 0  # bayrak temizlendi, aynı paket iki kez gelmez


def test_rssi_corrected_for_negative_snr(m):
    m.t_init(F, 7, 125000, 5, 10)
    m.mock_inject_rx(b"ab", 2, 20, 0xF0, 1)  # SNR = -16/4 = -4 dB
    ev, _, rssi = poll(m)
    assert ev == 2 and rssi == pytest.approx(-157 + 20 - 4)


def test_crc_error_is_reported_and_dropped(m):
    m.t_init(F, 7, 125000, 5, 10)
    m.mock_inject_rx(b"bad", 3, 50, 0, 0)
    assert poll(m)[0] == 3
    assert poll(m)[0] == 0


def test_airtime_matches_python_formula(m):
    from sim.lora import airtime
    m.t_init(F, 7, 125000, 5, 10)
    assert m.t_airtime(32) == pytest.approx(airtime(32, 7, 125000, 1, 8, True, False) * 1e6, abs=2)
