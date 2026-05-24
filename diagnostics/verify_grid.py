"""
Pollt die fuer evcc relevanten Register jede 2 Sekunden und zeigt sie live.
Damit kannst du die Werte mit der Solarman-App vergleichen und Vorzeichen
sowie Skalierung verifizieren bevor die evcc-Konfig live geht.

Konvention nach unserer Analyse:
  Grid (625):  + = Bezug, - = Einspeisung   (W, x1)
  Bat  (590):  + = Entladen, - = Laden      (W, x10 -> Wert mal 10)
  Load (653):  immer positiv                (W, x1)
  Inv  (636):  signed                        (W, x1)
  SOC  (588):  0..100                        (%)
"""

from pysolarmanv5 import PySolarmanV5
import time

HOST   = "192.168.1.100"
SERIAL = 1234567890
PORT   = 8899
SLAVE  = 1


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def main():
    m = PySolarmanV5(HOST, SERIAL, port=PORT, mb_slave_id=SLAVE,
                     socket_timeout=10, v5_error_correction=True)

    print(f"{'time':>8}  {'grid(W)':>8}  {'bat(W)':>8}  {'load(W)':>8}  "
          f"{'inv(W)':>8}  {'SOC':>4}  {'BatV':>6}  {'BatI':>6}")
    print("-" * 70)

    while True:
        try:
            # Block 586..653 in einem Read (Indices: reg - 586)
            regs = m.read_holding_registers(register_addr=586, quantity=68)

            grid = s16(regs[625 - 586])           # x1, signed
            bat  = s16(regs[590 - 586]) * 10      # x10, signed
            load = regs[653 - 586]                # x1, unsigned
            inv  = s16(regs[636 - 586])           # x1, signed
            soc  = regs[588 - 586]                # %
            batv = regs[587 - 586] / 10           # V
            bati = s16(regs[591 - 586]) / 100     # A

            print(f"{time.strftime('%H:%M:%S'):>8}  "
                  f"{grid:>8}  {bat:>8}  {load:>8}  {inv:>8}  "
                  f"{soc:>4}  {batv:>6.1f}  {bati:>6.2f}")

        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')}  ERR {type(e).__name__}: {e}")

        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstop")
