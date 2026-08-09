"""
SOC-gesteuerter AVM-Schalter (FRITZ!DECT) fuer den Deye-Wechselrichter.

Liest den Batterie-SOC vom solarman_bridge (/bat_soc) und schaltet eine
FRITZ!DECT-Steckdose ueber das FRITZ!Box AHA-HTTP-Interface — saisonal:

  Sommer (SUMMER_MONTHS): EIN bei SOC >= SUMMER_ON und PV >= PV_ON
                          (Ueberschuss verkaufen),
                          AUS bei SOC <= SUMMER_OFF oder PV <= PV_OFF
  Winter (sonst):         EIN bei SOC <= WINTER_ON  (Strom zukaufen),
                          AUS bei SOC >= WINTER_OFF
  dazwischen: Zustand halten (Hysterese)

Konfiguration via .env im selben Verzeichnis (siehe .env.example):
  FRITZ_HOST, FRITZ_USER, FRITZ_PASS, FRITZ_AIN,
  SUMMER_MONTHS, SUMMER_ON/OFF, WINTER_ON/OFF, PV_ON/OFF,
  SEASON (auto|summer|winter)

Fail-safe: Wenn der SOC nicht lesbar ist (Bridge down/stale), wird NICHT
geschaltet — der letzte Zustand bleibt erhalten.

Selbsttest der Hysterese-Logik: python3 soc_switch.py --selftest
"""

import hashlib
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# ---------- Konfiguration (.env wie beim Bridge) ----------
_cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_cfg_file):
    with open(_cfg_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))

FRITZ_HOST = os.environ.get("FRITZ_HOST", "fritz.box")
FRITZ_USER = os.environ.get("FRITZ_USER", "")
FRITZ_PASS = os.environ.get("FRITZ_PASS", "")
FRITZ_AIN  = os.environ.get("FRITZ_AIN", "").replace(" ", "")
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:7071")
POLL       = float(os.environ.get("SOC_POLL", "60"))

# Saison: auto = nach Monat, sonst fest "summer"/"winter"
SEASON        = os.environ.get("SEASON", "auto")
SUMMER_MONTHS = {int(m) for m in
                 os.environ.get("SUMMER_MONTHS", "4,5,6,7,8,9").split(",")}
SUMMER_ON  = float(os.environ.get("SUMMER_ON",  "95"))
SUMMER_OFF = float(os.environ.get("SUMMER_OFF", "85"))
WINTER_ON  = float(os.environ.get("WINTER_ON",  "15"))
WINTER_OFF = float(os.environ.get("WINTER_OFF", "25"))

# Sommer zusaetzlich: EIN nur bei PV-Leistung >= PV_ON (W),
# AUS sobald PV <= PV_OFF (W). Hysterese gegen Wolken-Flattern.
PV_ON  = float(os.environ.get("PV_ON",  "200"))
PV_OFF = float(os.environ.get("PV_OFF", "50"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("soc_switch")


# ---------- FRITZ!Box AHA-HTTP ----------
def _http_get(url: str, timeout: float = 10) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace").strip()


def _pbkdf2_response(challenge: str, password: str) -> str:
    # challenge: "2$iter1$salt1$iter2$salt2" (FRITZ!OS >= 7.24)
    _, it1, salt1, it2, salt2 = challenge.split("$")
    h1 = hashlib.pbkdf2_hmac("sha256", password.encode(),
                             bytes.fromhex(salt1), int(it1))
    h2 = hashlib.pbkdf2_hmac("sha256", h1, bytes.fromhex(salt2), int(it2))
    return f"{salt2}${h2.hex()}"


def _md5_response(challenge: str, password: str) -> str:
    md5 = hashlib.md5(f"{challenge}-{password}".encode("utf-16-le")).hexdigest()
    return f"{challenge}-{md5}"


def fritz_login() -> str:
    """Hole eine Session-ID von der FRITZ!Box."""
    base = f"http://{FRITZ_HOST}/login_sid.lua?version=2"
    root = ET.fromstring(_http_get(base))
    challenge = root.findtext("Challenge", "")
    if challenge.startswith("2$"):
        response = _pbkdf2_response(challenge, FRITZ_PASS)
    else:
        response = _md5_response(challenge, FRITZ_PASS)
    url = (f"{base}&username={urllib.parse.quote(FRITZ_USER)}"
           f"&response={urllib.parse.quote(response)}")
    root = ET.fromstring(_http_get(url))
    sid = root.findtext("SID", "0" * 16)
    if sid == "0" * 16:
        raise RuntimeError("FRITZ!Box-Login fehlgeschlagen (SID=0)")
    return sid


def fritz_cmd(sid: str, cmd: str) -> str:
    url = (f"http://{FRITZ_HOST}/webservices/homeautoswitch.lua"
           f"?ain={urllib.parse.quote(FRITZ_AIN)}&switchcmd={cmd}&sid={sid}")
    return _http_get(url)


# ---------- Saison + Hysterese ----------
def season(month: int) -> str:
    if SEASON in ("summer", "winter"):
        return SEASON
    return "summer" if month in SUMMER_MONTHS else "winter"


def decide(soc: float, mode: str, pv: float = 0.0):
    """True=ein, False=aus, None=Zustand halten (Hysterese)."""
    if mode == "summer":          # voll + PV vorhanden -> verkaufen
        if pv <= PV_OFF:
            return False          # keine PV -> nichts zu verkaufen
        if soc >= SUMMER_ON and pv >= PV_ON:
            return True
        if soc <= SUMMER_OFF:
            return False
    else:                         # leer -> zukaufen
        if soc <= WINTER_ON:
            return True
        if soc >= WINTER_OFF:
            return False
    return None


def read_value(path: str) -> float:
    return float(_http_get(f"{BRIDGE_URL}/{path}", timeout=5))


# ---------- Hauptschleife ----------
def main():
    if not (FRITZ_USER and FRITZ_PASS and FRITZ_AIN):
        log.error("FRITZ_USER/FRITZ_PASS/FRITZ_AIN fehlen in .env")
        sys.exit(1)
    if (SUMMER_OFF >= SUMMER_ON or WINTER_ON >= WINTER_OFF
            or PV_OFF >= PV_ON):
        log.error("Hysterese kaputt: SUMMER_OFF < SUMMER_ON, "
                  "WINTER_ON < WINTER_OFF und PV_OFF < PV_ON noetig")
        sys.exit(1)

    sid = None
    log.info("Start: Sommer EIN>=%s%% & PV>=%sW / AUS<=%s%% oder PV<=%sW, "
             "Winter EIN<=%s%%/AUS>=%s%%, Saison=%s, Poll %ss",
             SUMMER_ON, PV_ON, SUMMER_OFF, PV_OFF,
             WINTER_ON, WINTER_OFF, SEASON, POLL)
    last_mode = None
    while True:
        mode = season(time.localtime().tm_mon)
        try:
            soc = read_value("bat_soc")
            pv = read_value("pv") if mode == "summer" else 0.0
        except Exception as e:
            log.warning("SOC/PV nicht lesbar (%s) — halte Zustand", e)
            time.sleep(POLL)
            continue

        if mode != last_mode:
            log.info("Saison-Modus: %s", mode)
            last_mode = mode
        want = decide(soc, mode, pv)
        if want is not None:
            try:
                if sid is None:
                    sid = fritz_login()
                state = fritz_cmd(sid, "getswitchstate")
                if state == "inval":
                    raise RuntimeError(f"AIN {FRITZ_AIN} unbekannt")
                is_on = state == "1"
                if want != is_on:
                    fritz_cmd(sid, "setswitchon" if want else "setswitchoff")
                    log.info("SOC %.1f%%, PV %.0fW -> Steckdose %s",
                             soc, pv, "EIN" if want else "AUS")
            except Exception as e:
                log.warning("FRITZ-Fehler (%s) — neuer Login beim naechsten Poll", e)
                sid = None
        time.sleep(POLL)


def selftest():
    # Sommer: voll + PV -> verkaufen (Defaults 95/85, PV 200/50)
    assert decide(96, "summer", pv=500) is True
    assert decide(95, "summer", pv=200) is True
    assert decide(90, "summer", pv=500) is None   # Hysterese: halten
    assert decide(85, "summer", pv=500) is False
    assert decide(20, "summer", pv=500) is False
    # Sommer: PV-Bedingung
    assert decide(96, "summer", pv=0) is False    # keine PV -> AUS
    assert decide(96, "summer", pv=50) is False   # PV <= PV_OFF -> AUS
    assert decide(96, "summer", pv=100) is None   # PV-Hysterese: halten
    assert decide(90, "summer", pv=100) is None   # halten
    # Winter: leer -> zukaufen (Defaults 15/25)
    assert decide(10, "winter") is True
    assert decide(15, "winter") is True
    assert decide(20, "winter") is None   # Hysterese: halten
    assert decide(25, "winter") is False
    assert decide(90, "winter") is False
    # Saison nach Monat (Default 4-9 = Sommer)
    assert season(7) == "summer"
    assert season(12) == "winter"
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
