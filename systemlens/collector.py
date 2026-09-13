"""One sampler for every client; monotonic deltas, bounded in-memory history."""

from collections import deque
from datetime import datetime, timezone
import logging
import os
import platform
import threading
import time

import psutil

from .hardware import discover

LOG = logging.getLogger(__name__)


def rate(current, previous, elapsed):
    """Ignore counter resets and invalid intervals instead of showing spikes."""
    if previous is None or elapsed <= 0 or current < previous:
        return 0.0
    return (current - previous) / elapsed


def optional(call, default=None):
    try:
        return call()
    except (OSError, psutil.Error, RuntimeError, NotImplementedError, AttributeError):
        return default


class Collector:
    def __init__(self, interval=1.0, capacity=900):
        self.interval = interval
        self.history = deque(maxlen=capacity)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.hardware_thread = None
        self.hardware = {"status": "loading", "cpu": [], "memory": [], "disks": [], "graphics": []}
        self.error = None
        self.latest = None
        self.previous = None
        self.process_previous = {}
        self.sequence = 0
        self.system = {
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "processor": platform.processor() or platform.machine(),
            "logical_cores": psutil.cpu_count() or 1,
            "physical_cores": psutil.cpu_count(logical=False),
        }

    def start(self):
        self.hardware_thread = threading.Thread(target=self._hardware, name="systemlens-hardware", daemon=True)
        self.hardware_thread.start()
        self.thread = threading.Thread(target=self._run, name="systemlens-sampler", daemon=True)
        self.thread.start()

    def _hardware(self):
        hardware = discover()
        with self.lock:
            self.hardware = hardware

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _run(self):
        # psutil's first CPU reading is meaningless; prime it in this same thread.
        psutil.cpu_percent(percpu=True)
        deadline = time.monotonic() + self.interval
        while not self.stop_event.wait(max(0.05, deadline - time.monotonic())):
            try:
                sample = self.sample()
                with self.lock:
                    self.latest = sample
                    self.history.append({key: value for key, value in sample.items()
                                         if key not in ("processes", "cores", "partitions")})
                    self.error = None
            except Exception:
                LOG.exception("Could not collect system metrics")
                with self.lock:
                    self.error = "Não foi possível atualizar as métricas. Tentando novamente."
            deadline = max(deadline + self.interval, time.monotonic())

    def snapshot(self):
        with self.lock:
            return {"system": self.system, "hardware": self.hardware, "samples": list(self.history), "latest": self.latest, "error": self.error,
                    "interval": self.interval, "capacity": self.history.maxlen}

    def sample(self):
        now = time.monotonic()
        net = optional(psutil.net_io_counters)
        disk_io = optional(psutil.disk_io_counters)
        elapsed = now - self.previous[0] if self.previous else 0
        previous_net = self.previous[1] if self.previous else None
        previous_disk = self.previous[2] if self.previous else None

        def delta(obj, old, field):
            if obj is None:
                return None
            return rate(getattr(obj, field), getattr(old, field) if old else None, elapsed)

        memory = psutil.virtual_memory()
        cores = psutil.cpu_percent(percpu=True)
        partitions = []
        seen = set()
        for part in optional(psutil.disk_partitions, []):
            if part.mountpoint in seen or "cdrom" in part.opts:
                continue
            usage = optional(lambda: psutil.disk_usage(part.mountpoint))
            if usage:
                seen.add(part.mountpoint)
                partitions.append({"mount": part.mountpoint, "filesystem": part.fstype,
                                   "total": usage.total, "used": usage.used, "percent": usage.percent})
        if not partitions:
            root = os.path.abspath(os.sep)
            usage = optional(lambda: psutil.disk_usage(root))
            if usage:
                partitions.append({"mount": root, "filesystem": "", "total": usage.total,
                                   "used": usage.used, "percent": usage.percent})
        processes = []
        next_processes = {}
        for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_times", "create_time"], ad_value=None):
            try:
                info = proc.info
                # PID 0 is an idle/kernel placeholder, not a consuming application.
                if info["pid"] == 0:
                    continue
                if not info["cpu_times"] or not info["memory_info"]:
                    continue
                key = (info["pid"], info["create_time"])
                cpu_time = info["cpu_times"].user + info["cpu_times"].system
                old = self.process_previous.get(key)
                cpu = rate(cpu_time, old[0] if old else None, now - old[1] if old else 0)
                next_processes[key] = (cpu_time, now)
                processes.append({"pid": info["pid"], "name": info["name"] or "Processo",
                                  "cpu": min(100.0, cpu * 100 / self.system["logical_cores"]),
                                  "memory": info["memory_info"].rss})
            except (psutil.Error, OSError):
                continue
        self.process_previous = next_processes
        temperatures = optional(lambda: psutil.sensors_temperatures(), {})
        values = [entry.current for group in temperatures.values() for entry in group
                  if entry.current is not None and -20 <= entry.current <= 150]
        battery = optional(psutil.sensors_battery)
        frequency = optional(psutil.cpu_freq)
        self.sequence += 1
        sample = {
            "id": self.sequence, "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu": sum(cores) / len(cores) if cores else 0, "cores": cores,
            "frequency_mhz": frequency.current if frequency else None,
            "memory_percent": memory.percent, "memory_used": memory.total - memory.available,
            "memory_total": memory.total, "memory_available": memory.available,
            "download": delta(net, previous_net, "bytes_recv"),
            "upload": delta(net, previous_net, "bytes_sent"),
            "disk_read": delta(disk_io, previous_disk, "read_bytes"),
            "disk_write": delta(disk_io, previous_disk, "write_bytes"),
            "partitions": partitions, "process_count": len(processes),
            "temperature": max(values) if values else None,
            "battery": {"percent": battery.percent, "plugged": battery.power_plugged} if battery else None,
            "uptime": max(0, time.time() - psutil.boot_time()),
            "processes": sorted(processes, key=lambda p: (p["cpu"], p["memory"]), reverse=True),
        }
        self.previous = (now, net, disk_io)
        return sample
