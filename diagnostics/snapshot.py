"""
Snapshot: liest in EINEM Augenblick alle relevanten Register.
Aufgabe: Vor dem Ausfuehren App oeffnen, Snapshot starten,
und SOFORT die App-Werte aufschreiben (Grid, Load, Battery, PV, SOC).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import WR_HOST as HOST, WR_SERIAL as SERIAL, WR_PORT as PORT, WR_SLAVE as SLAVE

from pysolarmanv5 import PySolarmanV5
import time


def as_signed(v):
    return v - 0x10000 if v & 0x8000 else v


# (reg, count, label, signed)
ITEMS = [
    (587, 1, "Bat V    *0.1 V", False),
    (588, 1, "SOC      %",       False),
    (590, 1, "Bat P    raw",     True),
    (591, 1, "Bat I    *0.01 A", True),
    (596, 1, "?596 (signed)",    True),

    # Grid CT-Verdaechtige
    (619, 1, "?619 grid L1?",    True),
    (620, 1, "?620 grid L2?",    True),
    (621, 1, "?621 grid L3?",    True),
    (622, 1, "?622",             True),
    (625, 1, "?625 grid total",  True),
    (647, 1, "?647",             True),
    (648, 1, "?648",             True),
    (649, 1, "?649",             True),

    # Phasen-Trios
    (633, 3, "Trio 633-635",     True),
    (640, 3, "Trio 640-642",     True),
    (650, 3, "Trio 650-652",     True),

    # Summen
    (636, 1, "636 inv tot",      True),
    (653, 1, "653 load tot",     True),

    # Breite Suche nach moeglichen Grid-Registern
    (167, 3, "167-169",          True),
    (169, 1, "169",              True),
    (170, 3, "170-172",          True),
    (175, 3, "175-177",          True),

    # PV (Tagesbetrieb)
    (672, 8, "672-679 PV",       False),
]


def main():
    m = PySolarmanV5(HOST, SERIAL, port=PORT, mb_slave_id=SLAVE,
                     socket_timeout=10, v5_error_correction=True)

    print(f"Snapshot @ {time.strftime('%H:%M:%S')}\n")
    for reg, cnt, label, signed in ITEMS:
        try:
            vals = m.read_holding_registers(register_addr=reg, quantity=cnt)
            if signed:
                vals = [as_signed(v) for v in vals]
            print(f"  reg {reg:>4} ({cnt}): {vals}   {label}")
        except Exception as e:
            print(f"  reg {reg:>4} ({cnt}): ERR {type(e).__name__}")
        time.sleep(0.1)


if __name__ == "__main__":
    main()
