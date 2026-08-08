# The grid — `deck-eval-gen`'s input contract

**Schema version: 1.**

A *grid* is one meet's officials: the competition, its
sessions, who is assigned to which position in each, and which of those
assignments have been flagged for a deck evaluation. It is what this tool reads.

Reading a published Google Sheet is one adapter that produces this shape, not
the shape itself. Everything downstream — validation, pagination, the filled
PDF — sees only the grid, so a form generated from JSON and one generated
from the equivalent Sheet are identical by construction.

[`officials-admin`](https://github.com/swimblocks/officials-admin) serves this
shape from `/meets/{id}/grid.json`. **Treat a change here as a change to a
published interface**, not an internal refactor.

## Versioning

`schema_version` is required, and a grid declaring a version this package
does not know is rejected rather than interpreted optimistically — a grid
half-understood produces a form that looks right and is wrong.

- **Adding an optional field is additive** and does not bump the version. A
  reader on version 1 ignores what it does not recognise.
- **Removing or renaming a field, or changing what a value means, bumps it.**

## JSON

```json
{
  "schema_version": 1,
  "competition_name": "Autumn Opener 2026",
  "competition_coordinator": "Alex Aspen",
  "host_club": "Centennial",
  "coc": "Jamie Sample",
  "sessions": [
    {
      "number": 1,
      "date": "2026-10-03",
      "label": "Session 1",
      "officials": [
        {"name": "Casey Cedar", "position": "Starter", "deck_eval": true},
        {"name": "Emery Elm", "position": "Stroke Judge", "club": "BBST", "deck_eval": true},
        {"name": "Jamie Juniper", "position": "Timer", "lane": "3", "deck_eval": true},
        {"name": "Harper Hemlock", "position": "Inspector of Turns"}
      ]
    }
  ]
}
```

### Top level

| Field | Type | Required | Meaning |
|---|---|---|---|
| `schema_version` | integer | **yes** | Must be `1`. |
| `competition_name` | string | **yes** | Meet name, without a trailing date range. |
| `competition_coordinator` | string | no | Printed on every form. |
| `host_club` | string | no | Substituted for any official whose `club` is empty. Overridden by `--host-club`. |
| `coc` | string | no | Chief of Officials Committee contact. Overridden by `--coc`. |
| `sessions` | array | **yes** | Non-empty. Sorted by `number` on load, so the order they appear in does not matter. |

### Session

| Field | Type | Required | Meaning |
|---|---|---|---|
| `number` | integer ≥ 1 | **yes** | The session number as officials refer to it, and the one in the output filename. Unique within the grid. Not a positional index: a grid may publish sessions 4 and 7 alone. |
| `date` | `YYYY-MM-DD` | no | The day the session swims. |
| `label` | string | no | Defaults to `Session {number}`. |
| `date_text` | string | no | See [below](#date_text). |
| `officials` | array | no | Every assignment in the session, flagged or not. |

### Official

One entry per assignment, so an official working two sessions appears twice.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | **yes** | Full name. It is printed as given — nothing here expands initials. |
| `position` | string | **yes** | Officiating position, e.g. `Starter`, `Inspector of Turns`. |
| `club` | string | no | Club code. Empty means "from the host club", which is the grid convention for an unannotated official. |
| `lane` | string | no | Lane this assignment covers. A string, because grids write `1` for a timer and nothing for a starter. |
| `deck_eval` | boolean | no | Default `false`. `true` puts this assignment on an evaluation form. |

`deck_eval` also accepts `"true"`/`"false"`/`"yes"`/`"no"`/`"1"`/`"0"` as
strings, so the JSON and CSV encodings agree. Anything else is an error rather
than a falsy guess.

### Unflagged assignments belong in the grid

The grid holds every assignment, and the PDF writer selects the flagged
rows from it. Filtering earlier would make this schema unable to represent a
grid — which is what `officials-admin` needs to serve.

### `date_text`

A legacy accommodation, not a second way to say `date`. A published Sheet writes
its date line as free text and not every meet writes a calendar date there — a
draft grid may say "Day 1 of 3". The Sheet adapter puts such a line here,
already rendered for print, so nothing is lost. It is used only when `date` is
absent. **A new integration should send `date`.**

## CSV

The same grid, one row per assignment, meet-level fields repeated. Chosen
over a preamble-plus-table layout because it is what a spreadsheet exports and
what fill-down produces by hand.

```csv
schema_version,competition_name,competition_coordinator,host_club,coc,session_number,session_date,session_label,session_date_text,name,position,club,lane,deck_eval
1,Autumn Opener 2026,Alex Aspen,Centennial,Jamie Sample,1,2026-10-03,Session 1,,Casey Cedar,Starter,,,true
1,Autumn Opener 2026,Alex Aspen,Centennial,Jamie Sample,1,2026-10-03,Session 1,,Emery Elm,Stroke Judge,BBST,,true
1,Autumn Opener 2026,Alex Aspen,Centennial,Jamie Sample,1,2026-10-03,Session 1,,Jamie Juniper,Timer,,3,true
```

Required columns: `schema_version`, `competition_name`, `session_number`,
`name`, `position`. The rest may be omitted entirely.

A repeated meet-level value that **disagrees** between rows is an error, not a
first-one-wins. Same for a session dated two different ways. Silently picking a
winner would put the wrong meet name on a printed form and nobody would know
which row it came from.

Error messages count rows the way a spreadsheet does — row 1 is the header, so
the first assignment is row 2.

`--grid-csv` also accepts a **published-Sheet CSV export** saved to a file. The
two are told apart by shape (the Sheet layout has a header row whose second
column is exactly `Position`), so working offline from a downloaded grid needs
no special flag.

## How the grid reaches the form

| Grid field | PDF form field | `deck-eval-parser` canonical name |
|---|---|---|
| `competition_name` | `Competition Name` | `competition_name` |
| `competition_coordinator` | `Competition Coordinator` | `competition_coordinator` |
| `host_club` | `Host Club` | `host_club` |
| `coc` | `COC` | `coc` |
| `date` + `label` | `Date  Session` | `date_session` |
| `officials[].name` | `Name of OfficialRow{n}` | `official_name` |
| `officials[].club` or `host_club` | `ClubRow{n}` | `club` |
| `officials[].position` | `PositionRow{n}` | `position` |
| `officials[].lane` | `Lane numberRow{n}` | `lane_number` |

`Date  Session` — two spaces, as the form names it — renders as
`Sat, Oct 3, 2026 / Session 1`, or `date_text / label`, or the label alone when
there is no date at all.

The right-hand column is
[`deck-eval-parser`](https://github.com/swimblocks/deck-eval-parser)'s
`src/schema.py`, which reads these forms back. The names differ where nesting
makes a prefix redundant; this table is the mapping, so neither repo has to
guess.

The form's remaining fields — times worked, mentor, level, successful — are
filled in by hand on deck and are deliberately written empty.

## Deliberately not in version 1

- **`sub_position`.** ROW's grid distinguishes `Stroke Judge / Gallery Side`
  from `Stroke Judge / Window Side`, and the Sheet adapter reads that column —
  but only to derive `lane`. Nothing consumes the rest, and a published contract
  should not carry fields with no consumer. Adding it later is additive.
- **Officiating level, and how many times an official has worked a position.**
  Both appear on the form and both are filled in on deck. Sourcing them is
  `officials-admin`'s job, not the grid's.
