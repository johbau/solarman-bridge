"""
Liest (nur lesend, keine Writes!) die typischen Deye-Hybrid Control-Register
fuer Batterie-Limits, Arbeitsmodus und Time-of-Use-Slots.

Ziel: Bestaetigen welche Register-Adressen beim SUN-25K-SG01HP3 fuer was
zustaendig sind, BEVOR wir Writes implementieren.

Vergleiche die Ausgabe mit den App-Settings (System Mode / Battery / TOU).
"""

from pysolarmanv5 import PySolarmanV5
import time

m = PySolarmanV5("192.168.1.100", 1234567890, port=8899, mb_slave_id=1,
                 socket_timeout=10, v5_error_correction=True)


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def read_one(reg, label, scale=1, signed=False, fmt="raw"):
    try:
        v = m.read_holding_registers(register_addr=reg, quantity=1)[0]
        sv = s16(v) if signed else v
        if fmt == "hhmm":
            disp = f"{sv//100:02d}:{sv%100:02d}"
        elif fmt == "bool":
            disp = "on" if sv else "off"
        else:
            disp = f"{sv * scale}"
        print(f"  reg {reg:>4} = {v:>6}  -> {disp:<12}  {label}")
    except Exception as e:
        print(f"  reg {reg:>4}  ERR {type(e).__name__}: {e}")
    time.sleep(0.1)


print("=== Batterie-Grundeinstellungen ===")
read_one(102, "Max Charge Current (LP3)         (A?)")
read_one(103, "Max Discharge Current (LP3)      (A?)")
read_one(108, "Battery Capacity                 (Ah?)")
read_one(217, "Battery Low Capacity Shutdown    (%?)")
read_one(218, "Battery Restart Capacity         (%?)")

print("\n=== System / Working Mode ===")
read_one(141, "Energy Mode (0=Self / 1=ZeroExp)")
read_one(142, "Solar Sell                        (0/1)", fmt="bool")
read_one(143, "Max Sell Power                    (W?)")
read_one(244, "Battery Working Mode              (0..3)")

print("\n=== Time of Use (6 Slots) ===")
print("--- Slot-Zeiten (HHMM) ---")
for i, reg in enumerate([148, 149, 150, 151, 152, 153], 1):
    read_one(reg, f"Slot {i} Start", fmt="hhmm")
print("--- Slot-Leistung (W) ---")
for i, reg in enumerate([154, 155, 156, 157, 158, 159], 1):
    read_one(reg, f"Slot {i} Power")
print("--- Slot-Ziel-SOC (%) ---")
for i, reg in enumerate([166, 167, 168, 169, 170, 171], 1):
    read_one(reg, f"Slot {i} SOC")
print("--- Slot-Grid-Charge-Enable (0/1) ---")
for i, reg in enumerate([172, 173, 174, 175, 176, 177], 1):
    read_one(reg, f"Slot {i} Grid Charge", fmt="bool")
print("--- Slot-Gen-Charge-Enable (0/1) ---")
for i, reg in enumerate([178, 179, 180, 181, 182, 183], 1):
    read_one(reg, f"Slot {i} Gen Charge", fmt="bool")

print("\n=== Alternative HP3-Kandidaten ===")
read_one(232, "Possibly: Active TOU Grid Charge", fmt="bool")
read_one(247, "Possibly: Max Charge Current HP3 (A?)")
read_one(248, "Possibly: Max Discharge Current HP3(A?)")
read_one(252, "Possibly: Charge Current Limit   (A?)")
read_one(253, "Possibly: Discharge Current Limit(A?)")
