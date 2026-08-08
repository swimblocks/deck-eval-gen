# deck-eval-gen

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Generates printable on-deck evaluation PDF forms from a swim meet's officials
grid (currently Swim Ontario). For Canadian swimming officials — part of the
[SwimBlocks](https://github.com/swimblocks) constellation. See
[`AGENTS.md`](AGENTS.md) for the agent / contributor guide.

## What it does

Reads the officials grid, finds every assignment flagged for a deck evaluation,
and produces one filled PDF per session. Each uses the blank `eval_form.pdf`
template and populates:

- Competition name, coordinator, date/session, host club, COC
- Official name, club, position, lane number
- Correct "Page X of Y" pagination (9 officials per page)

Officials whose club the grid does not note are taken to be from the host club.

Times worked, mentor, level and sign-off are left blank — those get filled in
on deck.

## Setup

```bash
python -m venv .venv

# Windows (Command Prompt)
.venv\Scripts\activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
```

That installs the package in editable mode, so the `deck-eval-gen` command and
the `deck_eval_gen` import are both available.

## Usage

Three ways in. All of them produce the same
[grid](docs/grid-schema.md) internally, so they produce the same PDFs.

```bash
deck-eval-gen <sheet_url>              # published Google Sheet
deck-eval-gen --grid-json grid.json    # a grid
deck-eval-gen --grid-csv grid.csv      # a grid as flat CSV
```

`python eval_gen.py …` still works and takes the same arguments.

### Arguments

| Argument | Description |
|---|---|
| `url` | Published Google Sheet URL (shortener or direct). Must be published via *File > Share > Publish to web* — sharing is not enough. |
| `--grid-json PATH` | The grid as JSON. `-` reads stdin. |
| `--grid-csv PATH` | The grid as flat CSV. `-` reads stdin. Also accepts a published-sheet CSV export saved to a file. |
| `--session N` / `-s N` | Generate only session N. Default: every session with flagged officials. |
| `--output-dir DIR` / `-o DIR` | Where to write PDFs. Default: current directory. |
| `--template PATH` / `-t PATH` | Blank eval form PDF. Default: the one shipped with the package. |
| `--host-club NAME` | Host club. Used for officials whose club the grid does not note. Overrides the grid. |
| `--coc NAME` | Chief of Officials Committee contact for the COC field. Overrides the grid. |
| `--no-prompt` | Never ask about truncated names; print them as the grid has them. |

Exactly one input is required. Giving two is an error rather than a silent
preference.

### Examples

```bash
# Every session, from the published grid
deck-eval-gen https://tinyurl.com/example-officials-grid \
  --host-club "Centennial" \
  --coc "Jamie Sample" \
  --output-dir output

# One session, from a grid
deck-eval-gen --grid-json grid.json --session 3 --output-dir output

# Straight from an API
curl -s https://officials.example/meets/42/grid.json \
  | deck-eval-gen --grid-json - -o output
```

Files are named `session_1_evals.pdf`, `session_2_evals.pdf`, … after the
session's own number, which is the one on the grid.

## As a library

The grid is the contract, so a caller that already holds the grid
never touches a Sheet, the network, or a Google account:

```python
from deck_eval_gen import default_template, fill_session_pdf, grid_from_dict

grid = grid_from_dict(payload).with_defaults(host_club="Centennial")
for session in grid.deck_eval_sessions:
    fill_session_pdf(
        default_template(),
        out_dir / f"session_{session.number}_evals.pdf",
        grid,
        session,
    )
```

## Input formats

- **[`docs/grid-schema.md`](docs/grid-schema.md)** — the grid, in JSON
  and CSV. Versioned; read this before changing it.
- **Published Sheet** — the legacy path, and the reason this tool exists. The
  grid layout is:

  | (blank) | Position | Sub-position | Session 1 | Session 2 | … |
  |---|---|---|---|---|---|

  Officials requesting deck evaluations are annotated `(DE)` in their cell. Club
  codes are embedded in the name, e.g. `Jane Doe (BBST) (DE)`. Non-club
  annotations that are ignored: `DE`, `Shadow`, `RCR`, country codes (`AUS`,
  `CAN`, `USA`, …), `Lane N`, `#REF!`. Session columns are recognised by a
  `Session N` header, so note columns alongside them are not mistaken for
  sessions. One cell may hold several officials, one per line.

## Local CSVs and PII

The Sheet path fetches the grid live, so there is no need to keep a local copy.
If you save one for offline work it stays local: `*.csv` is gitignored to keep
real officials' data out of git history. The one exception is
`tests/fixtures/*.csv`, which is synthetic by rule.

## Running tests

```bash
ruff check .
pytest -q
```

No Google credentials, no network, no `gcloud`.

## Documentation

- [`docs/grid-schema.md`](docs/grid-schema.md) — the input contract
- [`AGENTS.md`](AGENTS.md) — repo-specific agent / contributor guide (points at
  the org-wide rules in [`swimblocks/.github`](https://github.com/swimblocks/.github))

## License

[MIT](LICENSE) © 2026 Gavin Bee.
