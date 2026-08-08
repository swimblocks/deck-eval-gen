# Agent guide — deck-eval-gen

`deck-eval-gen` produces printable on-deck evaluation PDF forms from a swim meet's
officials grid (currently Swim Ontario). It's the upstream of
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

## The grid is the contract

Input is a **grid**, documented and versioned in
[`docs/grid-schema.md`](docs/grid-schema.md). Every input path produces that one model and
the PDF writer consumes only it, which is what makes a form generated from JSON identical
to one generated from the equivalent Sheet.

[`officials-admin`](https://github.com/swimblocks/officials-admin) serves this shape from
`/meets/{id}/grid.json` and consumes this package as a library. **A change to the schema is
a change to a published interface** — read the versioning rules in that doc before touching
it, and don't bump the version for an additive field.

Reading a published Google Sheet is one adapter (`sheet.py`), and the only path that needs
the network. Keep Sheets-specific knowledge — column indices, `(DE)` and `(CLUB)`
annotations, free-text session headers — inside it.

## Repo-specific quirks

- **Installable package, `src/` layout.** `pip install -r requirements-dev.txt` installs it
  editable; without that, `import deck_eval_gen` fails and every test errors. Runtime deps
  live in `pyproject.toml`, not `requirements.txt`. Root `eval_gen.py` is a compatibility
  shim, kept because the docs and muscle memory both say `python eval_gen.py <url>`.
- **Output PDFs feed `deck-eval-parser`.** `src/deck_eval_gen/eval_form.pdf` is the same
  form the parser fast-path expects to read back. **Don't change widget names or page
  layout** without a coordinated change in `deck-eval-parser`'s Swim Ontario template
  (`src/templates/swim_ontario_v1.py` over there). Keeping them in lockstep is what makes
  the form-field round-trip free. `docs/grid-schema.md` carries the field mapping between
  the two repos.
- **Merging pages renames repeated form fields.** PyMuPDF disambiguates duplicate field
  names when it merges template copies, so page 2's first name field is
  `Name of OfficialRow1 [226]`. The values are right and the form prints correctly, but
  anything reading fields *by name* only sees page 1's. `read_field_values` strips the
  suffix; nothing else depends on it yet.
- **9 officials per page** is baked into the form template and `pdf.ROWS_PER_PAGE`. If the
  blank form ever changes, update both ends.
- **Annotation parsing is hand-tuned.** `parse_name_and_club` knows that
  `Jane Doe (BBST) (DE)` means name=Jane Doe, club=BBST, deck-eval=yes; and ignores
  `DE`, `Shadow`, `RCR`, country codes, `Lane N`, `#REF!`. New annotations a meet introduces
  go in there.
- **Session numbers come from the header, not column order.** A grid carries note columns
  beside the sessions, and it may publish a subset (`Session 4`, `Session 7`). Counting
  columns misnumbers the output files.
- **Only PyMuPDF + requests** (plus pytest/ruff for dev). Keep the dependency surface
  narrow; PDF form filling needs PyMuPDF's appearance-stream generation.
- **No Google ADC or gcloud.** For the Sheet path the sheet must be **published to the
  web**, not just shared. This is a deliberate scope choice: the tool runs against a public
  artefact, not a permissioned one. Nothing else needs credentials at all.
- **Tests never touch the network.** `tests/fixtures/` holds a synthetic Sheet export and
  the equivalent grid. `*.csv` is gitignored to keep real officials out of git —
  `tests/fixtures/*.csv` is the one carve-out, and it stays synthetic.

## Where to start reading

- [`README.md`](README.md) — user-facing CLI and library overview
- [`docs/grid-schema.md`](docs/grid-schema.md) — the input contract
- [`src/deck_eval_gen/grid.py`](src/deck_eval_gen/grid.py) — the model and both codecs
- [`src/deck_eval_gen/sheet.py`](src/deck_eval_gen/sheet.py) — the published-Sheet adapter
- [`src/deck_eval_gen/pdf.py`](src/deck_eval_gen/pdf.py) — form filling
- [`src/deck_eval_gen/eval_form.pdf`](src/deck_eval_gen/eval_form.pdf) — blank Swim Ontario
  template (source of truth for field positions and widget names)
- [`tests/test_pdf.py`](tests/test_pdf.py) — including the JSON-vs-Sheet equivalence test
