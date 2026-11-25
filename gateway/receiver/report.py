import struct

# Uygulama yükü (DATA paketinin içi, şifreli gider): tür, x, y (metre, gateway'e göre), pil %, kod, serbest metin
REPORT_FORMAT = ">BhhBB"
REPORT_BYTES = struct.calcsize(REPORT_FORMAT)

KIND_STATUS = 1
KIND_SOS = 2
KIND_SENSOR = 3
KIND_NAMES = {KIND_STATUS: "durum", KIND_SOS: "SOS", KIND_SENSOR: "sensör"}
MAX_TEXT = 24


def encode_report(kind, x, y, battery, code=0, text=""):
    raw = text.encode("utf-8")[:MAX_TEXT]
    return struct.pack(REPORT_FORMAT, kind, x, y, battery, code) + raw


def decode_report(payload):
    if len(payload) < REPORT_BYTES:
        raise ValueError("rapor çok kısa")
    kind, x, y, battery, code = struct.unpack(REPORT_FORMAT, payload[:REPORT_BYTES])
    if kind not in KIND_NAMES:
        raise ValueError(f"bilinmeyen rapor türü {kind}")
    if battery > 100:
        raise ValueError("pil yüzdesi 0-100 olmalı")
    return {"kind": kind, "x": x, "y": y, "battery": battery, "code": code,
            "text": payload[REPORT_BYTES:].decode("utf-8", errors="replace")}
