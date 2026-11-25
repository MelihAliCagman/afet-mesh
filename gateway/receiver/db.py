import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id INTEGER PRIMARY KEY,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    last_rssi REAL,
    x INTEGER, y INTEGER, battery INTEGER, last_kind INTEGER,
    msg_count INTEGER NOT NULL DEFAULT 0,
    hello_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    src INTEGER NOT NULL,
    counter INTEGER NOT NULL,
    received_at REAL NOT NULL,
    kind INTEGER NOT NULL,
    x INTEGER, y INTEGER, battery INTEGER, code INTEGER, text TEXT,
    rssi REAL
);
CREATE INDEX IF NOT EXISTS idx_messages_src ON messages(src);
CREATE TABLE IF NOT EXISTS alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    src INTEGER,
    kind TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS rx_stats (
    status TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    created_at REAL NOT NULL,
    sent_at REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
"""


class Database:
    def __init__(self, path=":memory:"):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            if path != ":memory:":
                self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _one(self, sql, args=()):
        with self.lock:
            r = self.conn.execute(sql, args).fetchone()
            return dict(r) if r else None

    # ---- düğümler ----
    def touch_node(self, node_id, now, rssi=None, hello=False, report=None):
        with self.lock:
            row = self.conn.execute("SELECT node_id FROM nodes WHERE node_id=?", (node_id,)).fetchone()
            if row is None:
                self.conn.execute("INSERT INTO nodes(node_id, first_seen, last_seen) VALUES (?,?,?)",
                                  (node_id, now, now))
            self.conn.execute("UPDATE nodes SET last_seen=?, last_rssi=COALESCE(?, last_rssi), "
                              "hello_count=hello_count+? WHERE node_id=?",
                              (now, rssi, 1 if hello else 0, node_id))
            if report:
                self.conn.execute("UPDATE nodes SET x=?, y=?, battery=?, last_kind=?, msg_count=msg_count+1 "
                                  "WHERE node_id=?",
                                  (report["x"], report["y"], report["battery"], report["kind"], node_id))
            self.conn.commit()

    def nodes(self):
        return self._all("SELECT * FROM nodes ORDER BY node_id")

    # ---- mesajlar ----
    def insert_message(self, uid, src, counter, now, report, rssi=None):
        # Aynı uid ikinci kez gelirse eklenmez (çift kayıt önleme). Dönüş: yeni satır id'si veya None
        with self.lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO messages(uid, src, counter, received_at, kind, x, y, battery, code, text, rssi) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (uid, src, counter, now, report["kind"], report["x"], report["y"], report["battery"],
                 report["code"], report["text"], rssi))
            self.conn.commit()
            return cur.lastrowid if cur.rowcount else None

    def messages(self, limit=50, after_id=0):
        return self._all("SELECT * FROM messages WHERE id>? ORDER BY id DESC LIMIT ?", (after_id, limit))

    def message_count(self):
        return self._one("SELECT COUNT(*) AS n FROM messages")["n"]

    # ---- alarmlar ve istatistik ----
    def add_alarm(self, ts, src, kind, detail=""):
        with self.lock:
            self.conn.execute("INSERT INTO alarms(ts, src, kind, detail) VALUES (?,?,?,?)", (ts, src, kind, detail))
            self.conn.commit()

    def alarms(self, limit=30, after_id=0):
        return self._all("SELECT * FROM alarms WHERE id>? ORDER BY id DESC LIMIT ?", (after_id, limit))

    def count_status(self, status):
        with self.lock:
            self.conn.execute("INSERT INTO rx_stats(status, count) VALUES (?,1) "
                              "ON CONFLICT(status) DO UPDATE SET count=count+1", (status,))
            self.conn.commit()

    def rx_stats(self):
        return {r["status"]: r["count"] for r in self._all("SELECT * FROM rx_stats")}

    # ---- giden kutusu (köprü kuyruğu) ----
    def enqueue(self, uid, body, now):
        with self.lock:
            cur = self.conn.execute("INSERT OR IGNORE INTO outbox(uid, body, created_at) VALUES (?,?,?)",
                                    (uid, json.dumps(body), now))
            self.conn.commit()
            return bool(cur.rowcount)

    def pending(self, limit=50):
        rows = self._all("SELECT * FROM outbox WHERE sent_at IS NULL ORDER BY id LIMIT ?", (limit,))
        for r in rows:
            r["body"] = json.loads(r["body"])
        return rows

    def pending_count(self):
        return self._one("SELECT COUNT(*) AS n FROM outbox WHERE sent_at IS NULL")["n"]

    def sent_count(self):
        return self._one("SELECT COUNT(*) AS n FROM outbox WHERE sent_at IS NOT NULL")["n"]

    def mark_sent(self, uids, now):
        with self.lock:
            self.conn.executemany("UPDATE outbox SET sent_at=?, attempts=attempts+1 WHERE uid=?",
                                  [(now, u) for u in uids])
            self.conn.commit()

    def mark_failed(self, uids, error):
        with self.lock:
            self.conn.executemany("UPDATE outbox SET attempts=attempts+1, last_error=? WHERE uid=?",
                                  [(error, u) for u in uids])
            self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()
