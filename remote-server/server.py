import hmac
import json
import os
import sqlite3
import threading
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class Message(BaseModel):
    uid: str
    src: int
    counter: int
    kind: str
    x: int
    y: int
    battery: int
    code: int
    text: str
    received_at: float


class Batch(BaseModel):
    gateway: str
    messages: list[Message]


def create_app(db_path=":memory:", api_key=None):
    """Uzak sunucu demosu: gateway'lerden toplu mesaj alır, (gateway, uid) çiftiyle çift kaydı önler."""
    api_key = api_key or os.environ.get("REMOTE_API_KEY")
    if not api_key:
        raise RuntimeError("API anahtarı gerekli: REMOTE_API_KEY ortam değişkeni veya api_key parametresi")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    lock = threading.Lock()
    with lock:
        conn.execute("CREATE TABLE IF NOT EXISTS messages (gateway TEXT NOT NULL, uid TEXT NOT NULL, body TEXT NOT NULL, "
                     "stored_at REAL NOT NULL, PRIMARY KEY (gateway, uid))")
        conn.commit()
    app = FastAPI(title="Afet Mesh uzak sunucu")

    def check(key):
        if not key or not hmac.compare_digest(key, api_key):
            raise HTTPException(401, "geçersiz API anahtarı")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/ingest")
    def ingest(batch: Batch, x_api_key: str = Header(default="")):
        check(x_api_key)
        new = dup = 0
        with lock:
            for m in batch.messages:
                cur = conn.execute("INSERT OR IGNORE INTO messages(gateway, uid, body, stored_at) VALUES (?,?,?,?)",
                                   (batch.gateway, m.uid, json.dumps(m.model_dump()), time.time()))
                if cur.rowcount:
                    new += 1
                else:
                    dup += 1
            conn.commit()
        return {"accepted": new, "duplicates": dup}

    @app.get("/api/stats")
    def stats(x_api_key: str = Header(default="")):
        check(x_api_key)
        with lock:
            n = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
            per = conn.execute("SELECT gateway, COUNT(*) AS n FROM messages GROUP BY gateway").fetchall()
        return {"total": n, "per_gateway": {r["gateway"]: r["n"] for r in per}}

    @app.get("/api/messages")
    def messages(limit: int = 50, x_api_key: str = Header(default="")):
        check(x_api_key)
        with lock:
            rows = conn.execute("SELECT gateway, body FROM messages ORDER BY stored_at DESC LIMIT ?",
                                (max(1, min(limit, 500)),)).fetchall()
        return [{"gateway": r["gateway"], **json.loads(r["body"])} for r in rows]

    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="remote.db")
    ap.add_argument("--port", type=int, default=9000)
    args = ap.parse_args()
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port, log_level="warning")
