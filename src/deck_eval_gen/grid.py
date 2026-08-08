"""The grid: this package's input contract.

A *grid* is one meet's officials: the competition, its sessions,
who is assigned to which position in each, and which of those assignments have
been flagged for a deck evaluation. It is the single in-memory model every
input path produces and the PDF writer consumes, so a PDF generated from JSON
and one generated from the equivalent published Sheet are identical by
construction rather than by comparison.

The schema is documented in ``docs/grid-schema.md`` and versioned by
``SCHEMA_VERSION``. ``officials-admin`` will serve exactly this shape from
``/meets/{id}/grid.json``; treat a change here as a change to a published
interface.

Nothing in this module touches the network or Google APIs. The published-Sheet
adapter lives in :mod:`deck_eval_gen.sheet`.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# Bumped only for a breaking change. Adding an optional field is additive and
# does not bump it; removing or renaming one, or changing what a value means,
# does. A grid declaring a version this package does not know is rejected
# rather than guessed at.
SCHEMA_VERSION = 1

_MONTH_ABBR = (
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
)
_DAY_ABBR = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


class GridError(ValueError):
    """A grid is malformed, or declares an unsupported version."""


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class Official:
    """One official assigned to one position in one session.

    ``club`` is empty when the grid does not say — the caller's host club is
    substituted at render time, since an unannotated official is by convention
    from the host club.

    ``lane`` is the lane this assignment covers, as a string because grids
    write things like ``1`` for a timer and leave it blank for a starter. It is
    explicit here: the Sheet adapter derives it from the grid's sub-position
    column, but a grid states it outright.
    """

    name: str
    position: str
    club: str = ''
    lane: str = ''
    deck_eval: bool = False


@dataclass
class Session:
    """One session of a meet, with every assignment in it.

    ``number`` is the session number as officials refer to it and as it appears
    in output filenames — taken from the grid, not from column order.

    ``date`` is the day the session swims. Optional: a grid still being drafted
    may not have dates yet, and a session with no date simply prints its label
    alone on the form.

    ``date_text`` is a legacy accommodation, not a second way to say ``date``.
    A published Sheet writes its date line as free text, and not every meet
    writes a calendar date there — a draft grid may say "Day 1 of 3". The Sheet
    adapter puts such a line here, already rendered for print, so nothing is
    lost. It is used only when ``date`` is unset, and a new integration should
    send ``date``.
    """

    number: int
    date: date | None = None
    label: str = ''
    date_text: str = ''
    officials: list[Official] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.label:
            self.label = f"Session {self.number}"

    @property
    def deck_eval_officials(self) -> list[Official]:
        """The assignments flagged for a deck evaluation, in grid order."""
        return [o for o in self.officials if o.deck_eval]

    def date_session(self) -> str:
        """The form's "Date / Session" line, e.g. ``Sat, Apr 11, 2026 / Session 2``."""
        if self.date is not None:
            d = self.date
            rendered = f"{_DAY_ABBR[d.weekday()]}, {_MONTH_ABBR[d.month - 1]} {d.day}, {d.year}"
        elif self.date_text:
            rendered = self.date_text
        else:
            return self.label
        return f"{rendered} / {self.label}"


@dataclass
class Grid:
    """A meet's officials grid.

    ``host_club`` and ``coc`` are meet facts, so a grid may carry
    them; both are also CLI flags, because the published Sheet has nowhere to
    record them. An explicitly supplied value wins — see :meth:`with_defaults`.
    """

    competition_name: str
    competition_coordinator: str = ''
    host_club: str = ''
    coc: str = ''
    sessions: list[Session] = field(default_factory=list)

    def session(self, number: int) -> Session:
        """Return the session numbered *number*, or raise :class:`GridError`."""
        for s in self.sessions:
            if s.number == number:
                return s
        available = ', '.join(str(s.number) for s in self.sessions) or 'none'
        raise GridError(f"No session {number} in this grid (has: {available})")

    @property
    def deck_eval_sessions(self) -> list[Session]:
        """Sessions with at least one assignment flagged for evaluation."""
        return [s for s in self.sessions if s.deck_eval_officials]

    def with_defaults(self, host_club: str = '', coc: str = '') -> Grid:
        """Return a copy with *host_club* / *coc* filled in where non-empty.

        The caller's values override what the grid carries: a CLI flag is a
        deliberate act, and the Sheet path has no other way to supply them.
        """
        return Grid(
            competition_name=self.competition_name,
            competition_coordinator=self.competition_coordinator,
            host_club=host_club or self.host_club,
            coc=coc or self.coc,
            sessions=self.sessions,
        )


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def _require_mapping(obj: Any, where: str) -> dict:
    if not isinstance(obj, dict):
        raise GridError(f"{where}: expected an object, got {type(obj).__name__}")
    return obj


def _text(obj: dict, key: str, where: str, *, required: bool = False) -> str:
    value = obj.get(key)
    if value is None or value == '':
        if required:
            raise GridError(f"{where}: '{key}' is required")
        return ''
    if not isinstance(value, str):
        raise GridError(f"{where}: '{key}' must be a string, got {type(value).__name__}")
    return value.strip()


def _parse_iso_date(value: Any, where: str) -> date | None:
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise GridError(f"{where}: 'date' must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise GridError(f"{where}: 'date' is not a valid YYYY-MM-DD date: {value!r}") from exc


def _parse_bool(value: Any, where: str, key: str) -> bool:
    if value is None or value == '':
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', 'yes', 'y', '1'):
            return True
        if lowered in ('false', 'no', 'n', '0'):
            return False
    raise GridError(f"{where}: '{key}' must be true or false, got {value!r}")


def grid_from_dict(doc: Any) -> Grid:
    """Build a :class:`Grid` from a decoded grid.

    Raises :class:`GridError` with the offending location named, so a bad
    grid from an API response is diagnosable without a debugger.
    """
    doc = _require_mapping(doc, 'grid')

    declared = doc.get('schema_version')
    if declared is None:
        raise GridError(
            "grid: 'schema_version' is required "
            f"(this package speaks version {SCHEMA_VERSION})"
        )
    if declared != SCHEMA_VERSION:
        raise GridError(
            f"grid: unsupported schema_version {declared!r}; "
            f"this package speaks version {SCHEMA_VERSION}"
        )

    raw_sessions = doc.get('sessions')
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise GridError("grid: 'sessions' must be a non-empty list")

    sessions: list[Session] = []
    seen: set[int] = set()
    for i, raw in enumerate(raw_sessions):
        where = f"sessions[{i}]"
        raw = _require_mapping(raw, where)

        number = raw.get('number')
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise GridError(f"{where}: 'number' must be an integer >= 1, got {number!r}")
        if number in seen:
            raise GridError(f"{where}: duplicate session number {number}")
        seen.add(number)

        officials: list[Official] = []
        raw_officials = raw.get('officials', [])
        if not isinstance(raw_officials, list):
            raise GridError(f"{where}: 'officials' must be a list")
        for j, raw_off in enumerate(raw_officials):
            off_where = f"{where}.officials[{j}]"
            raw_off = _require_mapping(raw_off, off_where)
            officials.append(Official(
                name=_text(raw_off, 'name', off_where, required=True),
                position=_text(raw_off, 'position', off_where, required=True),
                club=_text(raw_off, 'club', off_where),
                lane=_text(raw_off, 'lane', off_where),
                deck_eval=_parse_bool(raw_off.get('deck_eval'), off_where, 'deck_eval'),
            ))

        sessions.append(Session(
            number=number,
            date=_parse_iso_date(raw.get('date'), where),
            label=_text(raw, 'label', where),
            date_text=_text(raw, 'date_text', where),
            officials=officials,
        ))

    sessions.sort(key=lambda s: s.number)
    return Grid(
        competition_name=_text(doc, 'competition_name', 'grid', required=True),
        competition_coordinator=_text(doc, 'competition_coordinator', 'grid'),
        host_club=_text(doc, 'host_club', 'grid'),
        coc=_text(doc, 'coc', 'grid'),
        sessions=sessions,
    )


def grid_to_dict(grid: Grid) -> dict:
    """Serialise *grid* back to a grid. Round-trips through :func:`grid_from_dict`."""
    return {
        'schema_version': SCHEMA_VERSION,
        'competition_name': grid.competition_name,
        'competition_coordinator': grid.competition_coordinator,
        'host_club': grid.host_club,
        'coc': grid.coc,
        'sessions': [
            {
                'number': s.number,
                'date': s.date.isoformat() if s.date else None,
                'label': s.label,
                'date_text': s.date_text,
                'officials': [
                    {
                        'name': o.name,
                        'position': o.position,
                        'club': o.club,
                        'lane': o.lane,
                        'deck_eval': o.deck_eval,
                    }
                    for o in s.officials
                ],
            }
            for s in grid.sessions
        ],
    }


def load_grid_json(source: str | Path) -> Grid:
    """Read a grid from a JSON file path, or ``-`` for stdin."""
    text = _read_text(source)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GridError(f"{_name_of(source)}: not valid JSON: {exc}") from exc
    return grid_from_dict(doc)


# ---------------------------------------------------------------------------
# Flat CSV
#
# One row per assignment, with the meet-level fields repeated. Chosen over a
# preamble-plus-table layout because it is what a spreadsheet exports and what
# fill-down produces by hand.
# ---------------------------------------------------------------------------

_CSV_MEET_COLUMNS = ('competition_name', 'competition_coordinator', 'host_club', 'coc')
_CSV_REQUIRED_COLUMNS = (
    'schema_version', 'competition_name', 'session_number', 'name', 'position',
)


def grid_from_csv_rows(rows: list[dict[str, str]]) -> Grid:
    """Build a :class:`Grid` from parsed flat-CSV rows (``DictReader`` output)."""
    if not rows:
        raise GridError("grid CSV: no data rows")

    missing = [c for c in _CSV_REQUIRED_COLUMNS if c not in rows[0]]
    if missing:
        raise GridError(f"grid CSV: missing required column(s): {', '.join(missing)}")

    meet: dict[str, str] = {}
    sessions: dict[int, Session] = {}

    for i, row in enumerate(rows, start=2):   # start=2: row 1 is the header
        where = f"grid CSV row {i}"

        declared = (row.get('schema_version') or '').strip()
        if declared != str(SCHEMA_VERSION):
            raise GridError(
                f"{where}: unsupported schema_version {declared!r}; "
                f"this package speaks version {SCHEMA_VERSION}"
            )

        # Meet-level fields are repeated on every row. Take the first non-empty
        # value and refuse to pick a winner if a later row disagrees.
        for column in _CSV_MEET_COLUMNS:
            value = (row.get(column) or '').strip()
            if not value:
                continue
            if column in meet and meet[column] != value:
                raise GridError(
                    f"{where}: '{column}' is {value!r} here but {meet[column]!r} on an "
                    "earlier row; meet-level fields must agree on every row"
                )
            meet[column] = value

        raw_number = (row.get('session_number') or '').strip()
        if not raw_number.isdigit() or int(raw_number) < 1:
            raise GridError(f"{where}: 'session_number' must be an integer >= 1, got {raw_number!r}")
        number = int(raw_number)

        session_date = _parse_iso_date((row.get('session_date') or '').strip() or None, where)
        label = (row.get('session_label') or '').strip()

        if number not in sessions:
            sessions[number] = Session(
                number=number,
                date=session_date,
                label=label,
                date_text=(row.get('session_date_text') or '').strip(),
            )
        else:
            existing = sessions[number]
            if session_date and existing.date and session_date != existing.date:
                raise GridError(
                    f"{where}: session {number} is dated {session_date} here but "
                    f"{existing.date} on an earlier row"
                )
            if session_date and not existing.date:
                existing.date = session_date

        name = (row.get('name') or '').strip()
        position = (row.get('position') or '').strip()
        if not name:
            raise GridError(f"{where}: 'name' is required")
        if not position:
            raise GridError(f"{where}: 'position' is required")

        sessions[number].officials.append(Official(
            name=name,
            position=position,
            club=(row.get('club') or '').strip(),
            lane=(row.get('lane') or '').strip(),
            deck_eval=_parse_bool((row.get('deck_eval') or '').strip(), where, 'deck_eval'),
        ))

    if 'competition_name' not in meet:
        raise GridError("grid CSV: 'competition_name' is empty on every row")

    return Grid(
        competition_name=meet['competition_name'],
        competition_coordinator=meet.get('competition_coordinator', ''),
        host_club=meet.get('host_club', ''),
        coc=meet.get('coc', ''),
        sessions=[sessions[n] for n in sorted(sessions)],
    )


def grid_to_csv(grid: Grid) -> str:
    """Serialise *grid* as flat CSV. Round-trips through :func:`grid_from_csv_rows`."""
    columns = [
        'schema_version', *_CSV_MEET_COLUMNS,
        'session_number', 'session_date', 'session_label', 'session_date_text',
        'name', 'position', 'club', 'lane', 'deck_eval',
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    for session in grid.sessions:
        for off in session.officials:
            writer.writerow({
                'schema_version': SCHEMA_VERSION,
                'competition_name': grid.competition_name,
                'competition_coordinator': grid.competition_coordinator,
                'host_club': grid.host_club,
                'coc': grid.coc,
                'session_number': session.number,
                'session_date': session.date.isoformat() if session.date else '',
                'session_label': session.label,
                'session_date_text': session.date_text,
                'name': off.name,
                'position': off.position,
                'club': off.club,
                'lane': off.lane,
                'deck_eval': 'true' if off.deck_eval else 'false',
            })
    return buf.getvalue()


def load_grid_csv(source: str | Path) -> Grid:
    """Read a grid from a CSV file path, or ``-`` for stdin.

    Accepts either encoding of the grid: the flat CSV documented in
    ``docs/grid-schema.md``, or a published-Sheet CSV export saved to a file.
    The two are told apart by shape, so an ``officials.csv`` pulled from the
    Sheet for offline work needs no special flag.
    """
    text = _read_text(source)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise GridError(f"{_name_of(source)}: empty CSV")

    if _looks_like_sheet_export(rows):
        # Imported here rather than at module scope: `sheet` imports this
        # module for the model, and `requests` should not be a hard dependency
        # of reading a local file.
        from deck_eval_gen.sheet import grid_from_sheet_rows
        return grid_from_sheet_rows(rows)

    reader = csv.DictReader(io.StringIO(text))
    return grid_from_csv_rows(list(reader))


def _looks_like_sheet_export(rows: list[list[str]]) -> bool:
    """True if *rows* are a published-Sheet export rather than the flat CSV.

    The Sheet layout has a header row whose second column is exactly
    ``Position``; the flat CSV's header is a single row of field names.
    """
    return any(len(row) > 1 and row[1].strip() == 'Position' for row in rows)


# ---------------------------------------------------------------------------
# Shared IO
# ---------------------------------------------------------------------------

def _name_of(source: str | Path) -> str:
    return '<stdin>' if str(source) == '-' else str(source)


def _read_text(source: str | Path) -> str:
    if str(source) == '-':
        import sys
        return sys.stdin.read()
    path = Path(source)
    if not path.exists():
        raise GridError(f"{path}: no such file")
    # utf-8-sig: Sheets exports and Excel round-trips both carry a BOM.
    return path.read_text(encoding='utf-8-sig')
