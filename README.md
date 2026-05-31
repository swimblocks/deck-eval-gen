# deck-eval-gen

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Generates printable on-deck evaluation PDF forms from a published officials grid (currently
Swim Ontario). For Canadian swimming officials — part of the [SwimBlocks](https://github.com/swimblocks)
constellation. See [`AGENTS.md`](AGENTS.md) for the agent / contributor guide.

## What it does

Reads the officials grid, finds every official marked `(DE)` (Deck Evaluation Requested), and
produces one filled PDF per session. Each PDF uses the blank `eval_form.pdf` template and
populates:

- Competition name, coordinator, date/session, host club, COC
- Official name, club, position, lane number
- Session referee as the mentor official
- Correct "Page X of Y" pagination (9 officials per page)

Officials whose club is not noted in the grid (no `(CLUB)` annotation after their name) are
assumed to be from the host club.

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

## Usage

```bash
python eval_gen.py <sheet_url> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `url` | Published Google Sheet URL (tinyurl or direct). Must be published via *File > Share > Publish to web*. |
| `--session N` / `-s N` | Generate only session N (1-based). Default: all sessions with DE officials. |
| `--output-dir DIR` / `-o DIR` | Where to write PDFs. Default: current directory. |
| `--template PATH` / `-t PATH` | Blank eval form PDF. Default: `eval_form.pdf` next to the script. |
| `--host-club NAME` | Host club name. Used for officials with no club annotation in the grid. |
| `--coc NAME` | Chief of Officials Committee contact for the COC field. |

### Examples

Generate all sessions:

```bash
python eval_gen.py https://tinyurl.com/row-cc-2026-officials \
  --host-club "Centennial" \
  --coc "Jane Smith" \
  --output-dir output
```

Generate only session 3:

```bash
python eval_gen.py https://tinyurl.com/row-cc-2026-officials \
  --session 3 \
  --host-club "Centennial" \
  --output-dir output
```

## Output

Files are named `session_1_evals.pdf`, `session_2_evals.pdf`, etc., written to `--output-dir`.

## Sheet format

The tool expects a Google Sheet with this column layout:

| (blank) | Position | Sub-position | Session 1 | Session 2 | … |
|---|---|---|---|---|---|

Officials requesting deck evaluations are annotated `(DE)` in their cell. Club codes can be
embedded in the name, e.g. `Jane Doe (BBST) (DE)`. Known non-club annotations that are
ignored: `DE`, `Shadow`, `RCR`, country codes (`AUS`, `CAN`, `USA`, `GBR`, `NZL`, …),
`Lane N`, `#REF!`.

## Local CSVs and PII

The tool fetches the grid live from a published Google Sheet URL — there's no need to keep
a local CSV. If you do save one for offline development, it stays local: `*.csv` is
gitignored to prevent real officials' data from ever landing in git history.

## Running tests

```bash
ruff check .
pytest -q
```

## Documentation

- [`AGENTS.md`](AGENTS.md) — repo-specific agent / contributor guide (points at the org-wide
  rules in [`swimblocks/.github`](https://github.com/swimblocks/.github))

## License

[MIT](LICENSE) © 2026 Gavin Bee.
