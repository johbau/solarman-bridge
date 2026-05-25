"""
Solarman-zu-HTTP-Bruecke fuer Deye SUN-25K-SG01HP3-EU-AM2

Liest Werte vom Wechselrichter (Read-Endpunkte) und steuert die Batterie
ueber die TOU-Slots (Write-Endpunkt fuer evcc-Battery-Mode).

READ-Endpunkte (GET):
  /grid /bat_power /bat_soc /load /inv /bat_v /bat_i
  /pv /pv1 /pv2 /pv1_v /pv1_i /pv2_v /pv2_i /pv_today /pv_total
  /all       -> alle Werte als JSON
  /health    -> Status (200 ok / 503 stale)
  /battery_mode -> aktueller Mode als JSON

WRITE-Endpunkt (POST):
  /battery_mode  Body: "normal" | "hold" | "charge"  oder "1" | "2" | "3"
                 (evcc-Mapping: 1=normal, 2=hold, 3=charge)

Steuerstrategie: Manipuliert den aktuell aktiven TOU-Slot des Deye-WR.
  CHARGE -> Slot SOC=100, Power=25000W, Grid-Charge=on  (zwingt Netz-Laden)
  HOLD   -> Slot Power=0                                (keine Be-/Entladung)
  NORMAL -> Original-Slot-Werte wiederherstellen

Original-Werte werden beim Start des Bridges einmal gelesen und im Speicher
gehalten. WARNUNG: Wenn du TOU-Slots in der App aenderst waehrend der Bridge
laeuft, gehen diese Aenderungen beim Wechsel zurueck zu NORMAL verloren.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pysolarmanv5 import PySolarmanV5

# ---------- Konfiguration ----------
# Lade WR_HOST / WR_SERIAL / WR_PORT / WR_SLAVE aus .env im selben Verzeichnis.
# Falls keine .env existiert, nutze Prozess-Environment, dann Defaults.
_cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_cfg_file):
    with open(_cfg_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))

WR_HOST    = os.environ.get("WR_HOST",   "192.168.1.100")
WR_SERIAL  = int(os.environ.get("WR_SERIAL", "1234567890"))
WR_PORT    = int(os.environ.get("WR_PORT",   "8899"))
WR_SLAVE   = int(os.environ.get("WR_SLAVE",  "1"))

HTTP_PORT     = 7071
POLL_INTERVAL = 5.0
STALE_AFTER   = 30.0

# ---------- Read-Register ----------
REG_BASE = 586
REG_QTY  = 68    # 586..653
PV_BASE  = 672
PV_QTY   = 8    # 672..679
EN_BASE  = 529
EN_QTY   = 6    # 529..534

# ---------- Control-Register (TOU) ----------
TOU_TIME_BASE = 148   # 148..153, HHMM
TOU_POWER_BASE = 154  # 154..159, x10 W
TOU_SOC_BASE = 166    # 166..171, %
TOU_GC_BASE = 172     # 172..177, 0/1
TOU_SLOTS = 6

# Werte fuer den manipulierten Slot
CHARGE_SOC   = 100
CHARGE_POWER = 2500    # raw value -> x10 = 25000 W
CHARGE_GC    = 1
HOLD_POWER   = 0

# Validierungs-Grenzen (Schutz vor unsinnigen Writes)
MAX_SOC      = 100
MAX_POWER_RAW = 2600   # 26 kW

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("solarman-bridge")


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


# ============================================================
# Modbus-Client mit Lock (poller + writes nutzen denselben)
# ============================================================
class Modbus:
    def __init__(self):
        self.lock = threading.Lock()
        self.client = None

    def _connect(self):
        log.info("connecting to %s:%d serial=%d",
                 WR_HOST, WR_PORT, WR_SERIAL)
        self.client = PySolarmanV5(
            WR_HOST, WR_SERIAL,
            port=WR_PORT, mb_slave_id=WR_SLAVE,
            socket_timeout=10, v5_error_correction=True)

    def _drop(self):
        try:
            if self.client is not None:
                self.client.disconnect()
        except Exception:
            pass
        self.client = None

    def read(self, addr, qty):
        with self.lock:
            if self.client is None:
                self._connect()
            try:
                return self.client.read_holding_registers(
                    register_addr=addr, quantity=qty)
            except Exception:
                self._drop()
                raise

    def write_one(self, addr, value):
        """Schreibt EIN Register, nutzt aber FC16 (write_multiple) weil Deye
        FC06 (write_single) mit AcknowledgeError ablehnt."""
        with self.lock:
            if self.client is None:
                self._connect()
            try:
                self.client.write_multiple_holding_registers(
                    register_addr=addr, values=[value])
                # Read-back verify
                got = self.client.read_holding_registers(
                    register_addr=addr, quantity=1)[0]
                if got != value:
                    raise RuntimeError(
                        f"verify failed reg {addr}: wrote {value} read {got}")
                log.info("write reg %d = %d (verified)", addr, value)
            except Exception:
                self._drop()
                raise


mb = Modbus()


# ============================================================
# State (gepollte Werte fuer GET-Endpunkte)
# ============================================================
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_update = 0.0
        self.values = {}

    def update(self, regs, pv_regs, en_regs):
        with self.lock:
            pv1_v = pv_regs[676 - PV_BASE] / 10.0
            pv1_i = pv_regs[677 - PV_BASE] / 10.0
            pv2_v = pv_regs[678 - PV_BASE] / 10.0
            pv2_i = pv_regs[679 - PV_BASE] / 10.0
            pv1 = round(pv1_v * pv1_i)
            pv2 = round(pv2_v * pv2_i)

            pv_today = round(en_regs[529 - EN_BASE] / 10.0, 1)
            pv_total = round(en_regs[534 - EN_BASE] / 10.0, 1)

            self.values = {
                "grid":      s16(regs[625 - REG_BASE]),
                "bat_power": s16(regs[590 - REG_BASE]) * 10,
                "bat_soc":   regs[588 - REG_BASE],
                "load":      regs[653 - REG_BASE],
                "inv":       s16(regs[636 - REG_BASE]),
                "bat_v":     round(regs[587 - REG_BASE] / 10.0, 2),
                "bat_i":     round(s16(regs[591 - REG_BASE]) / 100.0, 2),
                "pv":        pv1 + pv2,
                "pv1":       pv1,
                "pv2":       pv2,
                "pv1_v":     round(pv1_v, 1),
                "pv1_i":     round(pv1_i, 2),
                "pv2_v":     round(pv2_v, 1),
                "pv2_i":     round(pv2_i, 2),
                "pv_today":  pv_today,
                "pv_total":  pv_total,
            }
            self.last_update = time.time()

    def snapshot(self):
        with self.lock:
            return dict(self.values), self.last_update


state = State()


# ============================================================
# Battery-Mode-Controller (TOU-Slot Manipulation)
# ============================================================
class Controller:
    """Verwaltet den aktiven Battery-Mode durch TOU-Slot-Manipulation."""

    def __init__(self):
        self.lock = threading.Lock()
        self.mode = "normal"
        # Baseline: 6 Slots x (time, power, soc, grid_charge)
        self.baseline = None
        self.modified_slot = None

    # ---- Baseline einlesen mit Retries ----
    def load_baseline(self):
        times, powers, socs, gcs = [], [], [], []

        def read_with_retry(addr):
            for attempt in range(5):
                try:
                    return mb.read(addr, 1)[0]
                except Exception as e:
                    log.warning("baseline read reg %d attempt %d: %s",
                                addr, attempt + 1, e)
                    time.sleep(1)
            raise RuntimeError(f"baseline read failed for reg {addr}")

        for i in range(TOU_SLOTS):
            times.append(read_with_retry(TOU_TIME_BASE + i))
            powers.append(read_with_retry(TOU_POWER_BASE + i))
            socs.append(read_with_retry(TOU_SOC_BASE + i))
            gcs.append(read_with_retry(TOU_GC_BASE + i))

        with self.lock:
            self.baseline = {
                "times": times, "powers": powers,
                "socs": socs, "gcs": gcs,
            }
        log.info("TOU baseline loaded: times=%s socs=%s powers=%s gcs=%s",
                 times, socs, powers, gcs)

    # ---- Aktuellen Slot bestimmen ----
    def current_slot(self):
        if self.baseline is None:
            raise RuntimeError("baseline not loaded")
        now = datetime.now()
        now_hhmm = now.hour * 100 + now.minute
        times = self.baseline["times"]
        # Slot, dessen Startzeit am groessten und <= now ist (mit Wrap)
        sorted_idx = sorted(range(TOU_SLOTS), key=lambda i: times[i])
        current = sorted_idx[-1]  # Fallback: spaetester Slot (wrap)
        for i in sorted_idx:
            if times[i] <= now_hhmm:
                current = i
        return current

    # ---- Mode setzen ----
    def set_mode(self, new_mode):
        new_mode = self._normalize(new_mode)
        with self.lock:
            if new_mode == self.mode:
                log.info("mode unchanged: %s", new_mode)
                return self.mode
            log.info("mode change %s -> %s", self.mode, new_mode)

            # 1. Erst alles auf Baseline zuruecksetzen
            if self.modified_slot is not None:
                self._restore_slot(self.modified_slot)
                self.modified_slot = None

            # 2. Neue Mode anwenden
            if new_mode == "normal":
                pass
            elif new_mode == "hold":
                slot = self.current_slot()
                self._apply_hold(slot)
                self.modified_slot = slot
            elif new_mode == "charge":
                slot = self.current_slot()
                self._apply_charge(slot)
                self.modified_slot = slot

            self.mode = new_mode
            return self.mode

    def _restore_slot(self, slot):
        b = self.baseline
        mb.write_one(TOU_POWER_BASE + slot, b["powers"][slot])
        mb.write_one(TOU_SOC_BASE + slot,   b["socs"][slot])
        mb.write_one(TOU_GC_BASE + slot,    b["gcs"][slot])
        log.info("restored slot %d to baseline", slot + 1)

    def _apply_hold(self, slot):
        if HOLD_POWER > MAX_POWER_RAW:
            raise ValueError("HOLD_POWER too large")
        mb.write_one(TOU_POWER_BASE + slot, HOLD_POWER)
        log.info("HOLD applied on slot %d: power=0", slot + 1)

    def _apply_charge(self, slot):
        if CHARGE_SOC > MAX_SOC or CHARGE_POWER > MAX_POWER_RAW:
            raise ValueError("CHARGE values out of range")
        mb.write_one(TOU_SOC_BASE + slot, CHARGE_SOC)
        mb.write_one(TOU_POWER_BASE + slot, CHARGE_POWER)
        mb.write_one(TOU_GC_BASE + slot, CHARGE_GC)
        log.info("CHARGE applied on slot %d: soc=%d power=%d gc=%d",
                 slot + 1, CHARGE_SOC, CHARGE_POWER, CHARGE_GC)

    @staticmethod
    def _normalize(mode):
        if isinstance(mode, int):
            return {1: "normal", 2: "hold", 3: "charge"}.get(mode) or mode
        m = str(mode).strip().lower()
        if m in ("1", "normal"):
            return "normal"
        if m in ("2", "hold"):
            return "hold"
        if m in ("3", "charge"):
            return "charge"
        raise ValueError(f"unknown mode: {mode!r}")

    def info(self):
        with self.lock:
            return {
                "mode": self.mode,
                "modified_slot": (None if self.modified_slot is None
                                  else self.modified_slot + 1),
                "baseline_loaded": self.baseline is not None,
                "current_slot": (self.current_slot() + 1
                                 if self.baseline else None),
            }


controller = Controller()


# ============================================================
# Polling-Thread
# ============================================================
def poller():
    backoff = 2
    while True:
        try:
            regs = mb.read(REG_BASE, REG_QTY)
            pv_regs = mb.read(PV_BASE, PV_QTY)
            en_regs = mb.read(EN_BASE, EN_QTY)
            state.update(regs, pv_regs, en_regs)
            log.debug("update ok grid=%d bat=%d soc=%d load=%d pv=%d",
                      state.values["grid"], state.values["bat_power"],
                      state.values["bat_soc"], state.values["load"],
                      state.values["pv"])
            backoff = 2
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            log.warning("poll error: %s: %s", type(e).__name__, e)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


# ============================================================
# HTTP-Handler
# ============================================================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="text/plain; charset=utf-8"):
        body_b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body_b)

    def do_GET(self):
        path = self.path.rstrip("/")

        # ---- Control-Endpunkte ----
        if path == "/battery_mode":
            self._send(200, json.dumps(controller.info()),
                       "application/json")
            return

        # ---- Read-Endpunkte ----
        values, ts = state.snapshot()
        age = time.time() - ts

        if path == "/health":
            ok = bool(values) and age < STALE_AFTER
            payload = json.dumps({
                "ok": ok, "age_s": round(age, 1),
                "stale_after_s": STALE_AFTER,
                "controller": controller.info(),
            })
            self._send(200 if ok else 503, payload, "application/json")
            return

        if not values:
            self._send(503, "no data yet")
            return
        if age > STALE_AFTER:
            self._send(503, f"stale data, age={age:.1f}s")
            return

        if path == "/all":
            payload = json.dumps({**values, "age_s": round(age, 1)})
            self._send(200, payload, "application/json")
            return

        key = path.lstrip("/")
        if key in values:
            self._send(200, str(values[key]))
            return

        self._send(404, f"unknown endpoint: {path}\n"
                        f"available: {sorted(values.keys())}, "
                        f"/all, /health, /battery_mode")

    def do_POST(self):
        path = self.path.rstrip("/")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", "replace").strip()

        if path != "/battery_mode":
            self._send(404, f"unknown POST endpoint: {path}")
            return

        if not controller.baseline:
            self._send(503, "baseline not loaded yet, retry later")
            return

        try:
            new_mode = controller.set_mode(body)
            self._send(200, json.dumps({"mode": new_mode}),
                       "application/json")
        except ValueError as e:
            self._send(400, f"bad mode: {e}")
        except Exception as e:
            log.exception("set_mode failed")
            self._send(500, f"{type(e).__name__}: {e}")

    # evcc nutzt teils PUT statt POST
    do_PUT = do_POST


# ============================================================
# Main
# ============================================================
def main():
    t = threading.Thread(target=poller, daemon=True)
    t.start()

    # Baseline asynchron laden (blockiert nicht den HTTP-Server)
    def init_controller():
        for attempt in range(10):
            try:
                controller.load_baseline()
                return
            except Exception as e:
                log.warning("baseline load attempt %d failed: %s",
                            attempt + 1, e)
                time.sleep(5)
        log.error("could not load TOU baseline - write endpoints disabled")

    threading.Thread(target=init_controller, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    log.info("HTTP server listening on :%d", HTTP_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
        # Sicherheits-Restore: falls Mode != normal, zurueck auf Baseline
        try:
            if controller.mode != "normal":
                log.info("restoring TOU baseline on shutdown")
                controller.set_mode("normal")
        except Exception as e:
            log.warning("shutdown restore failed: %s", e)


if __name__ == "__main__":
    main()
