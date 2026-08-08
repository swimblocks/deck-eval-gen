"""Published-Sheet adapter: reads ROW-style officials grids into a :class:`~deck_eval_gen.grid.Grid`.

This is one input path among several, and the only one that needs the network.
Everything Sheets-specific is confined here — column indices, the free-text
session headers, the ``(DE)`` and ``(CLUB)`` annotations officials write into
cells. Downstream code sees only the grid model.

The Sheet must be *published to the web* (File > Share > Publish to web), not
merely shared: this path deliberately reads a public artefact, so it needs no
Google credentials and no ``gcloud``.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.parse
from datetime import date as _date

import requests

from deck_eval_gen.grid import Grid, GridError, Official, Session

# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def resolve_to_csv_url(url: str) -> str:
    """Follow redirects and convert a published Google Sheets URL to its CSV export URL."""
    resp = requests.head(url, allow_redirects=True, timeout=15)
    final_url = resp.url

    # Strip any link-shortener / redirect wrapper to get the real Sheets URL.
    qs_match = re.search(r'[?&]u=([^&]+)', final_url)
    if qs_match:
        final_url = urllib.parse.unquote(qs_match.group(1))

    # Normalise pubhtml -> pub?output=csv
    if '/pubhtml' in final_url:
        gid_match = re.search(r'[?&]gid=(\d+)', final_url)
        gid = gid_match.group(1) if gid_match else '0'
        base = re.sub(r'/pubhtml.*', '', final_url)
        return f"{base}/pub?gid={gid}&single=true&output=csv"

    if '/pub' in final_url:
        if 'output=csv' not in final_url:
            sep = '&' if '?' in final_url else '?'
            return final_url + sep + 'output=csv'
        return final_url

    raise ValueError(
        f"Could not derive a CSV export URL from: {url}\n"
        "Make sure the sheet is published (File > Share > Publish to web)."
    )


def fetch_csv(url: str) -> list[list[str]]:
    """Download and parse CSV rows from a published Sheets URL (or a shortener pointing at one)."""
    csv_url = resolve_to_csv_url(url)
    resp = requests.get(csv_url, allow_redirects=True, timeout=15)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


def load_grid_url(url: str) -> Grid:
    """Fetch a published Sheet and return it as a :class:`Grid`."""
    return grid_from_sheet_rows(fetch_csv(url))


# ---------------------------------------------------------------------------
# Name / club parsing
# ---------------------------------------------------------------------------

# Parenthetical annotations that are definitively NOT club codes.
_NON_CLUB_ANNOTATIONS = frozenset({
    'DE',                                   # deck evaluation requested
    'SHADOW',                               # shadowing role
    'RCR',                                  # referee coaching review
    'AUS', 'USA', 'CAN', 'GBR', 'NZL',      # visiting country codes
    'FRA', 'GER', 'JPN', 'RSA',
})

_PAREN_RE = re.compile(r'\s*\(([^)]*)\)')
_LANE_IN_PAREN_RE = re.compile(r'^Lane\s*\d+(?:/\d+)*$', re.IGNORECASE)
_LANE_IN_ENTRY_RE = re.compile(r'\(Lane\s*(\d+)(?:/\d+)*\)', re.IGNORECASE)
_LANE_IN_SUBPOS_RE = re.compile(r'^Lane\s*(\d+)$', re.IGNORECASE)


def parse_name_and_club(entry: str) -> tuple[str, str]:
    """Return ``(clean_name, club_code)`` from an entry like ``Jane Doe (BBST) (DE)``.

    The first parenthetical that is not a known annotation is taken as the club
    code. Known non-club annotations: DE, Shadow, RCR, country codes (AUS …),
    Lane N, and ``#REF!``. If none is found, club is ``''`` — meaning the
    official is from the host club.
    """
    club = ''
    for m in _PAREN_RE.finditer(entry):
        content = m.group(1).strip()
        if content.upper() in _NON_CLUB_ANNOTATIONS:
            continue
        if _LANE_IN_PAREN_RE.match(content):
            continue
        if content == '#REF!':
            continue
        club = content
        break

    # Strip ALL parentheticals to get the clean name.
    name = _PAREN_RE.sub('', entry).strip()
    return name, club


def is_incomplete_name(name: str) -> bool:
    """Return True if *name* looks like it is missing a surname.

    Triggers on single-word names ("Zoe") and on names whose last word is a
    bare initial ("Harsh G", "Adrian S."). Grid cells are typed in a hurry, and
    an evaluation form wants the official's full name.
    """
    parts = name.split()
    if len(parts) == 1:
        return True
    last = parts[-1].rstrip('.')
    if len(last) == 1 and last.isalpha():
        return True
    return False


def extract_lane(entry: str, sub_position: str) -> str:
    """Return a lane number from the entry text, else from the column's sub-position."""
    m = _LANE_IN_ENTRY_RE.search(entry)
    if m:
        return m.group(1)
    m = _LANE_IN_SUBPOS_RE.match(sub_position)
    if m:
        return m.group(1)
    return ''


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

# Trailing date range on the meet title, e.g. " - April 10-12, 2026".
_DATE_SUFFIX_RE = re.compile(
    r'\s*-\s*(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\b.*$',
    re.IGNORECASE,
)

_DAY_ABBREVS = {
    'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
    'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat', 'Sunday': 'Sun',
}

_MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12,
}

# "Session 4" — the session's own number, which is what officials call it and
# what the output filename uses. Taken from the header rather than from column
# order, because a grid carries non-session columns too (a "Sign In &
# Briefings" note column sits to the right of the sessions on ROW's grid).
_SESSION_LABEL_RE = re.compile(r'^Session\s+(\d+)\b', re.IGNORECASE)

# "Saturday, Apr 11" / "Sat, April 11" / "Apr 11" — optional weekday, month
# name, day of month. A trailing range ("Apr 11-12") keeps the first day.
_DATE_LINE_RE = re.compile(
    r'^(?:[A-Za-z]+\.?,\s*)?(?P<month>[A-Za-z]+)\.?\s+(?P<dom>\d{1,2})\b',
)


def strip_competition_name(raw: str) -> str:
    """Remove the trailing date range from a meet title.

    ``"Cunningham Classic 2026 - April 10-12, 2026"`` -> ``"Cunningham Classic 2026"``
    """
    return _DATE_SUFFIX_RE.sub('', raw).strip()


def extract_year(text: str) -> str:
    """Return the first 4-digit year found in *text*, or ``''``."""
    m = re.search(r'\b(20\d{2})\b', text)
    return m.group(1) if m else ''


def render_date_line(date_line: str, year: str) -> str:
    """Abbreviate the weekday in a Sheet date line and append *year*.

    Preserves how the grid words its own date line, for the case where it is
    not a calendar date this adapter can parse — see ``Session.date_text``.
    """
    for full, abbr in _DAY_ABBREVS.items():
        if full in date_line:
            date_line = date_line.replace(full, abbr)
            break
    return f"{date_line}, {year}" if year else date_line


def _parse_session_header(header: str, year: str) -> Session | None:
    """Build a :class:`Session` from a session header cell, or None if it isn't one.

    Headers are multi-line free text::

        Session 2
        Saturday, Apr 11
        Senior Briefing: 6:55 am
        ...

    Only the first two lines are meaningful here; briefing and warm-up times
    are for the officials reading the grid, not for the evaluation form.
    """
    lines = [line.strip() for line in header.split('\n') if line.strip()]
    if not lines:
        return None

    label = lines[0]
    m = _SESSION_LABEL_RE.match(label)
    if not m:
        # Not a session column — grids carry note columns alongside the
        # sessions, and treating one as a session would misnumber every
        # session after it.
        return None
    number = int(m.group(1))

    if len(lines) < 2:
        return Session(number=number, label=label)

    date_line = lines[1]
    session_date = None
    date_match = _DATE_LINE_RE.match(date_line)
    if date_match and year:
        month = _MONTHS.get(date_match.group('month').lower())
        if month:
            try:
                session_date = _date(int(year), month, int(date_match.group('dom')))
            except ValueError:
                session_date = None

    return Session(
        number=number,
        date=session_date,
        label=label,
        # Only kept when the line is not a date we could parse, so the form
        # still prints what the grid said.
        date_text='' if session_date else render_date_line(date_line, year),
    )


# ---------------------------------------------------------------------------
# Grid parsing
# ---------------------------------------------------------------------------

# Rows that describe the meet rather than assign an official to a position.
_MEET_LEVEL_POSITIONS = frozenset({'Competition Coordinator'})


def grid_from_sheet_rows(rows: list[list[str]]) -> Grid:
    """Parse published-Sheet CSV rows into a :class:`Grid`.

    Every assignment is retained, not just the ones flagged ``(DE)`` — the grid
    grid holds every assignment, and the PDF writer selects the flagged
    ones. Cells hold one official per line, so a two-timer lane is two entries
    in one cell.
    """
    header_row_idx = next(
        (i for i, row in enumerate(rows) if len(row) > 1 and row[1].strip() == 'Position'),
        None,
    )
    if header_row_idx is None:
        raise GridError(
            "Could not find the 'Position' header row in the sheet. "
            "Is this the officials grid tab?"
        )

    raw_title = next(
        (cell.strip() for row in rows[:header_row_idx] for cell in row if cell.strip()),
        '',
    )
    year = extract_year(raw_title)

    header_row = rows[header_row_idx]
    sessions: dict[int, Session] = {}
    column_session: dict[int, int] = {}     # sheet column -> session number
    for col in range(3, len(header_row)):
        session = _parse_session_header(header_row[col].strip(), year)
        if session is None:
            continue
        if session.number in sessions:
            raise GridError(
                f"The sheet has two columns labelled 'Session {session.number}'"
            )
        sessions[session.number] = session
        column_session[col] = session.number

    if not sessions:
        raise GridError("No session columns found in the sheet (expected headers like 'Session 1').")

    coordinator = ''

    for row in rows[header_row_idx + 1:]:
        if len(row) < 2:
            continue
        position = row[1].strip()
        if not position:
            continue
        sub_position = row[2].strip() if len(row) > 2 else ''

        for col, number in column_session.items():
            if col >= len(row) or not row[col].strip():
                continue
            cell = row[col]

            if position in _MEET_LEVEL_POSITIONS:
                if not coordinator:
                    coordinator, _ = parse_name_and_club(cell.split('\n')[0])
                continue

            for entry in cell.split('\n'):
                entry = entry.strip()
                if not entry or entry == '#REF!':
                    continue
                name, club = parse_name_and_club(entry)
                if not name:
                    continue
                sessions[number].officials.append(Official(
                    name=name,
                    position=position,
                    club=club,                      # '' means "use host club"
                    lane=extract_lane(entry, sub_position),
                    deck_eval='(DE)' in entry,
                ))

    return Grid(
        competition_name=strip_competition_name(raw_title),
        competition_coordinator=coordinator,
        sessions=[sessions[n] for n in sorted(sessions)],
    )
