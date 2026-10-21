"""Validate data/*.yaml, generate French audio, and write dist/french-a1.apkg.

  python scripts/build.py              # full build with audio
  python scripts/build.py --no-audio   # fast build, no TTS
  python scripts/build.py --check      # validate only

Why updates never reset progress: every note's GUID is derived from its permanent
`id` in the YAML (not from its text), and the note types and decks have fixed IDs.
Re-importing the .apkg updates existing notes in place and keeps their review history.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import sys

import genanki

from common import AUDIO, DIST, PERSONS, ROOT, all_chapters, load_config, norm

# Fixed forever. Never change these, or Anki will treat everything as new.
MODEL_WORD_ID = 1729340001
MODEL_CONJ_ID = 1729340002
MODEL_TABLE_ID = 1729340003

CSS = """
.card { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; font-size: 22px; text-align: center;
        color: #1d1d1f; background: #fafafa; line-height: 1.4; padding: 12px; }
.nightMode .card, .card.nightMode { color: #f2f2f2; background: #1e1e1e; }
.fr { font-size: 30px; font-weight: 600; }
.en { font-size: 24px; }
.hint, .meta { font-size: 15px; opacity: .65; }
.ex { font-size: 18px; margin-top: 14px; }
.g-m { color: #2f6fdb; } .g-f { color: #d0457a; }
table.conj { margin: 10px auto; border-collapse: collapse; font-size: 20px; }
table.conj td { padding: 4px 14px; text-align: left; border-bottom: 1px solid rgba(127,127,127,.25); }
hr#answer { margin: 14px 0; }
"""

WORD_FIELDS = ["Id", "French", "English", "Gender", "ExampleFR", "ExampleEN", "Audio", "ExampleAudio",
               "Chapter", "Listen"]
word_model = genanki.Model(
    MODEL_WORD_ID, "FrenchA1 Word/Phrase",
    fields=[{"name": f} for f in WORD_FIELDS],
    templates=[
        {"name": "FR -> EN",
         "qfmt": '<div class="fr g-{{Gender}}">{{French}}</div>{{Audio}}<div class="meta">{{Chapter}}</div>',
         "afmt": '{{FrontSide}}<hr id="answer"><div class="en">{{English}}</div>'
                 '{{#ExampleFR}}<div class="ex">{{ExampleFR}} {{ExampleAudio}}<br><span class="hint">{{ExampleEN}}</span></div>{{/ExampleFR}}'},
        {"name": "EN -> FR",
         "qfmt": '<div class="en">{{English}}</div><div class="hint">en français ?</div><div class="meta">{{Chapter}}</div>',
         "afmt": '{{FrontSide}}<hr id="answer"><div class="fr g-{{Gender}}">{{French}}</div>{{Audio}}'
                 '{{#ExampleFR}}<div class="ex">{{ExampleFR}}<br><span class="hint">{{ExampleEN}}</span></div>{{/ExampleFR}}'},
        {"name": "Listen",
         # Only generated when the Listen field is non-empty (controlled by listening_cards in config.yaml)
         "qfmt": '{{#Listen}}<div class="hint">Listen. What does it mean?</div>{{Audio}}{{/Listen}}',
         "afmt": '{{FrontSide}}<hr id="answer"><div class="fr g-{{Gender}}">{{French}}</div><div class="en">{{English}}</div>'},
    ],
    css=CSS, sort_field_index=1,
)

CONJ_FIELDS = ["Id", "Verb", "VerbEN", "Tense", "Person", "Answer", "Audio", "Chapter"]
conj_model = genanki.Model(
    MODEL_CONJ_ID, "FrenchA1 Conjugation",
    fields=[{"name": f} for f in CONJ_FIELDS],
    templates=[{
        "name": "Person -> form",
        "qfmt": '<div class="hint">{{Verb}} <i>({{VerbEN}})</i> · {{Tense}}</div><div class="fr">{{Person}} …</div>'
                '<div class="meta">{{Chapter}}</div>',
        "afmt": '{{FrontSide}}<hr id="answer"><div class="fr">{{Answer}}</div>{{Audio}}',
    }],
    css=CSS, sort_field_index=1,
)

TABLE_FIELDS = ["Id", "Verb", "VerbEN", "Tense", "Table", "Audio", "Chapter"]
table_model = genanki.Model(
    MODEL_TABLE_ID, "FrenchA1 Verb Table",
    fields=[{"name": f} for f in TABLE_FIELDS],
    templates=[{
        "name": "Conjugate all",
        "qfmt": '<div class="hint">Conjugate out loud</div><div class="fr">{{Verb}}</div>'
                '<div class="en">{{VerbEN}} · {{Tense}}</div><div class="meta">{{Chapter}}</div>',
        "afmt": '{{FrontSide}}<hr id="answer">{{Table}}{{Audio}}',
    }],
    css=CSS, sort_field_index=1,
)


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def deck_id(name: str) -> int:
    return int(hashlib.sha1(name.encode()).hexdigest()[:8], 16) | (1 << 30)


def audio_name(text: str, voice: str) -> str:
    return "fa_" + hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16] + ".mp3"


def speakable(text: str) -> str:
    # "il/elle/on a" -> "il a"; "grand / grande" -> "grand, grande"; drop "(f)" style notes
    import re
    t = re.sub(r"\([^)]*\)", "", text)
    t = re.sub(r"\b(il|ils)/elles?(/on)?\b", r"\1", t)
    t = t.replace(" / ", ", ")
    return " ".join(t.split())


# ---------- validation ----------

def validate(chapters: list[dict]) -> list[str]:
    errors, warnings = [], []
    ids, frs = {}, {}
    for d in chapters:
        ch = d.get("chapter")
        if not isinstance(ch, int):
            errors.append(f"{d.get('title')}: missing integer `chapter`")
        for kind in ("vocab", "phrases", "conjugations"):
            for it in d[kind]:
                i = it.get("id")
                if not i:
                    errors.append(f"ch{ch} {kind}: item without id: {it}")
                    continue
                if i in ids:
                    errors.append(f"duplicate id {i} (ch{ids[i]} and ch{ch})")
                ids[i] = ch
                if kind == "conjugations":
                    if not it.get("verb") or not it.get("forms"):
                        errors.append(f"{i}: needs verb and forms")
                    miss = [p for p in PERSONS if p not in (it.get("forms") or {})]
                    if miss:
                        warnings.append(f"{i} {it.get('verb')}: missing {miss}")
                else:
                    if not it.get("fr") or not it.get("en"):
                        errors.append(f"{i}: needs fr and en")
                        continue
                    n = norm(it["fr"])
                    if n in frs:
                        warnings.append(f"{i} duplicates {frs[n]}: {it['fr']!r}")
                    frs[n] = i
                    if kind == "vocab" and it.get("gender") not in ("", "m", "f", None):
                        errors.append(f"{i}: gender must be m, f or empty")
    for w in warnings:
        print(f"  warning: {w}")
    return errors


# ---------- audio ----------

async def _tts_all(jobs: dict[str, str], voice: str) -> None:
    import edge_tts

    sem = asyncio.Semaphore(6)

    async def one(fname: str, text: str):
        dest = AUDIO / fname
        async with sem:
            for attempt in range(3):
                try:
                    await edge_tts.Communicate(text, voice, rate="-10%").save(str(dest))
                    if dest.stat().st_size > 0:
                        return
                except Exception as e:  # noqa: BLE001
                    err = e
                dest.unlink(missing_ok=True)
                await asyncio.sleep(2)
            # Fallback: Google Translate TTS (pip install gTTS)
            try:
                from gtts import gTTS
                await asyncio.to_thread(lambda: gTTS(text, lang="fr").save(str(dest)))
                return
            except Exception as e:  # noqa: BLE001
                dest.unlink(missing_ok=True)
                print(f"  ! TTS failed for {text!r}: {err if 'err' in locals() else e}")

    await asyncio.gather(*(one(f, t) for f, t in jobs.items()))


def _have(fname: str) -> bool:
    p = AUDIO / fname
    return p.exists() and p.stat().st_size > 0


def ensure_audio(texts: set[str], voice: str) -> None:
    AUDIO.mkdir(exist_ok=True)
    jobs = {audio_name(t, voice): speakable(t) for t in texts}
    jobs = {f: t for f, t in jobs.items() if not _have(f)}
    if jobs:
        print(f"Generating {len(jobs)} audio clips with {voice} ...")
        asyncio.run(_tts_all(jobs, voice))


# ---------- build ----------

def build(with_audio: bool) -> None:
    cfg = load_config()
    voice = cfg.get("voice", "fr-FR-DeniseNeural")
    listen = "1" if cfg.get("listening_cards", True) else ""
    root_name = cfg.get("deck_name", "French A1")
    chapters = all_chapters()
    if not chapters:
        sys.exit("No data/ch*.yaml files yet.")

    errors = validate(chapters)
    if errors:
        print("Validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    texts: set[str] = set()
    for d in chapters:
        for kind in ("vocab", "phrases"):
            for it in d[kind]:
                texts.add(it["fr"])
                if it.get("example_fr"):
                    texts.add(it["example_fr"])
        for it in d["conjugations"]:
            texts.update(it["forms"].values())
            texts.add(", ".join(it["forms"].values()))
    if with_audio:
        ensure_audio(texts, voice)

    media: list[str] = []

    def snd(text: str) -> str:
        if not with_audio or not text:
            return ""
        f = audio_name(text, voice)
        if not _have(f):
            return ""
        media.append(str(AUDIO / f))
        return f"[sound:{f}]"

    decks, counts = [], {"notes": 0, "cards": 0}
    for d in sorted(chapters, key=lambda x: x["chapter"]):
        ch = d["chapter"]
        name = f"{root_name}::Ch {ch:02d} - {d.get('title') or ''}".rstrip(" -")
        deck = genanki.Deck(deck_id(f"{root_name}::Ch {ch:02d}"), name)
        label = f"Ch {ch:02d}"
        for kind in ("vocab", "phrases"):
            for it in d[kind]:
                e = esc
                note = genanki.Note(
                    model=word_model, guid=genanki.guid_for("frenchA1", it["id"]),
                    tags=[f"ch::{ch:02d}", f"type::{kind}"],
                    fields=[it["id"], e(it["fr"]), e(it["en"]), it.get("gender") or "",
                            e(it.get("example_fr") or ""), e(it.get("example_en") or ""),
                            snd(it["fr"]), snd(it.get("example_fr") or ""), label, listen])
                deck.add_note(note)
                counts["notes"] += 1
                counts["cards"] += 2 + (1 if listen and _have(audio_name(it["fr"], voice)) and with_audio else 0)
        for it in d["conjugations"]:
            forms = it["forms"]
            for p in PERSONS:
                if p not in forms:
                    continue
                deck.add_note(genanki.Note(
                    model=conj_model, guid=genanki.guid_for("frenchA1", it["id"], p),
                    tags=[f"ch::{ch:02d}", "type::conjugation", f"verb::{it['verb']}"],
                    fields=[f"{it['id']}-{p}", it["verb"], esc(it.get("en") or ""), it["tense"], p,
                            esc(forms[p]), snd(forms[p]), label]))
                counts["notes"] += 1
                counts["cards"] += 1
            rows = "".join(f"<tr><td>{esc(forms[p])}</td></tr>" for p in PERSONS if p in forms)
            deck.add_note(genanki.Note(
                model=table_model, guid=genanki.guid_for("frenchA1", it["id"], "table"),
                tags=[f"ch::{ch:02d}", "type::verbtable", f"verb::{it['verb']}"],
                fields=[it["id"], it["verb"], esc(it.get("en") or ""), it["tense"],
                        f'<table class="conj">{rows}</table>', snd(", ".join(forms.values())), label]))
            counts["notes"] += 1
            counts["cards"] += 1
        decks.append(deck)

    DIST.mkdir(exist_ok=True)
    out = DIST / "french-a1.apkg"
    pkg = genanki.Package(decks)
    pkg.media_files = sorted(set(media))
    pkg.write_to_file(str(out))
    print(f"Built {out.relative_to(ROOT)}: {len(decks)} chapters, {counts['notes']} notes, "
          f"~{counts['cards']} cards, {len(pkg.media_files)} audio files.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        errs = validate(all_chapters())
        print("OK" if not errs else "\n".join(errs))
        sys.exit(1 if errs else 0)
    build(with_audio=not a.no_audio)


if __name__ == "__main__":
    main()
