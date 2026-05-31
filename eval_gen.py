#!/usr/bin/env python3
"""eval-gen: Generate On-Deck Evaluation PDFs from a published officials grid Google Sheet.

Usage:
    python eval_gen.py <sheet_url> [options]

The sheet URL can be a tinyurl or direct Google Sheets published URL.
Officials marked with (DE) in the grid are included in the output PDF(s).
One PDF is produced per session (or per page if a session has >9 officials).
"""

import argparse
import csv
import io
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import requests

# ---------------------------------------------------------------------------
# Sheet fetching
# ---------------------------------------------------------------------------

def resolve_to_csv_url(url: str) -> str:
    """Follow redirects and convert a Google Sheets published URL to its CSV export URL."""
    resp = requests.head(url, allow_redirects=True, timeout=15)
    final_url = resp.url

    # Strip any viglink / redirect wrapper to get the real Sheets URL
    qs_match = re.search(r'[?&]u=([^&]+)', final_url)
    if qs_match:
        import urllib.parse
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
    """Download and parse CSV rows from a Google Sheets URL (or tinyurl pointing to one)."""
    csv_url = resolve_to_csv_url(url)
    resp = requests.get(csv_url, allow_redirects=True, timeout=15)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


# ---------------------------------------------------------------------------
# Name / club parsing
# ---------------------------------------------------------------------------

# Parenthetical annotations that are definitively NOT club codes
_NON_CLUB_ANNOTATIONS = frozenset({
    'DE',                                   # deck evaluation requested
    'SHADOW',                               # shadowing role
    'RCR',                                  # referee coaching review
    'AUS', 'USA', 'CAN', 'GBR', 'NZL',    # visiting country codes
    'FRA', 'GER', 'JPN', 'RSA',
})

_PAREN_RE = re.compile(r'\s*\(([^)]*)\)')
_LANE_IN_PAREN_RE = re.compile(r'^Lane\s*\d+(?:/\d+)*$', re.IGNORECASE)
_LANE_IN_ENTRY_RE = re.compile(r'\(Lane\s*(\d+)(?:/\d+)*\)', re.IGNORECASE)
_LANE_IN_SUBPOS_RE = re.compile(r'^Lane\s*(\d+)$', re.IGNORECASE)


def _parse_name_and_club(entry: str) -> tuple[str, str]:
    """Return (clean_name, club_code) from an entry like 'Jane Doe (BBST) (DE)'.

    The first parenthetical that is not a known annotation is taken as the club
    code.  Known non-club annotations: DE, Shadow, RCR, country codes (AUS …),
    Lane N, and #REF!.  If none found, club is returned as ''.
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

    # Strip ALL parentheticals to get the clean name
    name = _PAREN_RE.sub('', entry).strip()
    return name, club


def _is_incomplete_name(name: str) -> bool:
    """Return True if the name looks like it is missing a surname.

    Triggers on:
    - single-word names (e.g. "Zoe", "Janpreet")
    - names whose last word is a bare initial (e.g. "Harsh G", "Adrian S.")
    """
    parts = name.split()
    if len(parts) == 1:
        return True
    last = parts[-1].rstrip('.')
    if len(last) == 1 and last.isalpha():
        return True
    return False


def _resolve_incomplete_names(de_officials: dict) -> None:
    """Prompt the user to supply a full name for any official whose name looks incomplete.

    Each unique incomplete name is prompted only once; the correction is applied
    to every occurrence across all sessions.
    """
    corrections: dict[str, str] = {}   # original -> corrected (or same if user skipped)

    for officials in de_officials.values():
        for off in officials:
            if not _is_incomplete_name(off['name']):
                continue
            original = off['name']
            if original not in corrections:
                answer = input(
                    f"  '{original}' ({off['position']}) looks incomplete."
                    f" Full name [{original}]: "
                ).strip()
                corrections[original] = answer if answer else original
            off['name'] = corrections[original]


def _extract_lane(entry: str, sub_position: str) -> str:
    """Return a lane number string from the entry text or the column's sub-position."""
    m = _LANE_IN_ENTRY_RE.search(entry)
    if m:
        return m.group(1)
    m = _LANE_IN_SUBPOS_RE.match(sub_position)
    if m:
        return m.group(1)
    return ''


# ---------------------------------------------------------------------------
# Date / competition-name helpers
# ---------------------------------------------------------------------------

# Trailing date range like " - April 10-12, 2026"
_DATE_SUFFIX_RE = re.compile(
    r'\s*-\s*(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\b.*$',
    re.IGNORECASE,
)

_DAY_ABBREVS = {
    'Monday': 'Mon', 'Tuesday': 'Tue', 'Wednesday': 'Wed',
    'Thursday': 'Thu', 'Friday': 'Fri', 'Saturday': 'Sat', 'Sunday': 'Sun',
}


def _strip_competition_name(raw: str) -> str:
    """Remove trailing date range from the competition name.

    "Cunningham Classic 2026 - April 10-12, 2026"  ->  "Cunningham Classic 2026"
    """
    return _DATE_SUFFIX_RE.sub('', raw).strip()


def _extract_year(text: str) -> str:
    """Return the first 4-digit year found in *text*, or ''."""
    m = re.search(r'\b(20\d{2})\b', text)
    return m.group(1) if m else ''


def _format_date_session(session_header: str, year: str) -> str:
    """Format a session header into 'Abbr, Mon DD, YYYY - Session N'.

    Session header lines look like:
        Session 2
        Saturday, Apr 11
        Senior Briefing: 6:55 am
        ...
    """
    lines = [line.strip() for line in session_header.split('\n') if line.strip()]
    session_label = lines[0]
    if len(lines) < 2:
        return session_label

    date_line = lines[1]
    for full, abbr in _DAY_ABBREVS.items():
        if full in date_line:
            date_line = date_line.replace(full, abbr)
            break

    if year:
        date_line = f"{date_line}, {year}"

    return f"{date_line} / {session_label}"


# ---------------------------------------------------------------------------
# Grid parsing
# ---------------------------------------------------------------------------

def parse_officials_grid(rows: list[list[str]]) -> dict:
    """Parse the officials grid CSV.

    Returns a dict with keys:
        competition_name  : str   (date-range suffix stripped)
        year              : str   (4-digit year extracted from title)
        coordinator       : str
        sessions          : {col_index: header_text}
        de_officials      : {col_index: [{"name", "club", "position", "lane"}]}
    """
    header_row_idx = next(
        (i for i, row in enumerate(rows) if len(row) > 1 and row[1].strip() == 'Position'),
        None,
    )
    if header_row_idx is None:
        raise ValueError("Could not find the 'Position' header row in the spreadsheet.")

    raw_title = next(
        (cell.strip() for row in rows[:header_row_idx] for cell in row if cell.strip()),
        '',
    )
    competition_name = _strip_competition_name(raw_title)
    year = _extract_year(raw_title)

    header_row = rows[header_row_idx]
    sessions: dict[int, str] = {
        col: header_row[col].strip()
        for col in range(3, len(header_row))
        if col < len(header_row) and header_row[col].strip()
    }

    coordinator = ''
    de_officials: dict[int, list[dict]] = {}

    for row in rows[header_row_idx + 1:]:
        if len(row) < 2:
            continue
        position = row[1].strip()
        if not position:
            continue
        sub_position = row[2].strip() if len(row) > 2 else ''

        for col in sessions:
            if col >= len(row) or not row[col].strip():
                continue
            cell = row[col]

            if position == 'Competition Coordinator' and not coordinator:
                name, _ = _parse_name_and_club(cell.split('\n')[0])
                coordinator = name

            for entry in cell.split('\n'):
                entry = entry.strip()
                if not entry or '(DE)' not in entry:
                    continue
                name, club = _parse_name_and_club(entry)
                lane = _extract_lane(entry, sub_position)
                de_officials.setdefault(col, []).append({
                    'name': name,
                    'club': club,       # '' means "use host club"
                    'position': position,
                    'lane': lane,
                })

    return {
        'competition_name': competition_name,
        'year': year,
        'coordinator': coordinator,
        'sessions': sessions,
        'de_officials': de_officials,
    }


# ---------------------------------------------------------------------------
# PDF filling
# ---------------------------------------------------------------------------

_DEFAULT_FONTSIZE = 12
_MIN_FONTSIZE = 6
_FIELD_PADDING = 4   # points of horizontal padding inside a field


def _choose_fontsize(text: str, field_width: float) -> int:
    """Return the largest font size <= _DEFAULT_FONTSIZE that fits text in field_width."""
    if not text:
        return _DEFAULT_FONTSIZE
    for size in range(_DEFAULT_FONTSIZE, _MIN_FONTSIZE - 1, -1):
        if fitz.get_text_length(text, fontname="helv", fontsize=size) <= field_width:
            return size
    return _MIN_FONTSIZE


def _fill_widget(widget, value: str) -> None:
    """Set a widget's value and font size, then regenerate its appearance."""
    usable_width = max(widget.rect.width - _FIELD_PADDING, 1)
    widget.text_fontsize = _choose_fontsize(value, usable_width)
    widget.field_value = value
    widget.update()


def _build_fields(
    grid: dict,
    session_col: int,
    date_session: str,
    host_club: str,
    coc: str,
    page_officials: list,
    page_num: int,
    total_pages: int,
) -> dict[str, str]:
    """Build the flat field-name -> value dict for one page of officials."""
    fields: dict[str, str] = {
        'Competition Name':        grid['competition_name'],
        'Competition Coordinator': grid['coordinator'],
        'Level':                   '',
        'Date  Session':           date_session,
        'Host Club':               host_club,
        'COC':                     coc,
        'Page':                    str(page_num),
        'of':                      str(total_pages),
    }
    for i in range(1, 10):
        if i <= len(page_officials):
            off = page_officials[i - 1]
            fields[f'Name of OfficialRow{i}']                            = off['name']
            fields[f'ClubRow{i}']                                         = off['club'] or host_club
            fields[f'PositionRow{i}']                                     = off['position']
            fields[f'Lane numberRow{i}']                                  = off['lane']
            fields[f'How many times have you worked this positionRow{i}'] = ''
            fields[f'Mentor Official  Session refereeRow{i}']             = ''
            fields[f'LevelRow{i}']                                        = ''
            fields[f'Successful initialRow{i}']                           = ''
        else:
            fields[f'Name of OfficialRow{i}']                            = ''
            fields[f'ClubRow{i}']                                         = ''
            fields[f'PositionRow{i}']                                     = ''
            fields[f'Lane numberRow{i}']                                  = ''
            fields[f'How many times have you worked this positionRow{i}'] = ''
            fields[f'Mentor Official  Session refereeRow{i}']             = ''
            fields[f'LevelRow{i}']                                        = ''
            fields[f'Successful initialRow{i}']                           = ''
    return fields


def fill_session_pdf(
    template_path: Path,
    output_path: Path,
    grid: dict,
    session_col: int,
    host_club: str = '',
    coc: str = '',
) -> None:
    """Produce a filled PDF for session_col using PyMuPDF.

    Text is rendered at a consistent font size (shrunk only if it would overflow).
    Paginates at 9 officials per page.
    """
    officials = grid['de_officials'].get(session_col, [])
    if not officials:
        return

    date_session = _format_date_session(grid['sessions'][session_col], grid['year'])
    pages_of_officials = [officials[i:i+9] for i in range(0, len(officials), 9)]
    total_pages = len(pages_of_officials)

    output_doc = fitz.open()

    for page_num, page_officials in enumerate(pages_of_officials, start=1):
        fields = _build_fields(
            grid, session_col, date_session, host_club, coc,
            page_officials, page_num, total_pages,
        )

        tmpl = fitz.open(str(template_path))
        page = tmpl[0]

        for widget in page.widgets():
            name = widget.field_name
            if name in fields:
                _fill_widget(widget, fields[name])

        output_doc.insert_pdf(tmpl, from_page=0, to_page=0)
        tmpl.close()

    output_doc.save(str(output_path))
    output_doc.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Generate On-Deck Evaluation PDFs from a published officials-grid Google Sheet.\n'
            'Officials flagged with (DE) in the grid are written into the output PDF(s).'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'url',
        help='URL to the published officials grid (tinyurl or direct Google Sheets URL)',
    )
    parser.add_argument(
        '--session', '-s',
        type=int,
        metavar='N',
        help='Generate only for session N (1-based); default: all sessions with DE officials',
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='.',
        metavar='DIR',
        help='Directory for output PDFs (default: current directory)',
    )
    parser.add_argument(
        '--template', '-t',
        default=str(Path(__file__).parent / 'eval_form.pdf'),
        metavar='PATH',
        help='Path to the blank eval form PDF (default: eval_form.pdf next to this script)',
    )
    parser.add_argument(
        '--host-club',
        default='',
        metavar='NAME',
        help='Host club name; used for officials whose club is not noted in the grid',
    )
    parser.add_argument(
        '--coc',
        default='',
        metavar='NAME',
        help='Chief of Officials Committee name/contact for the COC field',
    )
    args = parser.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"Error: template PDF not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching officials grid ...")
    try:
        rows = fetch_csv(args.url)
    except Exception as exc:
        print(f"Error fetching sheet: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Parsing grid ...")
    grid = parse_officials_grid(rows)
    print(f"  Competition : {grid['competition_name']}")
    print(f"  Coordinator : {grid['coordinator']}")
    print(f"  Sessions    : {len(grid['sessions'])} found")
    total_de = sum(len(v) for v in grid['de_officials'].values())
    print(f"  DE officials: {total_de} across {len(grid['de_officials'])} session(s)")

    _resolve_incomplete_names(grid['de_officials'])

    sorted_cols = sorted(grid['sessions'].keys())
    if args.session is not None:
        if args.session < 1 or args.session > len(sorted_cols):
            print(
                f"Error: --session {args.session} is out of range "
                f"(sheet has {len(sorted_cols)} sessions)",
                file=sys.stderr,
            )
            sys.exit(1)
        target_col = sorted_cols[args.session - 1]
        cols_to_process = [target_col] if target_col in grid['de_officials'] else []
        if not cols_to_process:
            print(f"Session {args.session} has no DE officials - nothing to generate.")
            return
    else:
        cols_to_process = [c for c in sorted_cols if c in grid['de_officials']]

    if not cols_to_process:
        print("No sessions with DE officials found.")
        return

    session_num = {col: i + 1 for i, col in enumerate(sorted_cols)}

    for col in cols_to_process:
        n = session_num[col]
        officials = grid['de_officials'][col]
        out_path = output_dir / f"session_{n}_evals.pdf"
        print(f"  Session {n}: {len(officials)} official(s) -> {out_path}")
        fill_session_pdf(
            template_path, out_path, grid, col,
            host_club=args.host_club,
            coc=args.coc,
        )

    print("Done.")


if __name__ == '__main__':
    main()
