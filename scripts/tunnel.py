"""Configure and run the official tunnel client without logging credentials."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "tunnel"
CLIENT = RUNTIME / "tunnel-client.exe"
CONFIG = RUNTIME / "project-brain.yaml"
SETTINGS = RUNTIME / "settings.json"
SECRET = RUNTIME / "runtime-key.dpapi"


def environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["TEMP"] = env["TMP"] = str(ROOT / ".runtime" / "tmp")
    Path(env["TEMP"]).mkdir(parents=True, exist_ok=True)
    # Go uses proxy environment variables, not the Windows browser proxy registry.
    # Respect explicit environment settings; otherwise reuse the user's system proxy.
    proxies = urllib.request.getproxies()
    for scheme in ("http", "https"):
        if not env.get(scheme.upper() + "_PROXY") and not env.get(scheme + "_proxy"):
            proxy = proxies.get(scheme)
            if proxy:
                env[scheme.upper() + "_PROXY"] = proxy if "://" in proxy else "http://" + proxy
    env.setdefault("NO_PROXY", env.get("no_proxy", "localhost,127.0.0.1,::1"))
    if SETTINGS.exists():
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        git = settings.get("git_executable")
        if git and Path(git).is_file():
            env["PATH"] = str(Path(git).parent) + os.pathsep + env.get("PATH", "")
    if SECRET.exists():
        import win32crypt
        env["CONTROL_PLANE_API_KEY"] = win32crypt.CryptUnprotectData(
            SECRET.read_bytes(), None, None, None, 0
        )[1].decode("utf-8")
    return env


def configure(tunnel_id: str | None, replace_key: bool = False) -> None:
    import win32crypt
    RUNTIME.mkdir(parents=True, exist_ok=True)
    settings = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    tunnel_id = tunnel_id or input("Tunnel ID (tunnel_...): ").strip()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]+", tunnel_id):
        raise SystemExit("Invalid tunnel ID. Copy the ID from OpenAI Platform > Tunnels.")
    if replace_key or not SECRET.exists():
        key = getpass.getpass("Runtime API key (hidden, not an admin key): ").strip()
        if not key:
            raise SystemExit("No key entered; configuration cancelled.")
        SECRET.write_bytes(win32crypt.CryptProtectData(
            key.encode("utf-8"), "Project Brain MCP tunnel runtime key", None, None, None, 0
        ))
    git = shutil.which("git") or settings.get("git_executable")
    if not git:
        raise SystemExit("Git not found. Add your installed Git to PATH and configure again.")
    command = f'"{Path(sys.executable).as_posix()}" -m project_brain.server --transport stdio'
    config = {
        "config_version": 1,
        "control_plane": {"base_url": "https://api.openai.com", "tunnel_id": tunnel_id,
                          "api_key": "env:CONTROL_PLANE_API_KEY"},
        "health": {"listen_addr": "127.0.0.1:0", "url_file": str(RUNTIME / "health.url")},
        "admin_ui": {"open_browser": False},
        "log": {"level": "warn", "format": "json"},
        "mcp": {"commands": [{"channel": "main", "command": command}]},
    }
    # JSON is a YAML subset and avoids shell/quote interpolation in paths.
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    SETTINGS.write_text(json.dumps({"tunnel_id": tunnel_id, "git_executable": git}, indent=2), encoding="utf-8")
    print("Configured. The runtime key is encrypted with Windows DPAPI for this Windows user.")
    print("Next: run start_chatgpt.bat and keep the window open while using ChatGPT.")


def status() -> None:
    """Check recent successful remote polling, not just the local ready endpoint."""
    try:
        base = (RUNTIME / "health.url").read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"http://127\.0\.0\.1:\d+", base):
            raise ValueError("Unexpected health URL")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "/readyz", timeout=5) as response:
            ready = response.status == 200
        with opener.open(base + "/metrics", timeout=5) as response:
            metrics = response.read().decode("utf-8")
        match = re.search(r"^commands_poll_last_successful_timestamp_seconds(?:\{[^\n]*\})?\s+([\d.eE+-]+)$", metrics, re.MULTILINE)
        last_success = float(match.group(1)) if match else 0
        age = time.time() - last_success if last_success else None
        connected = bool(ready and age is not None and 0 <= age < 90)
        print(json.dumps({"local_ready": ready, "openai_polling_connected": connected,
                          "last_success_age_seconds": round(age, 1) if age is not None else None,
                          "local_ui": base + "/ui"}, indent=2))
        raise SystemExit(0 if connected else 1)
    except (OSError, ValueError) as exc:
        print("Tunnel status unavailable: " + str(exc))
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["configure", "start", "doctor", "status"])
    parser.add_argument("--tunnel-id")
    parser.add_argument("--replace-key", action="store_true")
    args = parser.parse_args()
    if args.action == "status":
        status()
        return
    if args.action == "configure":
        configure(args.tunnel_id, args.replace_key)
        return
    if not CLIENT.exists():
        raise SystemExit("Run install_tunnel.bat first.")
    if not CONFIG.exists():
        raise SystemExit("Run configure_tunnel.bat first.")
    env = environment()
    if not env.get("CONTROL_PLANE_API_KEY"):
        raise SystemExit("Runtime API key is missing. Run configure_tunnel.bat.")
    if args.action == "doctor":
        command = [str(CLIENT), "doctor", "--config", str(CONFIG), "--explain"]
    else:
        command = [str(CLIENT), "run", "--config", str(CONFIG)]
        print("Starting tunnel. Keep this window open; Ctrl+C stops it.", flush=True)
        print("Local health alone does not prove the OpenAI connection; check successful polling.", flush=True)
    try:
        raise SystemExit(subprocess.call(command, cwd=ROOT, env=env))
    except KeyboardInterrupt:
        print("Tunnel stopped.")


if __name__ == "__main__":
    main()
