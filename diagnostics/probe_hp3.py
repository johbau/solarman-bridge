"""
Diagnose-Skript für Deye SUN-25K-SG01HP3-EU-AM2
Liest die typischen HP3-Hybrid-Register und zeigt sie lesbar an.
"""

from pysolarmanv5 import PySolarmanV5

HOST   = "192.168.1.100"
SERIAL = 1234567890
PORT   = 8899
SLAVE  = 1

# (label, register, count, scale, unit, signed)
REGS = [
    # Identifikation
    ("Modell/SN  (504)",     504,  5, 1,     "",     False),

    # PV-Strings (Leistung in 0.1 kW bzw. W je nach FW -> beides ausgeben)
    ("PV1 Power  (672)",     672,  1, 0.1,   "kW",   False),
    ("PV2 Power  (674)",     674,  1, 0.1,   "kW",   False),
    ("PV3 Power  (676)",     676,  1, 0.1,   "kW",   False),
    ("PV4 Power  (678)",     678,  1, 0.1,   "kW",   False),

    # Netz (signed: + = Bezug, - = Einspeisung)
    ("Grid total (625)",     625,  1, 1,     "W",    True),
    ("Grid extern(622)",     622,  1, 1,     "W",    True),

    # Hausverbrauch
    ("Load total (653)",     653,  1, 1,     "W",    False),

    # Batterie
    ("Bat Power  (590)",     590,  1, 1,     "W",    True),
    ("Bat SOC    (588)",     588,  1, 1,     "%",    False),
    ("Bat Voltage(587)",     587,  1, 0.01,  "V",    False),

    # Inverter-Ausgang
    ("Inv Power  (636)",     636,  1, 1,     "W",    True),

    # Tagesenergie / Gesamt (zur Plausibilisierung)
    ("PV today   (529)",     529,  1, 0.1,   "kWh",  False),
    ("PV total   (534)",     534,  2, 0.1,   "kWh",  False),
]


def as_signed16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def fmt(values, scale, unit, signed):
    if values is None:
        return "—"
    if len(values) == 1:
        v = as_signed16(values[0]) if signed else values[0]
        return f"{v * scale:>10.2f} {unit}   raw={values}"
    # Mehrere Register: roh ausgeben + als 32bit kombiniert
    combined = (values[0] << 16) | values[1] if len(values) == 2 else None
    extra = f"   u32={combined * scale:.2f} {unit}" if combined is not None else ""
    return f"raw={values}{extra}"


def main():
    print(f"Verbinde zu {HOST}:{PORT}  Logger-SN={SERIAL}  Slave={SLAVE}\n")
    m = PySolarmanV5(HOST, SERIAL, port=PORT, mb_slave_id=SLAVE, verbose=False,
                     socket_timeout=10, v5_error_correction=True)

    width = max(len(r[0]) for r in REGS)
    for label, reg, count, scale, unit, signed in REGS:
        try:
            values = m.read_holding_registers(register_addr=reg, quantity=count)
            print(f"{label:<{width}} : {fmt(values, scale, unit, signed)}")
        except Exception as e:
            print(f"{label:<{width}} : FEHLER  {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
