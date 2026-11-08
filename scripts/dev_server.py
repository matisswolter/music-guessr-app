"""Dev server: run Music Guessr as a web app and restart it whenever a file in src/ changes.

    python scripts/dev_server.py            # http://localhost:8550
    python scripts/dev_server.py --port 9000

`flet run -d -r --web` can't restart reliably: the old process keeps the port while a
browser tab is connected. This runner force-stops it instead. After a restart, press F5.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def snapshot() -> dict[Path, float]:
    return {p: p.stat().st_mtime for p in SRC.rglob("*.py") if "storage" not in p.parts}


def start(port: int) -> subprocess.Popen:
    env = {
        **os.environ,
        "FLET_FORCE_WEB_SERVER": "true",
        "FLET_SERVER_PORT": str(port),
        # same data folder as `flet run`, so logins and stats are shared
        "FLET_APP_STORAGE_DATA": str(SRC / "storage" / "data"),
        "FLET_APP_STORAGE_TEMP": str(SRC / "storage" / "temp"),
    }
    Path(env["FLET_APP_STORAGE_DATA"]).mkdir(parents=True, exist_ok=True)
    print(f"▶ Music Guessr on http://localhost:{port}", flush=True)
    return subprocess.Popen([sys.executable, "-u", "main.py"], cwd=SRC, env=env, start_new_session=True)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL)  # don't wait for open browser connections
        proc.wait()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8550)
    port = parser.parse_args().port

    state = snapshot()
    proc = start(port)
    try:
        while True:
            time.sleep(1)
            new = snapshot()
            if new != state:
                changed = sorted(str(p.relative_to(ROOT)) for p in set(new) ^ set(state) | {
                    p for p in new if p in state and new[p] != state[p]})
                print(f"↻ changed: {', '.join(changed)} – restarting (press F5 in the browser)", flush=True)
                state = new
                stop(proc)
                proc = start(port)
    except KeyboardInterrupt:
        pass
    finally:
        stop(proc)


if __name__ == "__main__":
    main()
