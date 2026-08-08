"""Tests for PDF output, including the criterion that made this change worth doing:
a grid document and the equivalent published Sheet must produce identical forms.
"""
from datetime import date

from deck_eval_gen.grid import (
    Grid,
    Official,
    Session,
    grid_from_dict,
    grid_to_dict,
    load_grid_json,
)
from deck_eval_gen.pdf import (
    ROWS_PER_PAGE,
    build_fields,
    choose_fontsize,
    default_template,
    fill_session_pdf,
    read_field_values,
)
from deck_eval_gen.sheet import grid_from_sheet_rows

HOST_CLUB = 'Centennial'
COC = 'Jamie Sample'


def _render(grid: Grid, session_number: int, out_dir) -> list[dict[str, str]]:
    """Render one session and read back what landed in the form fields."""
    grid = grid.with_defaults(host_club=HOST_CLUB, coc=COC)
    out_path = out_dir / f"session_{session_number}_evals.pdf"
    assert fill_session_pdf(default_template(), out_path, grid, grid.session(session_number))
    return read_field_values(out_path)


# ---------------------------------------------------------------------------
# The acceptance criterion
# ---------------------------------------------------------------------------

class TestJsonAndSheetAgree:
    """Identical PDFs from a JSON input and from the equivalent published Sheet.

    The two fixtures are written independently — ``sheet_export.csv`` in the
    grid layout a Sheet exports, ``grid.json`` by hand as a grid document — so
    this compares two separate descriptions of one meet, not a value against
    itself.
    """

    def test_every_session_matches(self, sheet_export_rows, grid_json_path, tmp_path):
        from_sheet = grid_from_sheet_rows(sheet_export_rows)
        from_json = load_grid_json(grid_json_path)

        assert [s.number for s in from_sheet.sessions] == [s.number for s in from_json.sessions]

        for session in from_sheet.sessions:
            sheet_dir = tmp_path / f"sheet{session.number}"
            json_dir = tmp_path / f"json{session.number}"
            sheet_dir.mkdir()
            json_dir.mkdir()
            assert _render(from_sheet, session.number, sheet_dir) == \
                   _render(from_json, session.number, json_dir), \
                   f"session {session.number} differs"

    def test_the_comparison_would_notice_a_difference(
        self, sheet_export_rows, grid_json_path, tmp_path
    ):
        # Guards the test above: if the field-value comparison were vacuous —
        # empty dicts, say — it would pass no matter what. Perturb one name and
        # the same comparison must fail.
        from_sheet = grid_from_sheet_rows(sheet_export_rows)
        tampered = load_grid_json(grid_json_path)
        tampered.session(1).deck_eval_officials[0].name = 'Someone Else'

        sheet_dir = tmp_path / 'sheet'
        json_dir = tmp_path / 'json'
        sheet_dir.mkdir()
        json_dir.mkdir()
        assert _render(from_sheet, 1, sheet_dir) != _render(tampered, 1, json_dir)

    def test_sheet_grid_survives_a_json_round_trip(self, sheet_export_rows, tmp_path):
        # What officials-admin will actually do: read the grid, serve it as
        # JSON, generate from what came back.
        from_sheet = grid_from_sheet_rows(sheet_export_rows)
        round_tripped = grid_from_dict(grid_to_dict(from_sheet))

        direct = tmp_path / 'direct'
        via_json = tmp_path / 'via_json'
        direct.mkdir()
        via_json.mkdir()
        assert _render(from_sheet, 1, direct) == _render(round_tripped, 1, via_json)


# ---------------------------------------------------------------------------
# Field contents
# ---------------------------------------------------------------------------

class TestBuildFields:
    def _grid(self) -> Grid:
        return Grid(
            competition_name='Autumn Opener 2026',
            competition_coordinator='Alex Aspen',
            host_club=HOST_CLUB,
            coc=COC,
            sessions=[Session(number=2, date=date(2026, 10, 3), officials=[
                Official(name='Casey Cedar', position='Starter', deck_eval=True),
                Official(name='Emery Elm', position='Timer', club='BBST',
                         lane='4', deck_eval=True),
            ])],
        )

    def test_meet_level_fields(self):
        grid = self._grid()
        fields = build_fields(grid, grid.session(2), grid.session(2).officials, 1, 1)
        assert fields['Competition Name'] == 'Autumn Opener 2026'
        assert fields['Competition Coordinator'] == 'Alex Aspen'
        assert fields['Host Club'] == HOST_CLUB
        assert fields['COC'] == COC
        assert fields['Date  Session'] == 'Sat, Oct 3, 2026 / Session 2'

    def test_official_rows(self):
        grid = self._grid()
        fields = build_fields(grid, grid.session(2), grid.session(2).officials, 1, 1)
        assert fields['Name of OfficialRow1'] == 'Casey Cedar'
        assert fields['PositionRow1'] == 'Starter'
        assert fields['Lane numberRow2'] == '4'
        assert fields['ClubRow2'] == 'BBST'

    def test_unannotated_club_falls_back_to_the_host_club(self):
        grid = self._grid()
        fields = build_fields(grid, grid.session(2), grid.session(2).officials, 1, 1)
        assert fields['ClubRow1'] == HOST_CLUB

    def test_unused_rows_are_blanked(self):
        grid = self._grid()
        fields = build_fields(grid, grid.session(2), grid.session(2).officials, 1, 1)
        for i in range(3, ROWS_PER_PAGE + 1):
            assert fields[f'Name of OfficialRow{i}'] == ''
            assert fields[f'ClubRow{i}'] == ''

    def test_hand_filled_columns_are_left_empty(self):
        # These get written on deck, by the evaluator.
        grid = self._grid()
        fields = build_fields(grid, grid.session(2), grid.session(2).officials, 1, 1)
        assert fields['How many times have you worked this positionRow1'] == ''
        assert fields['Mentor Official  Session refereeRow1'] == ''
        assert fields['Successful initialRow1'] == ''

    def test_pagination_counters(self):
        grid = self._grid()
        fields = build_fields(grid, grid.session(2), grid.session(2).officials, 2, 3)
        assert (fields['Page'], fields['of']) == ('2', '3')


# ---------------------------------------------------------------------------
# fill_session_pdf
# ---------------------------------------------------------------------------

class TestFillSessionPdf:
    def test_paginates_at_nine_officials_per_page(self, tmp_path):
        grid = Grid(competition_name='M', sessions=[Session(
            number=1,
            date=date(2026, 10, 3),
            officials=[
                Official(name=f'Official {i}', position='Timer', lane=str(i), deck_eval=True)
                for i in range(1, 12)
            ],
        )])
        pages = _render(grid, 1, tmp_path)
        assert len(pages) == 2
        assert pages[0]['Name of OfficialRow9'] == 'Official 9'
        assert pages[1]['Name of OfficialRow1'] == 'Official 10'
        assert pages[1]['Name of OfficialRow3'] == ''
        assert (pages[0]['Page'], pages[0]['of']) == ('1', '2')
        assert (pages[1]['Page'], pages[1]['of']) == ('2', '2')

    def test_unflagged_officials_are_not_on_the_form(self, tmp_path):
        grid = Grid(competition_name='M', sessions=[Session(number=1, officials=[
            Official(name='Not Flagged', position='Timer'),
            Official(name='Casey Cedar', position='Starter', deck_eval=True),
        ])])
        page = _render(grid, 1, tmp_path)[0]
        names = [page[f'Name of OfficialRow{i}'] for i in range(1, ROWS_PER_PAGE + 1)]
        assert names[0] == 'Casey Cedar'
        assert 'Not Flagged' not in names

    def test_writes_nothing_when_no_official_is_flagged(self, tmp_path):
        grid = Grid(competition_name='M', sessions=[Session(number=1, officials=[
            Official(name='Not Flagged', position='Timer'),
        ])])
        out_path = tmp_path / 'session_1_evals.pdf'
        assert fill_session_pdf(default_template(), out_path, grid, grid.session(1)) is False
        assert not out_path.exists()


# ---------------------------------------------------------------------------
# choose_fontsize
# ---------------------------------------------------------------------------

class TestChooseFontsize:
    def test_short_text_gets_default_size(self):
        assert choose_fontsize("Hi", 100) == 12

    def test_very_long_text_shrinks(self):
        assert choose_fontsize("A" * 50, 30) < 12

    def test_empty_string_gets_default(self):
        assert choose_fontsize("", 50) == 12

    def test_minimum_font_size_floor(self):
        assert choose_fontsize("A" * 200, 5) == 6
