#!/usr/bin/env bash
# Test der Battery-Mode-Endpunkte vor der evcc-Integration.
# Vorgehen: jeden Modus 30 Sekunden, parallel in App pruefen ob sich
# das WR-Verhalten aendert (Ladestrom, Verkauf, Verbrauchsanteile).

BASE=http://localhost:7071

set -e

echo "=== aktueller Mode ==="
curl -s $BASE/battery_mode | jq .

echo ""
echo "=== switch to HOLD ==="
curl -sX POST -d "hold" $BASE/battery_mode | jq .
echo "wait 30s..."; sleep 30
curl -s $BASE/all | jq '{mode: .mode, soc: .bat_soc, bat: .bat_power, grid: .grid, load: .load}'

echo ""
echo "=== switch to CHARGE ==="
curl -sX POST -d "charge" $BASE/battery_mode | jq .
echo "wait 30s..."; sleep 30
curl -s $BASE/all | jq '{mode: .mode, soc: .bat_soc, bat: .bat_power, grid: .grid, load: .load}'

echo ""
echo "=== switch to NORMAL ==="
curl -sX POST -d "normal" $BASE/battery_mode | jq .
sleep 5
curl -s $BASE/battery_mode | jq .

echo ""
echo "Done. Pruefe in der Solarman-App ob die Slot-Werte wieder auf"
echo "den Ausgangszustand zurueckgestellt sind."
