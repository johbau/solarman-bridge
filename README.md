# solarman-bridge

HTTP bridge between a **Deye hybrid inverter with Solarman WiFi dongle** and
**[evcc](https://evcc.io)**. Reads measurements and status values via the
Solarman v5 protocol (port 8899) and exposes them as HTTP endpoints, so that
evcc can talk to the inverter via `source: http` without needing a real
Modbus TCP gateway.

In addition: a write endpoint for **battery control** (Tibber-driven grid
charging when electricity prices are low).

## Hardware

Developed and tested with:

- **Deye SUN-25K-SG01HP3-EU-AM2** (3-phase, high-voltage hybrid, 25 kW)
- Solarman/Deye WiFi logger (LSE-3 / LSW-3, port 8899)
- HV battery ~210 V, 200 Ah
- evcc appliance on Raspberry Pi 4

Other Deye hybrid models with the same logger should work, but Modbus
register addresses may differ — verify with the diagnostic scripts in
[diagnostics/](diagnostics/).

## Why this bridge?

The original Deye WiFi dongle speaks the proprietary Solarman v5 protocol on
port 8899, **not** standard Modbus TCP. The evcc templates for Deye, however,
assume an RS485-to-Modbus-TCP gateway is attached to the inverter — which is
not the case here. Solution: a small Python bridge translates Solarman v5
to HTTP.

```
Deye HP3 -- WiFi dongle --(Solarman v5, port 8899)--> solarman_bridge.py
                                                              |
                                                              v
                                                    evcc (source: http)
```

## What the bridge provides

### Read endpoints (GET)

Current measurements as JSON or plain text:

- `/grid` — grid power (W, signed, + import / − export)
- `/bat_power` — battery power (W, signed, + discharging / − charging)
- `/bat_soc` — state of charge (%)
- `/load` — house consumption (W)
- `/inv` — inverter output power (W)
- `/pv` `/pv1` `/pv2` — PV power total and per string (W)
- `/pv_today` `/pv_total` — PV energy counters (kWh)
- `/all` — all values as JSON
- `/health` — status (200/503)

### Write endpoint (POST)

`POST /battery_mode` with body `normal` | `hold` | `charge`:

- **charge**: forces grid charging (TOU slot SOC=100, Power=25 kW, GridCharge=on)
- **normal**: restores the original TOU slot values
- **hold**: sets slot power=0 (stops grid charging, but PV charging continues
  — see limitation in SETUP.md)

On bridge startup, the original TOU values are read and stored as a
baseline. Mode changes manipulate the currently active slot and are
restored exactly when switching back to `normal`. Each write is verified
via read-back.

## Installation

See **[SETUP.md](SETUP.md)** — installation and maintenance guide for the
Pi (systemd service, evcc UI meters, test scripts).

## How it was built

**[SESSION.md](SESSION.md)** documents the full reverse-engineering
process: register identification, scaling and sign conventions,
verification against app and display, evcc pitfalls. Useful for anyone
working with a similar HP3 setup.

## Project structure

```
solarman-bridge/
  README.md                 - this document
  SETUP.md                  - installation and maintenance guide
  SESSION.md                - session log / reverse engineering notes

  pi/                       - files deployed to the Pi
    solarman_bridge.py      - HTTP bridge (read + write)
    solarman-bridge.service - systemd unit
    meter_*.yaml            - evcc custom-meter configs
    test_battery_mode.sh    - manual test of the write endpoint

  diagnostics/              - local diagnostic scripts
    probe_hp3.py            - read specific registers
    scan_hp3.py             - scan register blocks
    snapshot.py             - synchronized read
    verify_grid.py          - live verification grid/bat/load
    verify_pv.py            - live verification PV V/I/power
    find_pv.py              - find PV registers
    discover_control.py     - read control registers (TOU, limits)
    live_hp3.py             - live monitor of multiple registers

  archive/                  - earlier attempts (direct Modbus)
```

## Configuration

### Diagnostic scripts (laptop)

Copy `.env.example` to `.env` and fill in your inverter details:

```bash
cp .env.example .env
# edit .env: WR_HOST, WR_SERIAL, WR_PORT, WR_SLAVE
```

All scripts in `diagnostics/` automatically pick up these values via the
shared `_config.py` loader. The `.env` file is gitignored.

### Bridge (Pi)

Set the inverter IP and logger serial number at the top of
[`pi/solarman_bridge.py`](pi/solarman_bridge.py):

```python
WR_HOST    = "192.168.x.x"
WR_SERIAL  = 1234567890     # 10-digit number from the WiFi dongle label
```

## License

MIT — use at your own risk. Writes to the inverter may overwrite TOU
settings; original values are saved before modification, but if TOU is
changed in the app while the bridge is running, the bridge must be
restarted (see SETUP.md).
