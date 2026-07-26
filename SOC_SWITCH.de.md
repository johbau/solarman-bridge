# SOC-gesteuerter Netzschalter (`pi/soc_switch.py`)

*English version: [SOC_SWITCH.md](SOC_SWITCH.md)*

Verbindet/trennt den Deye-Wechselrichter mit dem Stromnetz ueber eine
**FRITZ!DECT-Steckdose** (AVM AHA-HTTP-API), gesteuert vom Batterie-SOC,
den die Solarman-Bridge liefert (`/bat_soc`).

## Warum

- **Sommer:** Wechselrichter bleibt vom Netz getrennt, bis die Batterie
  fast voll ist — dann verbinden, um den Ueberschuss zu **verkaufen**.
- **Winter:** Wechselrichter bleibt vom Netz getrennt, bis die Batterie
  fast leer ist — dann verbinden, um Strom zu **kaufen**.

## Schaltlogik

Die Saison wird ueber den Kalendermonat bestimmt (`SUMMER_MONTHS`,
Standard April–September) oder mit `SEASON=summer|winter` fest vorgegeben.

| Saison | Steckdose EIN (verbinden)   | Steckdose AUS (trennen)     |
|--------|-----------------------------|-----------------------------|
| Sommer | SOC ≥ `SUMMER_ON` (95 %)    | SOC ≤ `SUMMER_OFF` (85 %)   |
| Winter | SOC ≤ `WINTER_ON` (15 %)    | SOC ≥ `WINTER_OFF` (25 %)   |

Zwischen den beiden Schwellen wird der Zustand **gehalten** (Hysterese) —
die Steckdose flattert also nicht um eine einzelne Schwelle herum.

Fail-safe-Verhalten:

- SOC nicht lesbar (Bridge down/stale) → **kein Schalten**, letzter
  Zustand bleibt erhalten.
- FRITZ!Box-Fehler → neuer Login beim naechsten Poll, Zustand bleibt
  solange erhalten.
- Der tatsaechliche Steckdosen-Zustand wird bei jedem Poll zurueckgelesen
  (`getswitchstate`) — ein manuelles Umschalten wird automatisch
  korrigiert.

## ⚠ Hardware

Eine FRITZ!DECT 200/210 schaltet maximal 16 A einphasig (~3,6 kW). Die
Netzzuleitung eines SUN-25K darf **nicht** direkt ueber die Steckdose
laufen — die Steckdose darf nur ein ausreichend dimensioniertes Schuetz
ansteuern. Ausserdem sicherstellen, dass das Haus versorgt bleibt,
waehrend der Wechselrichter vom Netz getrennt ist (Backup-Ausgang oder
separater Netzpfad).

## Konfiguration

Alle Einstellungen liegen in derselben `.env` wie die Bridge
(siehe `.env.example`):

```ini
# FRITZ!Box-Login (Benutzer braucht die Berechtigung "Smart Home")
FRITZ_HOST=fritz.box
FRITZ_USER=myuser
FRITZ_PASS=mypassword
# AIN der DECT-Steckdose (steht auf dem Geraet, Leerzeichen egal)
FRITZ_AIN=087610000000

# Saisonale Schwellen (%)
SEASON=auto            # auto | summer | winter
SUMMER_MONTHS=4,5,6,7,8,9
SUMMER_ON=95
SUMMER_OFF=85
WINTER_ON=15
WINTER_OFF=25

# Bridge-URL und Poll-Intervall (s)
BRIDGE_URL=http://127.0.0.1:7071
SOC_POLL=60
```

## Installation auf dem Pi

```sh
cp pi/soc_switch.py pi/soc-switch.service /opt/solarman-bridge/
# FRITZ_*- / Saison-Werte in /opt/solarman-bridge/.env eintragen
sudo cp /opt/solarman-bridge/soc-switch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now soc-switch
journalctl -u soc-switch -f
```

Keine zusaetzlichen Python-Abhaengigkeiten — nur Standardbibliothek
(laeuft mit dem venv der Bridge oder dem System-Python).

## Test

```sh
python3 pi/soc_switch.py --selftest   # prueft Hysterese-/Saison-Logik
```

Um die Steckdose end-to-end zu testen, ohne auf einen echten SOC zu
warten: Saison in der `.env` fest vorgeben, eine Schwelle temporaer
absenken und das Journal beobachten.
