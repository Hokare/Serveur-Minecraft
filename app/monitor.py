"""Collecte des performances : stats Docker, ping Minecraft, ressources de l'hôte."""
from __future__ import annotations

import json
import logging
import socket
import struct
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

log = logging.getLogger("mc-panel.monitor")

HISTORY_LEN = 360          # 30 min à 5 s
ROUTER_KEY = "__router__"


# --------------------------------------------------------------------------- ping
def _varint(n: int) -> bytes:
    out = b""
    while True:
        byte = n & 0x7F
        n >>= 7
        out += bytes([byte | (0x80 if n else 0)])
        if not n:
            return out


def _read_varint(sock: socket.socket) -> int:
    result = shift = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise EOFError("connexion fermée")
        v = b[0]
        result |= (v & 0x7F) << shift
        shift += 7
        if not v & 0x80:
            return result
        if shift > 35:
            raise ValueError("varint trop long")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("réponse tronquée")
        buf += chunk
    return buf


def ping(host: str, port: int = 25565, timeout: float = 2.0) -> dict:
    """Server List Ping (protocole Minecraft) : joueurs, version, latence."""
    start = time.monotonic()
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        hb = host.encode()
        payload = b"\x00" + _varint(765) + _varint(len(hb)) + hb + struct.pack(">H", port) + _varint(1)
        s.sendall(_varint(len(payload)) + payload)
        s.sendall(b"\x01\x00")
        _read_varint(s)                       # longueur du paquet
        if _read_varint(s) != 0:
            raise ValueError("paquet inattendu")
        length = _read_varint(s)
        if length > 1 << 20:
            raise ValueError("réponse trop grande")
        data = json.loads(_recv_exact(s, length))
    data["latency_ms"] = round((time.monotonic() - start) * 1000)
    return data


# --------------------------------------------------------------------------- stats
def compute_cpu(stats: dict) -> float:
    """% CPU d'un conteneur (100 % = un cœur), comme `docker stats`."""
    cpu = stats.get("cpu_stats", {})
    pre = stats.get("precpu_stats", {})
    cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get("total_usage", 0)
    sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    online = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or []) or 1
    if sys_delta > 0 and cpu_delta >= 0:
        return round(cpu_delta / sys_delta * online * 100, 1)
    return 0.0


def compute_mem(stats: dict) -> tuple[int, int]:
    mem = stats.get("memory_stats", {})
    detail = mem.get("stats", {})
    used = mem.get("usage", 0) - detail.get("inactive_file", detail.get("cache", 0))
    return max(used, 0), mem.get("limit", 0)


def compute_net(stats: dict) -> tuple[int, int]:
    nets = stats.get("networks") or {}
    return sum(n.get("rx_bytes", 0) for n in nets.values()), sum(n.get("tx_bytes", 0) for n in nets.values())


def host_stats() -> dict:
    if psutil is None:
        return {}
    vm = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage("/")
        disk_info = {"disk_used": disk.used, "disk_total": disk.total}
    except OSError:
        disk_info = {}
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "cores": psutil.cpu_count(),
        "mem_used": vm.total - vm.available,
        "mem_total": vm.total,
        **disk_info,
    }


class Monitor:
    def __init__(self, manager, interval: float = 5.0):
        self.manager = manager
        self.interval = interval
        self._history: dict[str, deque] = {}
        self._net: dict[str, tuple[float, int, int]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- cycle de vie
    def start(self) -> None:
        if psutil:
            psutil.cpu_percent(interval=None)   # amorce la mesure
        self._thread = threading.Thread(target=self._loop, name="monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # -- accès
    def latest(self, key: str) -> dict | None:
        with self._lock:
            hist = self._history.get(key)
            if hist and time.time() - hist[-1]["t"] < self.interval * 4:
                return hist[-1]
        return None

    def history(self, key: str) -> list[dict]:
        with self._lock:
            return list(self._history.get(key, ()))

    # -- collecte
    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.time()
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - la boucle ne doit jamais mourir
                log.exception("échec de la collecte")
            self._stop.wait(max(0.5, self.interval - (time.time() - started)))

    def _tick(self) -> None:
        if not self.manager.available():
            return
        containers = self.manager.running_managed()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self._sample, containers))
        alive = set()
        with self._lock:
            for key, point in results:
                if point is None:
                    continue
                alive.add(key)
                self._history.setdefault(key, deque(maxlen=HISTORY_LEN)).append(point)
            for key in list(self._history):
                if key not in {k for k, _ in results}:
                    self._net.pop(key, None)

    def _sample(self, container) -> tuple[str, dict | None]:
        key = self.manager.key_of(container)
        try:
            stats = container.stats(stream=False)
        except Exception:  # noqa: BLE001
            return key, None
        now = time.time()
        used, limit = compute_mem(stats)
        rx, tx = compute_net(stats)
        rx_rate = tx_rate = 0.0
        prev = self._net.get(key)
        if prev and now > prev[0] and rx >= prev[1] and tx >= prev[2]:
            rx_rate = (rx - prev[1]) / (now - prev[0])
            tx_rate = (tx - prev[2]) / (now - prev[0])
        self._net[key] = (now, rx, tx)
        point = {
            "t": now,
            "cpu": compute_cpu(stats),
            "mem": used,
            "mem_limit": limit,
            "rx_rate": round(rx_rate),
            "tx_rate": round(tx_rate),
            "players": None,
            "max_players": None,
            "latency_ms": None,
            "version": None,
        }
        if key != ROUTER_KEY:
            ip = self.manager.ip_of(container)
            if ip and self.manager.is_ready(container):
                try:
                    info = ping(ip, 25565)
                    players = info.get("players", {})
                    point.update(
                        players=players.get("online"),
                        max_players=players.get("max"),
                        latency_ms=info.get("latency_ms"),
                        version=info.get("version", {}).get("name"),
                    )
                except Exception:  # noqa: BLE001 - serveur en démarrage ou injoignable
                    pass
        return key, point
