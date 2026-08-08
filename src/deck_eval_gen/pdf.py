"""Fills the blank Swim Ontario deck-evaluation form from a grid.

The widget names and page layout here mirror ``eval_form.pdf``, which is also
what `deck-eval-parser <https://github.com/swimblocks/deck-eval-parser>`_'s
fillable-PDF fast path reads back. Changing a field name or the rows-per-page
count without a matching change to that repo's ``swim_ontario_v1`` template
breaks the round-trip.

This module knows nothing about where the grid came from.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from deck_eval_gen.grid import Grid, Session

# Rows the blank form has per page. Baked into the template, so it is not a
# preference — it is a fact about the PDF.
ROWS_PER_PAGE = 9

_DEFAULT_FONTSIZE = 12
_MIN_FONTSIZE = 6
_FIELD_PADDING = 4   # points of horizontal padding inside a field


def default_template() -> Path:
    """Path to the blank form shipped with this package."""
    return Path(__file__).with_name('eval_form.pdf')


def choose_fontsize(text: str, field_width: float) -> int:
    """Largest size <= 12pt at which *text* fits in *field_width*, floored at 6pt."""
    if not text:
        return _DEFAULT_FONTSIZE
    for size in range(_DEFAULT_FONTSIZE, _MIN_FONTSIZE - 1, -1):
        if fitz.get_text_length(text, fontname="helv", fontsize=size) <= field_width:
            return size
    return _MIN_FONTSIZE


def _fill_widget(widget, value: str) -> None:
    """Set a widget's value and font size, then regenerate its appearance."""
    usable_width = max(widget.rect.width - _FIELD_PADDING, 1)
    widget.text_fontsize = choose_fontsize(value, usable_width)
    widget.field_value = value
    widget.update()


def build_fields(
    grid: Grid,
    session: Session,
    page_officials: list,
    page_num: int,
    total_pages: int,
) -> dict[str, str]:
    """Build the flat field-name -> value map for one page of officials."""
    fields: dict[str, str] = {
        'Competition Name':        grid.competition_name,
        'Competition Coordinator': grid.competition_coordinator,
        'Level':                   '',
        'Date  Session':           session.date_session(),
        'Host Club':               grid.host_club,
        'COC':                     grid.coc,
        'Page':                    str(page_num),
        'of':                      str(total_pages),
    }
    for i in range(1, ROWS_PER_PAGE + 1):
        off = page_officials[i - 1] if i <= len(page_officials) else None
        fields[f'Name of OfficialRow{i}']                            = off.name if off else ''
        fields[f'ClubRow{i}']                                        = (
            (off.club or grid.host_club) if off else ''
        )
        fields[f'PositionRow{i}']                                    = off.position if off else ''
        fields[f'Lane numberRow{i}']                                 = off.lane if off else ''
        # Filled in by hand on deck, not by us.
        fields[f'How many times have you worked this positionRow{i}'] = ''
        fields[f'Mentor Official  Session refereeRow{i}']             = ''
        fields[f'LevelRow{i}']                                        = ''
        fields[f'Successful initialRow{i}']                           = ''
    return fields


def fill_session_pdf(
    template_path: Path,
    output_path: Path,
    grid: Grid,
    session: Session,
) -> bool:
    """Write the evaluation forms for *session*, paginated at 9 officials per page.

    Returns False without writing anything if the session has no officials
    flagged for evaluation.
    """
    officials = session.deck_eval_officials
    if not officials:
        return False

    pages_of_officials = [
        officials[i:i + ROWS_PER_PAGE] for i in range(0, len(officials), ROWS_PER_PAGE)
    ]
    total_pages = len(pages_of_officials)

    output_doc = fitz.open()
    try:
        for page_num, page_officials in enumerate(pages_of_officials, start=1):
            fields = build_fields(grid, session, page_officials, page_num, total_pages)

            tmpl = fitz.open(str(template_path))
            try:
                for widget in tmpl[0].widgets():
                    if widget.field_name in fields:
                        _fill_widget(widget, fields[widget.field_name])
                output_doc.insert_pdf(tmpl, from_page=0, to_page=0)
            finally:
                tmpl.close()

        output_doc.save(str(output_path))
    finally:
        output_doc.close()
    return True


def read_field_values(pdf_path: Path) -> list[dict[str, str]]:
    """Return each page's filled field values, keyed by form field name.

    Field names are normalised: merging several copies of one template into a
    multi-page document makes PyMuPDF disambiguate the repeated names by
    appending an xref number, so page 2's first name field is called
    ``Name of OfficialRow1 [226]``. The values are right and the form is usable,
    but the name a reader sees depends on which page it landed on.
    """
    doc = fitz.open(str(pdf_path))
    try:
        return [
            {_canonical_field_name(w.field_name): w.field_value for w in page.widgets()}
            for page in doc
        ]
    finally:
        doc.close()


_XREF_SUFFIX_RE = re.compile(r'\s*\[\d+\]$')


def _canonical_field_name(name: str) -> str:
    return _XREF_SUFFIX_RE.sub('', name)
