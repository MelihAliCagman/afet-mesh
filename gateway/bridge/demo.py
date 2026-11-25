import os
import secrets
import sys
import tempfile
import threading
import time

import httpx
import uvicorn

from gateway.bridge.bridge import Bridge, SimulatedCrash
from gateway.mockradio import MockRadio
from gateway.receiver.db import Database

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "remote-server"))
import server  # noqa: E402

PORT = 8791


class RemoteServer:
    """Gerçek bir HTTP sunucusu (uvicorn); durdurmak 'internet kesildi' demektir."""

    def __init__(self, db_path, key, port=PORT):
        self.db_path, self.key, self.port = db_path, key, port
        self.srv = None
        self.thread = None

    def start(self):
        cfg = uvicorn.Config(server.create_app(self.db_path, self.key), host="127.0.0.1", port=self.port, log_level="error")
        self.srv = uvicorn.Server(cfg)
        self.thread = threading.Thread(target=self.srv.run, daemon=True)
        self.thread.start()
        while not self.srv.started:
            time.sleep(0.05)

    def stop(self):
        self.srv.should_exit = True
        self.thread.join()


def main():
    tmp = tempfile.mkdtemp(prefix="afet-demo-")
    gw_path, remote_path = os.path.join(tmp, "gateway.db"), os.path.join(tmp, "remote.db")
    key = secrets.token_hex(16)  # her çalıştırmada rastgele; repoda anahtar yok
    remote = RemoteServer(remote_path, key)
    remote.start()
    db = Database(gw_path)
    radio = MockRadio(db, seed=3, report_period=10.0)
    http = httpx.Client(base_url=f"http://127.0.0.1:{PORT}")
    bridge = Bridge(Database(gw_path), http, key, clock=radio.clock)

    def remote_total():
        try:
            return http.get("/api/stats", headers={"X-API-Key": key}, timeout=2.0).json()["total"]
        except Exception:
            return None

    print("== Fırsatçı köprü demosu: 3x3 ızgara, her düğüm ~10 sn'de bir rapor")
    print("   t=120 sn internet kesilir, t=300 sn geri gelir, t=330 sn köprü yükleme sırasında çöker")
    print(f"{'t (sn)':>6} | {'köprü':<7} | {'kuyrukta':>8} | {'gateway DB':>10} | {'uzak sunucu':>11} | olay")
    crashed = False
    cut = False
    events = {120: "İNTERNET KESİLDİ", 300: "İNTERNET GERİ GELDİ", 330: "köprü çökmesi hazırlandı"}
    for t in range(0, 481, 10):
        note = events.get(t, "")
        if t == 120:
            remote.stop()
            cut = True
        if t == 300:
            remote.start()
            cut = False
        if t == 330:
            bridge.crash_after_post = lambda: True
        radio.run(10)
        try:
            state = bridge.step()
        except SimulatedCrash:
            crashed = True
            note = "KÖPRÜ ÇÖKTÜ (sunucu aldı, işaretleme yapılamadı); yeniden başlatıldı"
            bridge = Bridge(Database(gw_path), http, key, clock=radio.clock)
            state = bridge.step()
        if t % 30 == 0 or note:
            rt = remote_total()
            print(f"{t:>6} | {state:<7} | {db.pending_count():>8} | {db.message_count():>10} | "
                  f"{'ulaşılamıyor' if rt is None else rt:>11} | {note}")
    for _ in range(4):  # trafik durdu, kalan kuyruğu boşalt
        bridge.step()
    total_remote = remote_total()
    print("== Sonuç")
    print(f"gateway'e ulaşan mesaj: {db.message_count()} | uzak sunucuda kayıtlı: {total_remote} | kuyrukta kalan: {db.pending_count()}")
    print(f"çökme sonrası aynı mesajlar yeniden gönderildi mi (sunucunun bildirdiği çift): {bridge.stats['duplicates_reported']} "
          f"(yeniden başlatılan köprünün sayacı)")
    print("kayıp yok:", total_remote == db.message_count(), "| çift kayıt yok: sunucuda (gateway, uid) benzersiz")
    remote.stop()


if __name__ == "__main__":
    main()
