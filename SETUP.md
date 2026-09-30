# Solarman-to-evcc bridge — setup on the Raspberry Pi

Bridges the Deye WiFi logger (Solarman v5 on port 8899) to evcc via an HTTP
service so that evcc custom meters with `source: http` can read inverter
values.

## Hardware / software context

- Inverter: **Deye SUN-25K-SG01HP3-EU-AM2**
- WiFi logger: IP `192.168.1.100`, serial `1234567890`
- evcc runs on a Pi (`evcc.local`) as the evcc-OS appliance, user `evcc`,
  config in `/var/lib/evcc/evcc.db` (DB mode, UI-managed config)
- evcc's Deye templates do NOT work with this logger — they expect real
  Modbus TCP. Solution: a bridge translates Solarman v5 → HTTP/JSON.

## Verified Modbus registers

| Reg | Content | Scale | Sign |
|-----|---------|-------|------|
| 587 | Battery voltage | x0.1 V | unsigned |
| 588 | Battery SOC | x1 % | unsigned |
| 590 | Battery power | x10 W | + discharging / - charging |
| 591 | Battery current | x0.01 A | signed |
| 625 | Grid power | x1 W | + import / - export |
| 636 | Inverter output power | x1 W | signed |
| 653 | House consumption | x1 W | unsigned |
| 529 | PV daily production | x0.1 kWh | unsigned |
| 534 | PV total production | x0.1 kWh | unsigned |
| 676 | PV1 voltage | x0.1 V | unsigned |
| 677 | PV1 current | x0.1 A | unsigned |
| 678 | PV2 voltage | x0.1 V | unsigned |
| 679 | PV2 current | x0.1 A | unsigned |
| 102 | Battery capacity | x1 Ah | unsigned |
| 108 | Max charge current | x1 A | unsigned |
| 109 | Max discharge current | x1 A | unsigned |
| 141 | Energy pattern (0/1/2) | enum | unsigned |
| 143 | Max sell power | x10 W | unsigned |
| 148-153 | TOU slot start times | HHMM | unsigned |
| 154-159 | TOU slot power | x10 W | unsigned |
| 166-171 | TOU slot target SOC | x1 % | unsigned |
| 172-177 | TOU slot grid charge | 0/1 | unsigned |

Note: the HP3 has no reliable single register for "total PV power". The
bridge computes PV power from V x I per string: `PV = V676*I677 + V678*I679`.

### Battery hardware limits

The app shows for the battery:
- Capacity 200 Ah (reg 102)
- Max charge current 37 A (reg 108)
- Max discharge current 40 A (reg 109)

At ~210 V HV battery voltage these translate to effective power limits of
roughly 7.8 kW charging / 8.4 kW discharging. These limits ALWAYS apply,
even when the TOU slot specifies a higher power. With CHARGE mode (25 kW
in the slot) the battery therefore actually charges with only ~7.5 kW from
the grid.

## Files

```
solarman/
  SETUP.md
  SESSION.md
  pi/                   # install on the Pi
    solarman_bridge.py        - HTTP service
    solarman-bridge.service   - systemd unit
    meter_grid_http.yaml      - evcc custom meter for grid
    meter_battery_http.yaml   - evcc custom meter for battery + SOC + mode
    meter_pv_http.yaml        - evcc custom meter for PV
    test_battery_mode.sh      - test script for the battery-mode endpoint
  diagnostics/          # run locally on the laptop (venv with pysolarmanv5)
    probe_hp3.py              - read specific registers
    scan_hp3.py               - scan register blocks
    live_hp3.py               - live monitor
    snapshot.py               - one-shot read
    verify_grid.py            - live verification of grid values
    verify_pv.py              - live verification of PV values
    find_pv.py                - find PV registers
    discover_control.py       - read control registers (TOU, limits)
  archive/              # earlier attempts kept for reference
    evcc.yaml, meter_grid.yaml, meter_battery.yaml
```

## Installation on the Pi

### 1. Copy files (from the laptop)

```bash
scp pi/solarman_bridge.py admin@evcc.local:/tmp/
scp pi/solarman-bridge.service admin@evcc.local:/tmp/
```

### 2. Set up on the Pi

```bash
ssh admin@evcc.local

# Target directory
sudo mkdir -p /opt/solarman-bridge
sudo mv /tmp/solarman_bridge.py /opt/solarman-bridge/

# venv + pysolarmanv5
sudo python3 -m venv /opt/solarman-bridge/.venv
sudo /opt/solarman-bridge/.venv/bin/pip install pysolarmanv5

# Permissions for the evcc user
sudo chown -R evcc:evcc /opt/solarman-bridge

# systemd service
sudo mv /tmp/solarman-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now solarman-bridge
```

### 3. Check status

```bash
sudo systemctl status solarman-bridge
sudo journalctl -u solarman-bridge -f
```

Expected log line: `HTTP server listening on :7071`.

### 4. Test functionality

```bash
curl http://localhost:7071/all
curl http://localhost:7071/grid
curl http://localhost:7071/bat_power
curl http://localhost:7071/bat_soc
curl http://localhost:7071/health
```

Compare values with the Solarman app — they should match exactly.

## HTTP endpoints (read)

| URL | Content | Format |
|-----|---------|--------|
| `/grid` | Grid power (W, signed) | plain number |
| `/bat_power` | Battery power (W, signed) | plain number |
| `/bat_soc` | SOC (%) | plain number |
| `/load` | House consumption (W) | plain number |
| `/inv` | Inverter output (W) | plain number |
| `/bat_v` | Battery voltage (V) | number |
| `/bat_i` | Battery current (A) | number |
| `/pv` | Total PV power (W) | plain number |
| `/pv1` | PV1 power (W) | plain number |
| `/pv2` | PV2 power (W) | plain number |
| `/pv1_v` | PV1 voltage (V) | number |
| `/pv1_i` | PV1 current (A) | number |
| `/pv2_v` | PV2 voltage (V) | number |
| `/pv2_i` | PV2 current (A) | number |
| `/pv_today` | PV daily production (kWh) | number |
| `/pv_total` | PV total production (kWh) | number |
| `/battery_mode` | Current battery mode + slot info | JSON |
| `/all` | All values + age_s | JSON |
| `/health` | Service status | JSON, 200/503 |

## HTTP endpoint (write)

`POST /battery_mode` with body `normal` | `hold` | `charge` (or `1`/`2`/`3`).

| Mode | Effect | Use case |
|------|--------|----------|
| `normal` | Restore original TOU slot | Default |
| `hold` | Active slot Power=0 (only grid charging blocked) | See limitation below |
| `charge` | Active slot SOC=100, Power=25 kW, GridCharge=on | Tibber low price, grid charge |

### Limitation: HOLD mode

HOLD mode sets the TOU slot power to 0. On the Deye HP3 this "Power" value
is **only the grid-charge limit**, not the overall battery power. As a
result:

- Grid charging is stopped ✓
- The battery can still be charged from **PV surplus** ✗
- The battery can still discharge to **cover the load** ✗

Verified during testing: with HOLD active and PV production, the battery
still charged (e.g. PV 1940 W → load 520 W + battery 1420 W).

**Consequence:** HOLD is NOT suitable for the evcc wallbox use case
(holding the battery while the EV charges from PV surplus). For
Tibber low-price grid charging, HOLD is irrelevant — only `normal` and
`charge` are needed there.

If HOLD is really needed later (e.g. EV surplus charging), a different
strategy must be tested — e.g. temporarily setting register 108 (max
charge current) to 0 or finding a dedicated battery-disable register.

Example:
```bash
curl -X POST -d "charge" http://localhost:7071/battery_mode
curl -X POST -d "normal" http://localhost:7071/battery_mode
curl     http://localhost:7071/battery_mode   # status
```

WARNING: The bridge remembers the original values of the manipulated slot
on startup. If you change TOU slots in the app while the bridge is
running, those changes are lost when switching back to `normal`. Fix:
after app changes, restart the bridge once:
```bash
sudo systemctl restart solarman-bridge
```

## evcc configuration

In the evcc UI (http://evcc.local:7070) → Settings → Devices → Add.

### Meter "grid" (type: energy meter → custom)

```yaml
power:
  source: http
  uri: http://localhost:7071/grid
  method: GET
  timeout: 5s
```

### Meter "battery" (type: battery storage → custom)

```yaml
power:
  source: http
  uri: http://localhost:7071/bat_power
  method: GET
  timeout: 5s
soc:
  source: http
  uri: http://localhost:7071/bat_soc
  method: GET
  timeout: 5s
# Required since evcc 0.3xx; without it evcc fails at startup with
# "battery mode: no supported modes, add batteryModes".
# hold is deliberately not declared (see HOLD limitation above).
batteryModes: [normal, charge]
batterymode:
  source: http
  uri: http://localhost:7071/battery_mode
  method: POST
  body: "{{.mode}}"
  headers:
    - content-type: text/plain
  timeout: 10s
```

### Meter "pv" (type: PV system → custom)

```yaml
power:
  source: http
  uri: http://localhost:7071/pv
  method: GET
  timeout: 5s
energy:
  source: http
  uri: http://localhost:7071/pv_total
  method: GET
  timeout: 5s
```

## Maintenance

### Restart service

```bash
sudo systemctl restart solarman-bridge
```

### View logs

```bash
sudo journalctl -u solarman-bridge -f          # live
sudo journalctl -u solarman-bridge -n 100 --no-pager   # last 100 lines
```

### Edit script (e.g. extend PV registers)

```bash
sudo -u evcc nano /opt/solarman-bridge/solarman_bridge.py
sudo systemctl restart solarman-bridge
```

### Update library

```bash
sudo /opt/solarman-bridge/.venv/bin/pip install -U pysolarmanv5
sudo systemctl restart solarman-bridge
```

## Troubleshooting

### `connection refused` on port 7071

Service is not running. Check with `sudo systemctl status solarman-bridge`.

### `503 stale data, age=…s`

The bridge cannot reach the inverter. Check logs:
```bash
sudo journalctl -u solarman-bridge -n 50 --no-pager
```
Common causes: dongle temporarily offline (power cycle) or WiFi dropout.

### After an evcc update: grid/pv/battery all empty, bridge `/all` fine

Check `curl http://evcc.local:7070/api/state | grep fatal`. If it says
`battery mode: no supported modes, add batteryModes`, the battery meter
needs the `batteryModes` line from the config above (evcc UI → Devices →
battery meter → edit → save, then restart evcc).

### evcc shows 0 / wrong values

Run `curl http://localhost:7071/all` on the Pi — if those values are
correct, the issue is in the evcc meter config (usage grid/battery/pv
assigned correctly?).

### Inverter IP changes (DHCP)

Set up a DHCP reservation for the WiFi dongle in your router. Alternative:
configure `WR_HOST` in `/opt/solarman-bridge/solarman_bridge.py` as a
hostname (e.g. `deye-logger.local`) instead of an IP.

## Next steps

1. Install bridge on Pi, start service, run curl tests
2. Create grid and battery meters in the evcc UI, verify in the dashboard
3. Identify PV registers during the day with `snapshot.py`, extend
   `solarman_bridge.py`, create PV meter in evcc
