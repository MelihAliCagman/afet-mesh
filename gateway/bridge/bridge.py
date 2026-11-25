import time


class SimulatedCrash(Exception):
    """Testler için: yükleme başarılı olduktan sonra, kayıt işaretlenmeden süreç ölür."""


class ConnectivityMonitor:
    """Bağlantı izleyici: art arda başarılı/başarısız yoklamalara göre ONLINE/OFFLINE (histerezis)."""

    def __init__(self, probe, up_after=2, down_after=2):
        self.probe = probe
        self.up_after = up_after
        self.down_after = down_after
        self.state = "OFFLINE"
        self.ok_streak = 0
        self.fail_streak = 0

    def check(self):
        if self.probe():
            self.ok_streak += 1
            self.fail_streak = 0
            if self.state == "OFFLINE" and self.ok_streak >= self.up_after:
                self.state = "ONLINE"
        else:
            self.fail_streak += 1
            self.ok_streak = 0
            if self.state == "ONLINE" and self.fail_streak >= self.down_after:
                self.state = "OFFLINE"
        return self.state


class Bridge:
    """Fırsatçı köprü: internet varken kalıcı kuyruktaki (outbox) mesajları uzak sunucuya toplu yollar.
    Mesaj ancak sunucu 'aldım' dedikten sonra işaretlenir; arada çökme olursa aynı mesaj tekrar gider,
    uzak sunucu (gateway, uid) ile çift kaydı engeller. Böylece 'en az bir kez' gönderim 'tam bir kez' kayda dönüşür."""

    def __init__(self, db, http, api_key, gateway_id="gw-1", batch=50, clock=time.time, up_after=2, down_after=2):
        self.db = db
        self.http = http
        self.api_key = api_key
        self.gateway_id = gateway_id
        self.batch = batch
        self.clock = clock
        self.monitor = ConnectivityMonitor(self._probe, up_after, down_after)
        self.fails = 0
        self.next_try = 0.0
        self.stats = {"batches": 0, "uploaded": 0, "duplicates_reported": 0, "failures": 0}
        self.crash_after_post = None

    def _probe(self):
        try:
            return self.http.get("/health", timeout=2.0).status_code == 200
        except Exception:
            return False

    def step(self):
        """Bir tur: bağlantıyı yokla, ONLINE ise ve bekleme süresi dolduysa kuyruğu boşalt."""
        now = self.clock()
        state = self.monitor.check()
        if state != "ONLINE" or now < self.next_try:
            return state
        while True:
            rows = self.db.pending(self.batch)
            if not rows:
                break
            if not self._upload(rows, now):
                self.fails += 1
                self.next_try = now + min(2 ** self.fails, 60)  # üstel geri çekilme, en çok 60 sn
                break
            self.fails = 0
        return state

    def _upload(self, rows, now):
        uids = [r["uid"] for r in rows]
        try:
            r = self.http.post("/ingest", json={"gateway": self.gateway_id, "messages": [x["body"] for x in rows]},
                               headers={"X-API-Key": self.api_key}, timeout=5.0)
            if r.status_code != 200:
                raise RuntimeError(f"sunucu {r.status_code} döndü")
            info = r.json()
        except Exception as e:
            self.stats["failures"] += 1
            self.db.mark_failed(uids, repr(e)[:200])
            return False
        if self.crash_after_post is not None and self.crash_after_post():
            raise SimulatedCrash()
        self.db.mark_sent(uids, now)
        self.stats["batches"] += 1
        self.stats["uploaded"] += len(uids)
        self.stats["duplicates_reported"] += info.get("duplicates", 0)
        return True
