# Agent guide — deck-eval-gen

`deck-eval-gen` produces printable on-deck evaluation PDF forms from a published officials
grid Google Sheet (currently Swim Ontario). It's the upstream of
[`deck-eval-parser`](https://github.com/swimblocks/deck-eval-parser) — the PDFs this tool
emits should round-trip cleanly through the parser's fillable-PDF fast path.

## Canonical rules

The cross-repo rules for any SwimBlocks project live in the [`swimblocks/.github`](https://github.com/swimblocks/.github)
standards repo. Read these first:

- [AGENTS.md](https://github.com/swimblocks/.github/blob/main/AGENTS.md) — distilled agent guide
- [CONTRIBUTING.md](https://github.com/swimblocks/.github/blob/main/CONTRIBUTING.md) —
  long-form house rules
- [development.md](https://github.com/swimblocks/.github/blob/main/docs/development.md) —
  setting up a new machine

Everything below is **repo-specific** — quirks that the canonical guide doesn't cover.

## Repo-specific quirks

- **Input is a Google Sheet, not a local CSV.** The tool fetches the published sheet at
  runtime via the CSV-export URL. A local `officials.csv` is for offline development only
  and is gitignored — **never commit real officials' names/emails**. There's no synthetic
  fixture in-repo; tests use inline data.
- **Output PDFs feed `deck-eval-parser`.** The `eval_form.pdf` template is the same form
  the parser fast-path expects to read back. **Don't change widget names or page layout**
  without a coordinated change in `deck-eval-parser`'s Swim Ontario template
  (`src/templates/swim_ontario_v1.py` over there). Keeping them in lockstep is what makes
  the form-field round-trip free.
- **9 officials per page** is baked into the form template and the `_choose_fontsize`
  paginator. If the blank form ever changes, update both ends and the paginator.
- **Annotation parsing is hand-tuned.** `_parse_name_and_club` knows that
  `Jane Doe (BBST) (DE)` means name=Jane Doe, club=BBST, deck-eval=yes; and ignores
  `DE`, `Shadow`, `RCR`, country codes, `Lane N`, `#REF!`. New annotations a meet introduces
  go in there.
- **Only PyMuPDF + requests** (plus pytest/ruff for dev). Keep the dependency surface narrow;
  PDF form filling needs PyMuPDF's appearance-stream generation.
- **No Google ADC or gcloud** — the sheet must be **published to the web**, not just shared.
  This is a deliberate scope choice: the tool runs against a public artefact, not a
  permissioned one.

## Where to start reading

- [`README.md`](README.md) — user-facing CLI overview
- [`eval_gen.py`](eval_gen.py) — single-file Python module; all the logic lives here
- [`eval_form.pdf`](eval_form.pdf) — blank Swim Ontario template (source of truth for field
  positions and widget names)
- [`tests/test_eval_gen.py`](tests/test_eval_gen.py) — unit tests, inline data
