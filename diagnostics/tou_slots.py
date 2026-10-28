"""Print the inverter's six TOU slots (read-only).  Live view:
    watch -n 10 .venv/bin/python diagnostics/tou_slots.py
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import WR_HOST, WR_SERIAL, WR_PORT, WR_SLAVE
from pysolarmanv5 import PySolarmanV5

m = PySolarmanV5(WR_HOST, WR_SERIAL, port=WR_PORT, mb_slave_id=WR_SLAVE,
                 socket_timeout=10, v5_error_correction=True)


def rd(addr, n):
    for _ in range(4):
        try:
            return m.read_holding_registers(register_addr=addr, quantity=n)
        except Exception as e:  # noqa: BLE001 - dongle hiccups, retry
            err = e
            time.sleep(0.5)
    raise err


en = rd(146, 1)[0]
t, p, s, g = rd(148, 6), rd(154, 6), rd(166, 6), rd(172, 6)
b = rd(587, 5)
bp = b[3] - 65536 if b[3] > 32767 else b[3]
print(f"{time.strftime('%T')}  TOU {'on' if en & 1 else 'OFF'}  "
      f"days {''.join(d if en >> (i + 1) & 1 else '-' for i, d in enumerate('MTWTFSS'))}  "
      f"| battery SOC {b[1]}%  {bp * 10:+d} W (+ = discharging)")
print(f"{'slot':<5}{'start':<7}{'end':<7}{'power W':<9}{'target SOC':<12}grid charge")
for i in range(6):
    end = t[(i + 1) % 6]
    print(f"{i + 1:<5}{t[i] // 100:02d}:{t[i] % 100:02d}  {end // 100:02d}:{end % 100:02d}  "
          f"{p[i] * 10:<9}{s[i]:<12}{'on' if g[i] & 1 else 'off'}")
