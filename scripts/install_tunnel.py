"""Install the official Windows tunnel client inside this project only."""
from __future__ import annotations

import hashlib
import io
import json
import platform
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_API = "https://api.github.com/repos/openai/tunnel-client/releases/latest"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Project-Brain-MCP-installer"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def main() -> None:
    if platform.system() != "Windows":
        raise SystemExit("This installer is for Windows. Use the official release for your OS.")
    arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "amd64"
    release = json.loads(download(RELEASE_API))
    name = f"tunnel-client-{release['tag_name']}-windows-{arch}.zip"
    asset = next(a for a in release["assets"] if a["name"] == name)
    checksum_asset = next(a for a in release["assets"] if a["name"] == "SHA256SUMS.txt")
    checksum_text = download(checksum_asset["browser_download_url"]).decode("utf-8")
    expected = next(line.split()[0] for line in checksum_text.splitlines()
                    if line.split()[-1].lstrip("*") == name)
    payload = download(asset["browser_download_url"])
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise SystemExit("Official archive checksum mismatch; nothing installed.")
    destination = ROOT / ".runtime" / "tunnel"
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        matches = [p for p in archive.namelist() if p.replace("\\", "/").split("/")[-1] == "tunnel-client.exe"]
        if len(matches) != 1:
            raise SystemExit("Expected exactly one tunnel-client.exe in official archive")
        executable = archive.read(matches[0])
    target = destination / "tunnel-client.exe"
    target.write_bytes(executable)
    receipt = {
        "release": release["tag_name"], "source": asset["browser_download_url"],
        "archive_sha256": actual, "exe_sha256": hashlib.sha256(executable).hexdigest(),
    }
    (destination / "install.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"Installed official tunnel-client {release['tag_name']} at {target}")
    print(f"Archive SHA256: {actual}")


if __name__ == "__main__":
    main()
