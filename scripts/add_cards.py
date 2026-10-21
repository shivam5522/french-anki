"""Merge a batch of new cards (JSON) into data/chNN.yaml.

  python scripts/add_cards.py 4 new_cards.json --title "Les jours et les mois" --video https://youtu.be/XXXX

JSON shape:
  {"vocab":        [{"fr": "la boulangerie", "en": "the bakery", "gender": "f", "example_fr": "", "example_en": ""}],
   "phrases":      [{"fr": "Comment ça va ?", "en": "How are you?"}],
   "conjugations": [{"verb": "avoir", "en": "to have", "tense": "présent",
                     "forms": {"je": "j'ai", "tu": "tu as", "il/elle/on": "il/elle/on a",
                               "nous": "nous avons", "vous": "vous avez", "ils/elles": "ils/elles ont"}}]}

Anything already in an earlier chapter is skipped. New items get permanent IDs
(c04-v001, c04-p001, c04-c001). Never renumber or reuse an ID: it is what ties a
card to its review history.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import PERSONS, ROOT, all_chapters, load_chapter, norm, save_chapter


def merge(ch: int, raw: dict, title: str | None, video: str | None) -> None:
    existing = [d for d in all_chapters()]
    seen_fr = {norm(x["fr"]) for d in existing for k in ("vocab", "phrases") for x in d[k]}
    seen_conj = {(norm(x["verb"]), norm(x["tense"])) for d in existing for x in d["conjugations"]}

    chap = load_chapter(ch)
    if title:
        chap["title"] = title
    if video:
        vids = chap.setdefault("videos", [])
        if video not in vids:
            vids.append(video)
    # keep a tidy key order
    chap = {k: chap[k] for k in ("chapter", "title", "videos", "vocab", "phrases", "conjugations") if k in chap}

    def next_id(kind: str, items: list) -> str:
        prefix = f"c{ch:02d}-{kind}"
        nums = [int(x["id"][len(prefix):]) for x in items if x.get("id", "").startswith(prefix)]
        return f"{prefix}{(max(nums) + 1) if nums else 1:03d}"

    added = {"vocab": 0, "phrases": 0, "conjugations": 0}
    dupes: list[str] = []
    for kind, key in (("vocab", "v"), ("phrases", "p")):
        for it in raw.get(kind) or []:
            fr, en = (it.get("fr") or "").strip(), (it.get("en") or "").strip()
            if not fr or not en:
                continue
            if norm(fr) in seen_fr:
                dupes.append(fr)
                continue
            seen_fr.add(norm(fr))
            row = {"id": next_id(key, chap[kind]), "fr": fr, "en": en}
            if kind == "vocab":
                row["gender"] = it.get("gender") or ""
                row["example_fr"] = it.get("example_fr") or ""
                row["example_en"] = it.get("example_en") or ""
            chap[kind].append(row)
            added[kind] += 1
    for it in raw.get("conjugations") or []:
        verb, tense = (it.get("verb") or "").strip(), (it.get("tense") or "présent").strip()
        forms = it.get("forms") or {}
        if not verb or not forms:
            continue
        if (norm(verb), norm(tense)) in seen_conj:
            dupes.append(f"{verb} ({tense})")
            continue
        seen_conj.add((norm(verb), norm(tense)))
        missing = [p for p in PERSONS if p not in forms]
        if missing:
            print(f"  ! {verb} ({tense}) is missing {missing}")
        chap["conjugations"].append({
            "id": next_id("c", chap["conjugations"]), "verb": verb, "en": (it.get("en") or "").strip(),
            "tense": tense, "forms": {p: forms[p] for p in PERSONS if p in forms},
        })
        added["conjugations"] += 1

    p = save_chapter(chap)
    print(f"{p.relative_to(ROOT)}: +{added['vocab']} vocab, +{added['phrases']} phrases, "
          f"+{added['conjugations']} conjugations")
    if dupes:
        print(f"  skipped {len(dupes)} already in the deck: " + ", ".join(dupes))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter", type=int)
    ap.add_argument("json_file", type=Path)
    ap.add_argument("--title")
    ap.add_argument("--video")
    a = ap.parse_args()
    raw = json.loads(a.json_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        sys.exit("Expected a JSON object with vocab / phrases / conjugations")
    merge(a.chapter, raw, a.title, a.video)


if __name__ == "__main__":
    main()
