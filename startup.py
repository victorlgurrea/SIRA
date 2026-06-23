#!/usr/bin/env python3
"""Arranque SIRA: deps, ingesta inicial, API + dashboard."""
from __future__ import annotations

import importlib
import secrets
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_DIR, DASHBOARD_DIR = ROOT / "python", ROOT / "dashboard"
DEPS = ("requests", "dotenv", "fastapi", "uvicorn", "dash", "plotly", "pandas")
PIP = {"dotenv": "python-dotenv", "uvicorn": "uvicorn[standard]"}


def say(ok: bool, msg: str) -> None:
    print(f"{'[ok]' if ok else '[!!]'} {msg}")


def ensure_env() -> None:
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists():
        shutil.copy(example, env) if example.exists() else sys.exit("Error: falta .env")
    lines, has_key, changed = env.read_text(encoding="utf-8").splitlines(), False, False
    out = []
    for line in lines:
        if line.startswith("API_KEY="):
            has_key = True
            if line.split("=", 1)[1].strip():
                out.append(line)
            else:
                out.append(f"API_KEY={secrets.token_urlsafe(32)}")
                changed = True
        else:
            out.append(line)
    if not has_key:
        out.append(f"API_KEY={secrets.token_urlsafe(32)}")
        changed = True
    if changed:
        env.write_text("\n".join(out) + "\n", encoding="utf-8")
        say(True, "API_KEY generada en .env")
    else:
        say(True, ".env")


def ensure_deps() -> None:
    miss = [PIP.get(m, m) for m in DEPS if not _importable(m)]
    if miss:
        say(False, f"Instalando: {', '.join(miss)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "-q", "--no-warn-script-location"])
    say(True, "Dependencias Python")


def _importable(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def kill_port(port: int) -> None:
    """Cierra procesos que ocupan un puerto (evita instancias zombie del dashboard/API)."""
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
        except (subprocess.CalledProcessError, FileNotFoundError):
            return
        pids: set[str] = set()
        for line in out.splitlines():
            if f":{port}" not in line or "LISTENING" not in line:
                continue
            parts = line.split()
            if parts and parts[-1].isdigit() and parts[-1] != "0":
                pids.add(parts[-1])
        for pid in pids:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True,
                text=True,
                errors="replace",
            )
        if pids:
            say(True, f"Puerto :{port} liberado ({len(pids)} proceso(s))")
        return

    try:
        out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True, errors="replace")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    pids = [p.strip() for p in out.splitlines() if p.strip().isdigit()]
    for pid in pids:
        subprocess.run(["kill", "-9", pid], capture_output=True)
    if pids:
        say(True, f"Puerto :{port} liberado ({len(pids)} proceso(s))")


def wait_port(host: str, port: int, name: str) -> None:
    for _ in range(45):
        try:
            with socket.create_connection((host, port), timeout=1):
                say(True, f"{name} :{port}")
                return
        except OSError:
            time.sleep(1)
    say(False, f"{name} no respondió en :{port}")


def main() -> None:
    print("=" * 50, "\n  SIRA — Startup\n", "=" * 50, sep="")
    if sys.version_info < (3, 9):
        sys.exit("Error: Python 3.9+ requerido.")
    say(True, f"Python {sys.version.split()[0]}")
    ensure_env()
    ensure_deps()

    sys.path.insert(0, str(PYTHON_DIR))
    from config import ALLOW_DATA_REFRESH, API_HOST, API_PORT, DASHBOARD_HOST, DASHBOARD_PORT, DATA_FILE, ENABLE_API_DOCS
    from ingesta import ejecutar_ingesta

    if API_HOST in ("0.0.0.0", "::"):
        say(False, "API_HOST expuesto a todas las interfaces — usa 127.0.0.1 si solo es consulta local")
    if DASHBOARD_HOST in ("0.0.0.0", "::"):
        say(False, "DASHBOARD_HOST expuesto a todas las interfaces — usa 127.0.0.1 si solo es consulta local")
    if not ALLOW_DATA_REFRESH:
        say(True, "Modo solo consulta (ALLOW_DATA_REFRESH=false)")

    if not DATA_FILE.exists():
        say(False, "Ingesta inicial...")
        ejecutar_ingesta()
    say(True, "Datos listos")

    api_h = "127.0.0.1" if API_HOST in ("0.0.0.0", "") else API_HOST
    dash_h = "127.0.0.1" if DASHBOARD_HOST in ("0.0.0.0", "") else DASHBOARD_HOST
    kill_port(API_PORT)
    kill_port(DASHBOARD_PORT)
    time.sleep(0.5)
    kw = {"creationflags": subprocess.CREATE_NEW_CONSOLE} if sys.platform == "win32" else {}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "api_server:app", "--host", API_HOST, "--port", str(API_PORT)], cwd=PYTHON_DIR, **kw)
    dash = subprocess.Popen([sys.executable, "app.py"], cwd=DASHBOARD_DIR, **kw)
    wait_port(api_h, API_PORT, "API")
    wait_port(dash_h, DASHBOARD_PORT, "Dashboard")

    url = f"http://{dash_h}:{DASHBOARD_PORT}"
    print(f"\n  Dashboard: {url}")
    if ENABLE_API_DOCS:
        print(f"  API docs:  http://{api_h}:{API_PORT}/docs")
    webbrowser.open(url)

    try:
        while api.poll() is None and dash.poll() is None:
            time.sleep(2)
    except KeyboardInterrupt:
        for p in (api, dash):
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
