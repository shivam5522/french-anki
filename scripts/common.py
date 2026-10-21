"""Shared helpers: paths, config, YAML I/O, normalisation."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
AUDIO = ROOT / "audio"
DIST = ROOT / "dist"

PERSONS = ["je", "tu", "il/elle/on", "nous", "vous", "ils/elles"]


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def chapter_path(ch: int) -> Path:
    return DATA / f"ch{ch:02d}.yaml"


def load_chapter(ch: int) -> dict:
    p = chapter_path(ch)
    if not p.exists():
        return {"chapter": ch, "title": f"Chapter {ch}", "vocab": [], "phrases": [], "conjugations": []}
    with open(p, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    for k in ("vocab", "phrases", "conjugations"):
        d.setdefault(k, [])
    return d


def all_chapters() -> list[dict]:
    out = []
    for p in sorted(DATA.glob("ch*.yaml")):
        with open(p, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        for k in ("vocab", "phrases", "conjugations"):
            d[k] = d.get(k) or []
        out.append(d)
    return out


class _Dumper(yaml.SafeDumper):
    pass


def _str_rep(dumper, data):
    # keep long sentences readable; quote only when YAML needs it
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_rep)


def save_chapter(d: dict) -> Path:
    DATA.mkdir(exist_ok=True)
    p = chapter_path(int(d["chapter"]))
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(d, f, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=120)
    return p


def norm(text: str) -> str:
    """Normalise French text for duplicate detection (keeps accents)."""
    t = unicodedata.normalize("NFC", text or "").lower().strip()
    t = t.replace("’", "'").replace(" ", " ")
    t = re.sub(r"\s*\?", " ?", t)          # "ça va?" == "ça va ?", but "ça va ?" != "ça va."
    t = re.sub(r"[.!…]+$", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()
