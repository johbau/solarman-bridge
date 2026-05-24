"""
Live-Monitor: pollt alle 3 Sekunden die relevanten Register und zeigt Veränderungen.
Damit identifizierst du das Grid-Register, indem du eine starke Last einschaltest.
"""

from pysolarmanv5 import PySolarmanV5
import time

HOST   = "192.168.1.100"
SERIAL = 1234567890
PORT   = 8899
SLAVE  = 1

# Verdächtige Kandidaten für Grid-Leistung + bekannte Referenzen
REGS = {
    "SOC          588":  (588,  1, False),
    "Bat Power*10 590":  (590,  1, True),
    "PV1 V?       672":  (672,  1, False),
    "PV2 V?       674":  (674,  1, False),
    "Grid total?  625":  (625,  1, True),
    "Grid ext?    622":  (622,  1, True),
    "Cand 596":          (596,  1, True),
    "Cand 619":          (619,  1, True),
    "Cand 620":          (620,  1, True),
    "Cand 621":          (621,  1, True),
    "Cand 647":          (647,  1, True),
    "Cand 648":          (648,  1, True),
    "Cand 649":          (649,  1, True),
    "L1 power 633":      (633,  1, True),
    "L2 power 634":      (634,  1, True),
    "L3 power 635":      (635,  1, True),
    "L1 power 640":      (640,  1, True),
    "L1 power 650":      (650,  1, True),
    "Inv tot   636":     (636,  1, True),
    "Load tot  653":     (653,  1, True),
}


def as_signed(v):
    return v - 0x10000 if v & 0x8000 else v


def main():
    m = PySolarmanV5(HOST, SERIAL, port=PORT, mb_slave_id=SLAVE,
                     socket_timeout=10, v5_error_correction=True)

    header = " ".join(f"{k.split()[-1]:>6}" for k in REGS)
    labels = " ".join(f"{k.split()[0]:>6}" for k in REGS)
    print(labels)
    print(header)
    print("-" * len(header))

    while True:
        row = []
        for label, (reg, cnt, signed) in REGS.items():
            try:
                v = m.read_holding_registers(register_addr=reg, quantity=cnt)[0]
                if signed:
                    v = as_signed(v)
                row.append(f"{v:>6}")
            except Exception:
                row.append(f"{'ERR':>6}")
        print(" ".join(row))
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstop")
