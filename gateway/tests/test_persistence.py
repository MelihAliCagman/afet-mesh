from gateway.receiver.db import Database
from gateway.receiver.report import KIND_STATUS, encode_report
from gateway.receiver.service import Gateway
from sim.packet import PacketType
from sim.security import PersistentCounter, Sender
from sim.wire import decode, encode

KEY = bytes(range(16))  # yalnızca test anahtarı


def frame(node, text="x"):
    return encode(node.seal(1, 1, PacketType.DATA, encode_report(KIND_STATUS, 1, 2, 80, 0, text)))


def setup(tmp_path, t):
    path = str(tmp_path / "gw.db")
    node = Sender(5, KEY, PersistentCounter({}, block=64))
    return path, node


def test_replay_after_restart_is_rejected_with_persistence(tmp_path):
    t = [1000.0]
    path, node = setup(tmp_path, t)
    gw = Gateway(Database(path), KEY, clock=lambda: t[0])
    frames = [frame(node) for _ in range(5)]
    for f in frames:
        gw.on_frame(f)
        t[0] += 1
    gw.close()

    t[0] += 3600  # yeniden başlatma, aradan uzun süre geçti
    gw2 = Gateway(Database(path), KEY, clock=lambda: t[0])
    db2 = gw2.db
    before = db2.message_count()
    gw2.on_frame(frames[2])     # eski kare yeniden oynatılıyor
    gw2.on_frame(frames[-1])    # son kare tekrar
    assert db2.message_count() == before
    assert db2.rx_stats().get("replay") == 1 and db2.rx_stats().get("dup") == 1
    # yeni kare normal şekilde kabul edilir
    gw2.on_frame(frame(node, "yeni"))
    assert db2.message_count() == before + 1


def test_without_persistence_replay_window_opens_after_restart(tmp_path):
    t = [1000.0]
    path, node = setup(tmp_path, t)
    gw = Gateway(Database(path), KEY, clock=lambda: t[0], persist=False)
    frames = [frame(node) for _ in range(5)]
    for f in frames:
        gw.on_frame(f)
    t[0] += 3600
    gw2 = Gateway(Database(path), KEY, clock=lambda: t[0], persist=False)
    gw2.on_frame(frames[2])   # durum unutulduğu için güvenlik katmanı kareyi yeni sayıp kabul eder (tekrar oynatma geçti)
    assert gw2.db.rx_stats()["ok"] == 6  # ilk 5 + tekrar oynatılan
    assert gw2.db.rx_stats().get("replay") is None


def test_clone_with_low_counter_still_detected_after_restart(tmp_path):
    t = [1000.0]
    path, node = setup(tmp_path, t)
    gw = Gateway(Database(path), KEY, clock=lambda: t[0])
    for _ in range(200):
        gw.on_frame(frame(node))
    gw.close()
    gw2 = Gateway(Database(path), KEY, clock=lambda: t[0])
    clone = Sender(5, KEY, PersistentCounter({}, block=64))
    for _ in range(4):
        t[0] += 1
        gw2.on_frame(frame(clone, "klon"))
    assert any(a["kind"] == "klon_alarmi" for a in gw2.db.alarms())


def test_gateway_ack_counter_never_goes_back(tmp_path):
    t = [1000.0]
    path, node = setup(tmp_path, t)
    gw = Gateway(Database(path), KEY, clock=lambda: t[0])
    acks = []
    for _ in range(80):
        acks += gw.on_frame(frame(node))
    first_counters = [decode(a).seq for a in acks]
    gw.close()
    gw2 = Gateway(Database(path), KEY, clock=lambda: t[0])
    new_ack = gw2.on_frame(frame(node))
    assert decode(new_ack[0]).seq > max(first_counters)  # yeniden başlayan gateway'in ACK sayacı geride kalmadı


def test_writes_are_batched_not_per_frame(tmp_path):
    t = [1000.0]
    path, node = setup(tmp_path, t)
    db = Database(path)
    saves = []
    orig = db.save_peer_states
    db.save_peer_states = lambda rows, now: (saves.append(len(rows)), orig(rows, now))
    gw = Gateway(db, KEY, clock=lambda: t[0], flush_s=5.0)
    other = Sender(6, KEY, PersistentCounter({}, block=64))
    for _ in range(100):
        gw.on_frame(frame(node))
        gw.on_frame(frame(other))
        t[0] += 0.02          # toplam 2 sn: bir tur flush bile gerekmez
    assert saves == []
    t[0] += 10
    gw.on_frame(frame(node))
    assert len(saves) == 1 and saves[0] == 2   # iki kaynak, tek işlem
    gw.close()
    assert len(saves) == 2


def test_state_survives_multiple_restarts(tmp_path):
    t = [1000.0]
    path, node = setup(tmp_path, t)
    seen = []
    for round_ in range(3):
        gw = Gateway(Database(path), KEY, clock=lambda: t[0])
        for _ in range(10):
            f = frame(node)
            seen.append(f)
            gw.on_frame(f)
            t[0] += 1
        gw.close()
        t[0] += 120
    gw = Gateway(Database(path), KEY, clock=lambda: t[0])
    n = gw.db.message_count()
    assert n == 30
    for f in seen[::3]:
        gw.on_frame(f)
    assert gw.db.message_count() == n
