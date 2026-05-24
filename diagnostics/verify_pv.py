"""
Live-Verifikation der PV-Berechnung gegen die Solarman-App.
Liest V/I beider Strings, rechnet Leistung, vergleicht mit Energie-Zaehlern.
"""
from pysolarmanv5 import PySolarmanV5
import time

m = PySolarmanV5("192.168.1.100", 1234567890, port=8899, mb_slave_id=1,
                 socket_timeout=10, v5_error_correction=True)

print(f"{'time':>8}  {'PV1(W)':>7}  {'PV2(W)':>7}  {'Total(W)':>8}  "
      f"{'PV1 V/I':>11}  {'PV2 V/I':>11}  {'today(kWh)':>10}  {'total(MWh)':>10}")
print("-" * 90)

while True:
    try:
        pv = m.read_holding_registers(register_addr=672, quantity=8)
        en = m.read_holding_registers(register_addr=529, quantity=6)

        v1, i1 = pv[676-672]/10, pv[677-672]/10
        v2, i2 = pv[678-672]/10, pv[679-672]/10
        p1 = round(v1 * i1)
        p2 = round(v2 * i2)

        today = en[529-529] / 10
        total = en[534-529] / 1000   # in MWh

        print(f"{time.strftime('%H:%M:%S'):>8}  "
              f"{p1:>7}  {p2:>7}  {p1+p2:>8}  "
              f"{v1:>5.1f}V {i1:>4.2f}A  {v2:>5.1f}V {i2:>4.2f}A  "
              f"{today:>10.1f}  {total:>10.3f}")
    except Exception as e:
        print(f"{time.strftime('%H:%M:%S')}  ERR {type(e).__name__}: {e}")
    time.sleep(3)
