# SOC-controlled grid switch (`pi/soc_switch.py`)

*Deutsche Version: [SOC_SWITCH.de.md](SOC_SWITCH.de.md)*

Connects/disconnects the Deye inverter from the mains line via a
**FRITZ!DECT smart plug** (AVM AHA-HTTP API), based on the battery SOC
reported by the solarman bridge (`/bat_soc`).

## Why

- **Summer:** keep the inverter off-grid until the battery is nearly full,
  then connect to **sell** the surplus.
- **Winter:** keep the inverter off-grid until the battery is nearly empty,
  then connect to **buy** energy.

## Switching logic

The season is picked by calendar month (`SUMMER_MONTHS`, default Apr–Sep),
or forced with `SEASON=summer|winter`.

| Season | Plug ON (connect)     | Plug OFF (disconnect)  |
|--------|-----------------------|------------------------|
| Summer | SOC ≥ `SUMMER_ON` (95 %) | SOC ≤ `SUMMER_OFF` (85 %) |
| Winter | SOC ≤ `WINTER_ON` (15 %) | SOC ≥ `WINTER_OFF` (25 %) |

Between the two thresholds the state is **held** (hysteresis), so the plug
never chatters around a single threshold.

Fail-safe behavior:

- SOC unreadable (bridge down/stale) → **no switching**, last state kept.
- FRITZ!Box error → re-login on the next poll, state kept meanwhile.
- Actual plug state is read back every poll (`getswitchstate`), so a manual
  toggle is corrected automatically.

## ⚠ Hardware

A FRITZ!DECT 200/210 switches at most 16 A single-phase (~3.6 kW). The
mains feed of a SUN-25K **must not** run through the plug directly — the
plug may only pilot a suitably rated contactor. Also make sure the house
stays powered while the inverter is off-grid (backup output or separate
mains path).

## Configuration

All settings live in the same `.env` as the bridge (see `.env.example`):

```ini
# FRITZ!Box login (user needs the "Smart Home" permission)
FRITZ_HOST=fritz.box
FRITZ_USER=myuser
FRITZ_PASS=mypassword
# AIN printed on the DECT plug (spaces optional)
FRITZ_AIN=087610000000

# Seasonal thresholds (%)
SEASON=auto            # auto | summer | winter
SUMMER_MONTHS=4,5,6,7,8,9
SUMMER_ON=95
SUMMER_OFF=85
WINTER_ON=15
WINTER_OFF=25

# Bridge URL and poll interval (s)
BRIDGE_URL=http://127.0.0.1:7071
SOC_POLL=60
```

## Install on the Pi

```sh
cp pi/soc_switch.py pi/soc-switch.service /opt/solarman-bridge/
# add the FRITZ_* / season values to /opt/solarman-bridge/.env
sudo cp /opt/solarman-bridge/soc-switch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now soc-switch
journalctl -u soc-switch -f
```

No extra Python dependencies — stdlib only (works with the bridge's venv
or the system Python).

## Test

```sh
python3 pi/soc_switch.py --selftest   # checks the hysteresis/season logic
```

To test the plug end-to-end without waiting for a real SOC, force a season
and lower a threshold temporarily in `.env`, then watch the journal.
