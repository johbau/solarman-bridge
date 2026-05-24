"""
Sucht die PV-Register bei laufender PV-Produktion.

Vorgehen:
1. Solarman-App oeffnen, aktuellen PV-Wert merken (W oder kW)
2. Dieses Skript ausfuehren
3. Werte ausserhalb der bekannten (Grid/Bat/Load/Inv/SOC) ansehen
4. Zahlen finden, die zur App-Anzeige passen (x1, x10 oder x100)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import WR_HOST as HOST, WR_SERIAL as SERIAL, WR_PORT as PORT, WR_SLAVE as SLAVE

from pysolarmanv5 import PySolarmanV5
import time


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


# Bereiche, in denen Deye PV typischerweise ablegt
RANGES = [
    (167, 20),    # 167-186  alte Deye-Strings
    (520, 20),    # 520-539  Energie/Tagesproduktion
    (596,  4),    # 596-599  Sonderwerte
    (672, 24),    # 672-695  PV-Strings (HP3 + neuere)
    (700, 20),    # 700-719  alternative PV-Stellen
]

# Bekannte Register (die ignorieren wir bei der Suche)
KNOWN = {587, 588, 590, 591, 625, 633, 634, 635, 636,
         640, 641, 642, 650, 651, 652, 653,
         627, 628, 629, 638}


def main():
    m = PySolarmanV5(HOST, SERIAL, port=PORT, mb_slave_id=SLAVE,
                     socket_timeout=10, v5_error_correction=True)

    print(f"Snapshot @ {time.strftime('%H:%M:%S')}")
    print("Vergleiche die Werte mit dem aktuellen PV-Wert in der App.\n")

    print(f"{'reg':>5}  {'raw':>6}  {'signed':>8}  {'x1':>10}  {'x10':>10}  {'x100':>10}  bekannt?")
    print("-" * 75)

    for start, count in RANGES:
        chunk = 10
        for off in range(0, count, chunk):
            qty = min(chunk, count - off)
            base = start + off
            try:
                vals = m.read_holding_registers(register_addr=base, quantity=qty)
            except Exception as e:
                print(f"{base:>5}  ERR {type(e).__name__}")
                time.sleep(0.5)
                continue
            for i, v in enumerate(vals):
                reg = base + i
                if v == 0:
                    continue   # Nullen rauslassen, schafft Uebersicht
                sgn = s16(v)
                mark = "(KNOWN)" if reg in KNOWN else ""
                print(f"{reg:>5}  {v:>6}  {sgn:>8}  {v:>10}  {v*10:>10}  {v*100:>10}  {mark}")
            print()
            time.sleep(0.2)


if __name__ == "__main__":
    main()
