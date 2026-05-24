"""
Shared config loader for diagnostic scripts.

Reads WR_HOST / WR_SERIAL / WR_PORT / WR_SLAVE from a .env file at the
repo root, or from the process environment. Falls back to placeholder
values if neither is set (with a warning).

Usage in a diagnostic script:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
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


_repo_root = Path(__file__).resolve().parent.parent
_load_env_file(_repo_root / ".env")

WR_HOST   = os.environ.get("WR_HOST",   "192.168.1.100")
WR_SERIAL = int(os.environ.get("WR_SERIAL", "1234567890"))
WR_PORT   = int(os.environ.get("WR_PORT",   "8899"))
WR_SLAVE  = int(os.environ.get("WR_SLAVE",  "1"))


if WR_SERIAL == 1234567890:
    print("WARNING: WR_SERIAL is the placeholder value. "
          "Copy .env.example to .env and fill in real values.",
          file=sys.stderr)
