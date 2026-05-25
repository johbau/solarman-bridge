"""
Shared config loader for the solarman bridge.

Reads WR_HOST / WR_SERIAL / WR_PORT / WR_SLAVE from a .env file next to
the bridge script, or from the process environment. Falls back to
placeholder values if neither is set (with a warning).

Usage in the bridge:

    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _config import WR_HOST, WR_SERIAL, WR_PORT, WR_SLAVE
"""

import os
import sys
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_bridge_dir = Path(__file__).resolve().parent
_load_env_file(_bridge_dir / ".env")

WR_HOST   = os.environ.get("WR_HOST",   "192.168.1.100")
WR_SERIAL = int(os.environ.get("WR_SERIAL", "1234567890"))
WR_PORT   = int(os.environ.get("WR_PORT",   "8899"))
WR_SLAVE  = int(os.environ.get("WR_SLAVE",  "1"))


if WR_SERIAL == 1234567890:
    import sys as _sys
    print("WARNING: WR_SERIAL is the placeholder value. "
          "Copy pi/.env.example to pi/.env and fill in real values.",
          file=_sys.stderr)
