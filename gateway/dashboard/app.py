import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from gateway.receiver.report import KIND_NAMES

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ALIVE_S = 60.0
STALE_S = 150.0


def node_status(age):
    if age <= ALIVE_S:
        return "canli"
    if age <= STALE_S:
        return "gecikmis"
    return "kayip"


def build_health(db, now):
    nodes = db.nodes()
    counts = {"canli": 0, "gecikmis": 0, "kayip": 0}
    for n in nodes:
        counts[node_status(now - n["last_seen"])] += 1
    recent = [m for m in db.messages(500) if now - m["received_at"] <= 60.0]
    last = db.messages(1)
    return {"now": now, "nodes_total": len(nodes), **counts,
            "messages_total": db.message_count(), "messages_last_min": len(recent),
            "last_message_age": (now - last[0]["received_at"]) if last else None,
            "rx_stats": db.rx_stats(), "outbox_pending": db.pending_count(), "outbox_sent": db.sent_count(),
            "alarms_last_10min": len([a for a in db.alarms(200) if now - a["ts"] <= 600.0])}


def events_since(db, last_msg, last_alarm):
    """Yeni mesaj ve alarmları (eskiden yeniye) döndürür: (olaylar, yeni_son_mesaj_id, yeni_son_alarm_id)"""
    events = []
    for m in reversed(db.messages(100, after_id=last_msg)):
        last_msg = max(last_msg, m["id"])
        events.append({"type": "message", "data": {**m, "kind_name": KIND_NAMES.get(m["kind"], "?")}})
    for a in reversed(db.alarms(100, after_id=last_alarm)):
        last_alarm = max(last_alarm, a["id"])
        events.append({"type": "alarm", "data": a})
    return events, last_msg, last_alarm


def create_app(db, clock=time.time, mock=None):
    app = FastAPI(title="Afet Mesh gateway paneli")

    @app.get("/api/nodes")
    def api_nodes():
        now = clock()
        out = []
        for n in db.nodes():
            age = now - n["last_seen"]
            out.append({**n, "age": age, "status": node_status(age), "kind_name": KIND_NAMES.get(n["last_kind"])})
        return out

    @app.get("/api/messages")
    def api_messages(limit: int = 50, after_id: int = 0):
        limit = max(1, min(limit, 500))
        return [{**m, "kind_name": KIND_NAMES.get(m["kind"], "?")} for m in db.messages(limit, after_id)]

    @app.get("/api/alarms")
    def api_alarms(limit: int = 30):
        return db.alarms(max(1, min(limit, 200)))

    @app.get("/api/health")
    def api_health():
        return build_health(db, clock())

    @app.get("/api/stream")
    def api_stream():
        def gen():
            last_msg = last_alarm = 0
            first = db.messages(1)
            if first:
                last_msg = first[0]["id"]
            a = db.alarms(1)
            if a:
                last_alarm = a[0]["id"]
            while True:
                events, last_msg, last_alarm = events_since(db, last_msg, last_alarm)
                for e in events:
                    yield f"event: {e['type']}\ndata: {json.dumps(e['data'])}\n\n"
                yield f"event: health\ndata: {json.dumps(build_health(db, clock()))}\n\n"
                time.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    if mock is not None:
        @app.post("/api/demo/kill/{node_id}")
        def demo_kill(node_id: int):
            if node_id < 2 or node_id > len(mock.mesh):
                raise HTTPException(404, "düğüm yok")
            mock.kill_node(node_id)
            return {"ok": True}

        @app.post("/api/demo/attack/{kind}")
        def demo_attack(kind: str):
            if kind == "replay":
                mock.inject_replay(3)
            elif kind == "forgery":
                mock.inject_forgery(4, 3)
            elif kind == "clone":
                mock.inject_clone(6, 4)
            else:
                raise HTTPException(404, "bilinmeyen saldırı")
            return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main():
    import argparse

    import uvicorn

    from gateway.mockradio import MockRadio
    from gateway.receiver.db import Database

    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="sahte radyo ile canlı demo")
    ap.add_argument("--db", default=":memory:")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--speed", type=float, default=5.0, help="demo: simülasyon hızı (gerçek zamanın kaç katı)")
    args = ap.parse_args()

    db = Database(args.db)
    mock = None
    clock = time.time
    if args.demo:
        mock = MockRadio(db, seed=3)
        clock = mock.clock
        threading.Thread(target=lambda: mock.run(10 ** 9, realtime=True, speed=args.speed), daemon=True).start()
    uvicorn.run(create_app(db, clock, mock), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
