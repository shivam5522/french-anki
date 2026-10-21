"""Pull the latest French deck into Anki and sync. Standard library only, no pip install needed.

Best with Anki desktop OPEN and the AnkiConnect add-on (code 2055492159): fully automatic import + sync.
Without AnkiConnect it falls back to opening Anki's import dialog for you.

  python update_anki.py                      # latest GitHub release of REPO below
  python update_anki.py --file french-a1.apkg  # import a local file instead
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = "shivam5522/french-anki"
ASSET = "french-a1.apkg"
ANKI = "http://127.0.0.1:8765"


def anki(action: str, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(ANKI, body), timeout=300) as r:
            res = json.load(r)
    except urllib.error.URLError as e:
        raise ConnectionError("Anki is closed or AnkiConnect isn't installed") from e
    if res.get("error"):
        raise RuntimeError(f"AnkiConnect {action}: {res['error']}")
    return res.get("result")


def download(repo: str) -> Path:
    url = f"https://github.com/{repo}/releases/latest/download/{ASSET}"
    dest = Path(tempfile.gettempdir()) / ASSET
    print(f"Downloading {url}")
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.HTTPError as e:
        sys.exit(f"Download failed ({e.code}). Is the repo public and has a release been built?")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--file", type=Path)
    a = ap.parse_args()

    pkg = a.file.resolve() if a.file else download(a.repo)
    try:
        print(f"AnkiConnect version {anki('version')}")
        before = len(anki("findNotes", query="note:FrenchA1*"))
        anki("importPackage", path=str(pkg))
        after = len(anki("findNotes", query="note:FrenchA1*"))
    except (RuntimeError, ConnectionError) as e:
        # No AnkiConnect, or its importer failed: hand the file to Anki's own import dialog instead.
        print(f"Automatic import unavailable ({e}). Opening Anki's import dialog; click Import, then Sync.")
        os.startfile(pkg)  # Windows: same as double-clicking the .apkg
        return
    print(f"Imported. French notes: {before} -> {after} (+{after - before} new; existing ones updated in place).")
    try:
        anki("sync")
        print("Synced to AnkiWeb. Open ankiweb.net on your phone to review.")
    except RuntimeError as e:
        print(f"Imported, but sync failed ({e}). Click Sync in Anki.")


if __name__ == "__main__":
    main()
