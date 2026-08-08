"""Tests for the published-Sheet adapter. No network: fixtures are local CSV."""
from datetime import date

import pytest

from deck_eval_gen.grid import GridError
from deck_eval_gen.sheet import (
    extract_lane,
    extract_year,
    grid_from_sheet_rows,
    is_incomplete_name,
    parse_name_and_club,
    strip_competition_name,
)

# ---------------------------------------------------------------------------
# strip_competition_name
# ---------------------------------------------------------------------------

class TestStripCompetitionName:
    def test_removes_month_date_suffix(self):
        assert strip_competition_name(
            "Cunningham Classic 2026 - April 10-12, 2026"
        ) == "Cunningham Classic 2026"

    def test_leaves_name_without_suffix_unchanged(self):
        assert strip_competition_name("Cunningham Classic 2026") == "Cunningham Classic 2026"

    def test_handles_different_months(self):
        assert strip_competition_name("Spring Meet 2025 - March 5-6, 2025") == "Spring Meet 2025"

    def test_strips_trailing_whitespace(self):
        assert strip_competition_name("Meet 2026  ") == "Meet 2026"


# ---------------------------------------------------------------------------
# extract_year
# ---------------------------------------------------------------------------

class TestExtractYear:
    def test_finds_year_in_title(self):
        assert extract_year("Cunningham Classic 2026 - April 10-12, 2026") == "2026"

    def test_returns_empty_when_no_year(self):
        assert extract_year("Spring Championships") == ""

    def test_finds_first_year(self):
        assert extract_year("Meet 2025 recap for 2026") == "2025"


# ---------------------------------------------------------------------------
# parse_name_and_club
# ---------------------------------------------------------------------------

class TestParseNameAndClub:
    def test_name_with_club_and_de(self):
        assert parse_name_and_club("Alex Aspen (BBST) (DE)") == ("Alex Aspen", "BBST")

    def test_club_before_de(self):
        assert parse_name_and_club("Blake Birch (TSC) (DE)") == ("Blake Birch", "TSC")

    def test_de_only_no_club(self):
        assert parse_name_and_club("Casey Cedar (DE)") == ("Casey Cedar", "")

    def test_visiting_country_not_treated_as_club(self):
        assert parse_name_and_club("Drew Dogwood (AUS)") == ("Drew Dogwood", "")

    def test_visiting_country_with_de(self):
        assert parse_name_and_club("Drew Dogwood (AUS) (DE)") == ("Drew Dogwood", "")

    def test_shadow_not_treated_as_club(self):
        assert parse_name_and_club("Gray Gum (Shadow)") == ("Gray Gum", "")

    def test_rcr_not_treated_as_club(self):
        assert parse_name_and_club("Harper Hemlock (RCR)") == ("Harper Hemlock", "")

    def test_no_annotations(self):
        assert parse_name_and_club("Indigo Ivy") == ("Indigo Ivy", "")

    def test_lane_annotation_not_treated_as_club(self):
        assert parse_name_and_club("Emery Elm (Lane 4) (DE)") == ("Emery Elm", "")

    def test_ref_error_not_treated_as_club(self):
        assert parse_name_and_club("Robin M (#REF!)") == ("Robin M", "")

    def test_four_letter_club_code(self):
        assert parse_name_and_club("Finley Fir (MSSAC) (DE)") == ("Finley Fir", "MSSAC")


# ---------------------------------------------------------------------------
# extract_lane
# ---------------------------------------------------------------------------

class TestExtractLane:
    def test_lane_from_entry_parenthetical(self):
        assert extract_lane("Emery Elm (Lane 4) (DE)", "") == "4"

    def test_lane_from_sub_position(self):
        assert extract_lane("Sage (DE)", "Lane 2") == "2"

    def test_lane_from_sub_position_not_entry(self):
        assert extract_lane("Timer person (DE)", "Lane 6") == "6"

    def test_no_lane(self):
        assert extract_lane("Casey Cedar (DE)", "") == ""

    def test_entry_lane_takes_priority_over_sub_position(self):
        # Entry says Lane 4, sub_position says Lane 2 — entry wins
        assert extract_lane("Official (Lane 4) (DE)", "Lane 2") == "4"

    def test_lane_slash_notation(self):
        # "Lane 3/4" in IoT entries — returns the first lane number
        assert extract_lane("Jamie Juniper (Lane 1/2) (DE)", "") == "1"


# ---------------------------------------------------------------------------
# is_incomplete_name
# ---------------------------------------------------------------------------

class TestIsIncompleteName:
    def test_single_word_is_incomplete(self):
        assert is_incomplete_name("Riley") is True

    def test_bare_initial_is_incomplete(self):
        assert is_incomplete_name("Robin M") is True

    def test_initial_with_period_is_incomplete(self):
        assert is_incomplete_name("Quinn R.") is True

    def test_full_name_is_not_incomplete(self):
        assert is_incomplete_name("Casey Cedar") is False

    def test_three_part_name_is_not_incomplete(self):
        assert is_incomplete_name("Lane Larch Linden") is False

    def test_two_letter_last_name_is_not_incomplete(self):
        # "Lu" is a complete surname, not an initial
        assert is_incomplete_name("Morgan Lu") is False


# ---------------------------------------------------------------------------
# grid_from_sheet_rows
# ---------------------------------------------------------------------------

class TestGridFromSheetRows:
    def test_competition_name_and_coordinator(self, sheet_export_rows):
        grid = grid_from_sheet_rows(sheet_export_rows)
        assert grid.competition_name == "Autumn Opener 2026"
        assert grid.competition_coordinator == "Alex Aspen"

    def test_coordinator_is_not_also_an_assignment(self, sheet_export_rows):
        # The Competition Coordinator row is meet metadata, not a position
        # somebody is assigned to for a session.
        grid = grid_from_sheet_rows(sheet_export_rows)
        positions = {o.position for s in grid.sessions for o in s.officials}
        assert 'Competition Coordinator' not in positions

    def test_note_column_is_not_counted_as_a_session(self, sheet_export_rows):
        # The grid carries a "Sign In & Briefings" column to the right of the
        # sessions. Counting it would misnumber output files.
        grid = grid_from_sheet_rows(sheet_export_rows)
        assert [s.number for s in grid.sessions] == [1, 2]

    def test_session_dates_parsed_from_header(self, sheet_export_rows):
        grid = grid_from_sheet_rows(sheet_export_rows)
        assert grid.session(1).date == date(2026, 10, 3)
        assert grid.session(2).date == date(2026, 10, 4)
        # A parsed date leaves no free-text fallback behind.
        assert grid.session(1).date_text == ''

    def test_unflagged_officials_are_retained(self, sheet_export_rows):
        # The grid document describes the whole grid; the PDF writer selects
        # the flagged rows. officials-admin serves this shape wholesale.
        grid = grid_from_sheet_rows(sheet_export_rows)
        names = [o.name for o in grid.session(1).officials]
        assert names == [
            "Blake Birch", "Casey Cedar", "Emery Elm",
            "Gray Gum", "Harper Hemlock", "Jamie Juniper",
        ]
        assert [o.deck_eval for o in grid.session(1).officials] == [
            False, True, True, True, False, True,
        ]

    def test_clubs_and_lanes(self, sheet_export_rows):
        grid = grid_from_sheet_rows(sheet_export_rows)
        by_name = {o.name: o for o in grid.session(1).officials}
        assert by_name["Emery Elm"].club == "BBST"
        assert by_name["Casey Cedar"].club == ""        # host club, at render time
        assert by_name["Gray Gum"].lane == "1"          # from "(Lane 1/2)" in the cell
        assert by_name["Jamie Juniper"].lane == "3"     # from the "Lane 3" sub-position

    def test_multiple_officials_in_one_cell(self, sheet_export_rows):
        grid = grid_from_sheet_rows(sheet_export_rows)
        iot = [o for o in grid.session(1).officials if o.position == "Inspector of Turns"]
        assert [o.name for o in iot] == ["Gray Gum", "Harper Hemlock"]

    def test_deck_eval_sessions(self, sheet_export_rows):
        grid = grid_from_sheet_rows(sheet_export_rows)
        assert [s.number for s in grid.deck_eval_sessions] == [1, 2]
        assert len(grid.session(1).deck_eval_officials) == 4
        assert len(grid.session(2).deck_eval_officials) == 3

    def test_missing_header_row_is_an_error(self):
        with pytest.raises(GridError, match="Position"):
            grid_from_sheet_rows([['', 'Not a grid', '']])

    def test_no_session_columns_is_an_error(self):
        rows = [[''], ['', 'Position', '', 'Notes'], ['', 'Starter', '', 'Casey Cedar (DE)']]
        with pytest.raises(GridError, match="No session columns"):
            grid_from_sheet_rows(rows)

    def test_duplicate_session_number_is_an_error(self):
        rows = [
            ['', '', '', 'Meet 2026', ''],
            ['', 'Position', '', 'Session 1\nSaturday, Oct 3', 'Session 1\nSunday, Oct 4'],
        ]
        with pytest.raises(GridError, match="two columns labelled 'Session 1'"):
            grid_from_sheet_rows(rows)

    def test_ref_error_cells_are_skipped(self):
        rows = [
            ['', '', '', 'Meet 2026', ''],
            ['', 'Position', '', 'Session 1\nSaturday, Oct 3'],
            ['', 'Timer', 'Lane 1', '#REF!'],
        ]
        grid = grid_from_sheet_rows(rows)
        assert grid.session(1).officials == []

    def test_unparseable_date_line_keeps_the_grid_wording(self):
        # Some grids write a day label rather than a calendar date. Rather than
        # lose it, the adapter carries it as pre-rendered free text.
        rows = [
            ['', '', '', 'Meet 2026', ''],
            ['', 'Position', '', 'Session 1\nDay 1 of 3'],
            ['', 'Starter', '', 'Casey Cedar (DE)'],
        ]
        session = grid_from_sheet_rows(rows).session(1)
        assert session.date is None
        assert session.date_text == "Day 1 of 3, 2026"
        assert session.date_session() == "Day 1 of 3, 2026 / Session 1"

    def test_weekday_is_abbreviated_in_the_fallback(self):
        rows = [
            ['', '', '', 'Meet 2026', ''],
            ['', 'Position', '', 'Session 1\nSaturday the 3rd'],
            ['', 'Starter', '', 'Casey Cedar (DE)'],
        ]
        assert grid_from_sheet_rows(rows).session(1).date_text == "Sat the 3rd, 2026"

    def test_session_number_comes_from_the_header_not_column_order(self):
        # A grid may publish only the sessions that still need staffing.
        rows = [
            ['', '', '', 'Meet 2026', ''],
            ['', 'Position', '', 'Session 4\nSaturday, Oct 3', 'Session 7\nSunday, Oct 4'],
            ['', 'Starter', '', 'Casey Cedar (DE)', 'Drew Dogwood (DE)'],
        ]
        grid = grid_from_sheet_rows(rows)
        assert [s.number for s in grid.sessions] == [4, 7]
