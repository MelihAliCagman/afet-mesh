import os
import time

import httpx

from gateway.bridge.bridge import Bridge
from gateway.receiver.db import Database


def main():
    """Köprüyü sürekli çalıştırır (Pi'de systemd hizmeti). Ayarlar ortam değişkenlerinden okunur."""
    url = os.environ.get("REMOTE_SERVER_URL")
    key = os.environ.get("REMOTE_API_KEY")
    if not url or not key:
        raise SystemExit("REMOTE_SERVER_URL ve REMOTE_API_KEY tanımlı olmalı (.env dosyası)")
    db = Database(os.environ.get("GATEWAY_DB_PATH", "gateway.db"))
    bridge = Bridge(db, httpx.Client(base_url=url), key, gateway_id=os.environ.get("GATEWAY_ID", "gw-1"))
    while True:
        state = bridge.step()
        print(f"köprü {state} | kuyrukta {db.pending_count()} | gönderilen {bridge.stats['uploaded']}", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
