# French A1 Anki deck

Flashcards for the NLF Academy "Road to A1" course, built from `data/chNN.yaml` and published as `french-a1.apkg` on every push.

**Each new chapter:** send Claude the video link and chapter number. Claude watches the slides, writes the cards into `data/`, and pushes. The GitHub Action then builds a new Release.

**Each laptop:** open Anki and double-click `client/update-deck.bat`. It imports the new cards, keeping your review history, and syncs to AnkiWeb. Review on your phone at ankiweb.net.

| Path | Purpose |
| --- | --- |
| `data/chNN.yaml` | The cards (source of truth). Edit text freely; never change an `id`. |
| `config.yaml` | Deck name, TTS voice, listening cards on/off |
| `scripts/add_cards.py` | Merges a JSON batch into a chapter: dedupes, assigns permanent IDs |
| `scripts/build.py` | Validates, generates audio, writes `dist/french-a1.apkg` (`--check`, `--no-audio`) |
| `client/` | One-click updater for both laptops (stdlib Python, uses AnkiConnect) |
