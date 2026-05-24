"""
Breiter Scan-Modus: liest mehrere Bereiche und zeigt Roh + mögliche Interpretationen.
Damit findest du das richtige Register, indem du die App-Werte mit den Zahlen vergleichst.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import WR_HOST as HOST, WR_SERIAL as SERIAL, WR_PORT as PORT, WR_SLAVE as SLAVE

from pysolarmanv5 import PySolarmanV5
import time

# Interessante Bereiche bei Deye-Hybrid-Wechselrichtern (HP3 / LP3 / SG-Serien)
RANGES = [
    (500, 30),   # Status / Energie-Counter
    (586, 14),   # Batterie-Bereich
    (598, 16),   # Wechselrichter AC
    (616, 16),   # Netz-Phasen
    (633, 24),   # Lasten / Inverter
    (672, 20),   # PV-Strings
]


def as_signed(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def main():
    m = PySolarmanV5(HOST, SERIAL, port=PORT, mb_slave_id=SLAVE,
                     socket_timeout=10, v5_error_correction=True)

    print(f"{'Reg':>5}  {'raw':>6}  {'hex':>6}  {'signed':>8}  {'×0.1':>8}  {'×0.01':>8}")
    print("-" * 60)

    for start, count in RANGES:
        # In Häppchen lesen (max 20 je Read ist sicher)
        chunk_size = 10
        for off in range(0, count, chunk_size):
            qty = min(chunk_size, count - off)
            base = start + off
            try:
                vals = m.read_holding_registers(register_addr=base, quantity=qty)
            except Exception as e:
                print(f"{base:>5}  FEHLER {type(e).__name__}: {e}")
                time.sleep(0.5)
                continue
            for i, v in enumerate(vals):
                reg = base + i
                s = as_signed(v)
                print(f"{reg:>5}  {v:>6}  {v:>6x}  {s:>8}  {v*0.1:>8.1f}  {v*0.01:>8.2f}")
            print()
            time.sleep(0.2)


if __name__ == "__main__":
    main()
