"""Tests for eval_gen.py"""


from unittest.mock import patch

from eval_gen import (
    _choose_fontsize,
    _extract_lane,
    _extract_year,
    _format_date_session,
    _is_incomplete_name,
    _parse_name_and_club,
    _resolve_incomplete_names,
    _strip_competition_name,
    parse_officials_grid,
)

# ---------------------------------------------------------------------------
# _strip_competition_name
# ---------------------------------------------------------------------------

class TestStripCompetitionName:
    def test_removes_month_date_suffix(self):
        assert _strip_competition_name(
            "Cunningham Classic 2026 - April 10-12, 2026"
        ) == "Cunningham Classic 2026"

    def test_leaves_name_without_suffix_unchanged(self):
        assert _strip_competition_name("Cunningham Classic 2026") == "Cunningham Classic 2026"

    def test_handles_different_months(self):
        assert _strip_competition_name("Spring Meet 2025 - March 5-6, 2025") == "Spring Meet 2025"

    def test_strips_trailing_whitespace(self):
        assert _strip_competition_name("Meet 2026  ") == "Meet 2026"


# ---------------------------------------------------------------------------
# _extract_year
# ---------------------------------------------------------------------------

class TestExtractYear:
    def test_finds_year_in_title(self):
        assert _extract_year("Cunningham Classic 2026 - April 10-12, 2026") == "2026"

    def test_returns_empty_when_no_year(self):
        assert _extract_year("Spring Championships") == ""

    def test_finds_first_year(self):
        assert _extract_year("Meet 2025 recap for 2026") == "2025"


# ---------------------------------------------------------------------------
# _format_date_session
# ---------------------------------------------------------------------------

class TestFormatDateSession:
    def test_saturday_session(self):
        header = "Session 2\nSaturday, Apr 11\nSenior Briefing: 6:55 am"
        assert _format_date_session(header, "2026") == "Sat, Apr 11, 2026 / Session 2"

    def test_friday_session(self):
        header = "Session 1\nFriday, Apr 10\nWarm-up: 4:00 pm"
        assert _format_date_session(header, "2026") == "Fri, Apr 10, 2026 / Session 1"

    def test_sunday_session(self):
        header = "Session 5\nSunday, Apr 12"
        assert _format_date_session(header, "2026") == "Sun, Apr 12, 2026 / Session 5"

    def test_no_year(self):
        header = "Session 1\nFriday, Apr 10"
        assert _format_date_session(header, "") == "Fri, Apr 10 / Session 1"

    def test_header_with_only_session_label(self):
        assert _format_date_session("Session 1", "2026") == "Session 1"


# ---------------------------------------------------------------------------
# _parse_name_and_club
# ---------------------------------------------------------------------------

class TestParseNameAndClub:
    def test_name_with_club_and_de(self):
        name, club = _parse_name_and_club("Alex Aspen (BBST) (DE)")
        assert name == "Alex Aspen"
        assert club == "BBST"

    def test_club_before_de(self):
        name, club = _parse_name_and_club("Blake Birch (TSC) (DE)")
        assert name == "Blake Birch"
        assert club == "TSC"

    def test_de_only_no_club(self):
        name, club = _parse_name_and_club("Casey Cedar (DE)")
        assert name == "Casey Cedar"
        assert club == ""

    def test_visiting_country_not_treated_as_club(self):
        name, club = _parse_name_and_club("Drew Dogwood (AUS)")
        assert name == "Drew Dogwood"
        assert club == ""

    def test_visiting_country_with_de(self):
        name, club = _parse_name_and_club("Drew Dogwood (AUS) (DE)")
        assert name == "Drew Dogwood"
        assert club == ""

    def test_shadow_not_treated_as_club(self):
        name, club = _parse_name_and_club("Gray Gum (Shadow)")
        assert name == "Gray Gum"
        assert club == ""

    def test_rcr_not_treated_as_club(self):
        name, club = _parse_name_and_club("Harper Hemlock (RCR)")
        assert name == "Harper Hemlock"
        assert club == ""

    def test_no_annotations(self):
        name, club = _parse_name_and_club("Indigo Ivy")
        assert name == "Indigo Ivy"
        assert club == ""

    def test_lane_annotation_not_treated_as_club(self):
        name, club = _parse_name_and_club("Emery Elm (Lane 4) (DE)")
        assert name == "Emery Elm"
        assert club == ""

    def test_ref_error_not_treated_as_club(self):
        name, club = _parse_name_and_club("Robin M (#REF!)")
        assert name == "Robin M"
        assert club == ""

    def test_four_letter_club_code(self):
        name, club = _parse_name_and_club("Finley Fir (MSSAC) (DE)")
        assert name == "Finley Fir"
        assert club == "MSSAC"


# ---------------------------------------------------------------------------
# _extract_lane
# ---------------------------------------------------------------------------

class TestExtractLane:
    def test_lane_from_entry_parenthetical(self):
        assert _extract_lane("Emery Elm (Lane 4) (DE)", "") == "4"

    def test_lane_from_sub_position(self):
        assert _extract_lane("Sage (DE)", "Lane 2") == "2"

    def test_lane_from_sub_position_not_entry(self):
        assert _extract_lane("Timer person (DE)", "Lane 6") == "6"

    def test_no_lane(self):
        assert _extract_lane("Casey Cedar (DE)", "") == ""

    def test_entry_lane_takes_priority_over_sub_position(self):
        # Entry says Lane 4, sub_position says Lane 2 – entry wins
        assert _extract_lane("Official (Lane 4) (DE)", "Lane 2") == "4"

    def test_lane_slash_notation(self):
        # "Lane 3/4" in IoT entries – returns the first lane number
        assert _extract_lane("Jamie Juniper (Lane 1/2) (DE)", "") == "1"


# ---------------------------------------------------------------------------
# _is_incomplete_name
# ---------------------------------------------------------------------------

class TestIsIncompleteName:
    def test_single_word_is_incomplete(self):
        assert _is_incomplete_name("Riley") is True

    def test_single_word_longer_is_incomplete(self):
        assert _is_incomplete_name("Sage") is True

    def test_bare_initial_is_incomplete(self):
        assert _is_incomplete_name("Robin M") is True

    def test_initial_with_period_is_incomplete(self):
        assert _is_incomplete_name("Quinn R.") is True

    def test_full_name_is_not_incomplete(self):
        assert _is_incomplete_name("Casey Cedar") is False

    def test_three_part_name_is_not_incomplete(self):
        assert _is_incomplete_name("Lane Larch Linden") is False

    def test_two_letter_last_name_is_not_incomplete(self):
        # "Ng" is a complete surname, not an initial
        assert _is_incomplete_name("Morgan Lu") is False


# ---------------------------------------------------------------------------
# _resolve_incomplete_names
# ---------------------------------------------------------------------------

class TestResolveIncompleteNames:
    def _make_officials(self, names):
        return {0: [{'name': n, 'position': 'Timer', 'club': '', 'lane': '1'} for n in names]}

    def test_complete_name_not_prompted(self):
        officials = self._make_officials(["Casey Cedar"])
        with patch('builtins.input') as mock_input:
            _resolve_incomplete_names(officials)
            mock_input.assert_not_called()
        assert officials[0][0]['name'] == "Casey Cedar"

    def test_incomplete_name_prompted_and_replaced(self):
        officials = self._make_officials(["Riley"])
        with patch('builtins.input', return_value="Noor Nettle"):
            _resolve_incomplete_names(officials)
        assert officials[0][0]['name'] == "Noor Nettle"

    def test_empty_input_keeps_original(self):
        officials = self._make_officials(["Riley"])
        with patch('builtins.input', return_value=""):
            _resolve_incomplete_names(officials)
        assert officials[0][0]['name'] == "Riley"

    def test_same_name_prompted_only_once_across_sessions(self):
        # "Riley" appears in two sessions — should only prompt once
        officials = {
            0: [{'name': 'Zoe', 'position': 'Timer', 'club': '', 'lane': '1'}],
            1: [{'name': 'Zoe', 'position': 'Timer', 'club': '', 'lane': '2'}],
        }
        with patch('builtins.input', return_value="Noor Nettle") as mock_input:
            _resolve_incomplete_names(officials)
            assert mock_input.call_count == 1
        assert officials[0][0]['name'] == "Noor Nettle"
        assert officials[1][0]['name'] == "Noor Nettle"

    def test_different_incomplete_names_each_prompted(self):
        officials = self._make_officials(["Riley", "Robin M"])
        responses = ["Noor Nettle", "Oakley Oak"]
        with patch('builtins.input', side_effect=responses) as mock_input:
            _resolve_incomplete_names(officials)
            assert mock_input.call_count == 2
        assert officials[0][0]['name'] == "Noor Nettle"
        assert officials[0][1]['name'] == "Oakley Oak"


# ---------------------------------------------------------------------------
# _choose_fontsize
# ---------------------------------------------------------------------------

class TestChooseFontsize:
    def test_short_text_gets_default_size(self):
        # "Hi" should easily fit at 12pt in a 100pt wide field
        assert _choose_fontsize("Hi", 100) == 12

    def test_very_long_text_shrinks(self):
        # Very long text in a very narrow field should shrink below 12
        size = _choose_fontsize("A" * 50, 30)
        assert size < 12

    def test_empty_string_gets_default(self):
        assert _choose_fontsize("", 50) == 12

    def test_minimum_font_size_floor(self):
        # Even impossibly long text in tiny field should not go below 6
        size = _choose_fontsize("A" * 200, 5)
        assert size == 6


# ---------------------------------------------------------------------------
# parse_officials_grid (integration-style with inline CSV)
# ---------------------------------------------------------------------------

# Minimal CSV that mirrors the real sheet structure.
# Session header cells contain embedded newlines, so they must be quoted.
_SAMPLE_CSV = (
    ',,,"Spring Meet 2026 - March 1-2, 2026",,,,\n'
    ',,,,,,,\n'
    ',Position,,"Session 1\nSaturday, Mar 1\nStart 9am","Session 2\nSunday, Mar 2\nStart 9am",,\n'
    ',Competition Coordinator,,Alice Coord,Alice Coord,,\n'
    ',Session Referee,,Bob Ref,Carol Ref,,\n'
    ',Starter,,Dave (DE),Eve (BBST) (DE),,\n'
    ',Timer,Lane 1,Frank (DE),Grace,,\n'
    ',Timer,Lane 2,Heidi,Ivan (TSC) (DE),,\n'
)


def _parse_sample() -> dict:
    import csv
    import io
    rows = list(csv.reader(io.StringIO(_SAMPLE_CSV)))
    return parse_officials_grid(rows)


class TestParseOfficialsGrid:
    def test_competition_name_stripped(self):
        grid = _parse_sample()
        assert grid['competition_name'] == "Spring Meet 2026"

    def test_year_extracted(self):
        grid = _parse_sample()
        assert grid['year'] == "2026"

    def test_coordinator_parsed(self):
        grid = _parse_sample()
        assert grid['coordinator'] == "Alice Coord"

    def test_de_officials_found(self):
        grid = _parse_sample()
        all_names = [o['name'] for offs in grid['de_officials'].values() for o in offs]
        assert "Dave" in all_names
        assert "Eve" in all_names
        assert "Frank" in all_names
        assert "Ivan" in all_names

    def test_non_de_officials_excluded(self):
        grid = _parse_sample()
        all_names = [o['name'] for offs in grid['de_officials'].values() for o in offs]
        assert "Grace" not in all_names
        assert "Heidi" not in all_names

    def test_club_extracted_from_name(self):
        grid = _parse_sample()
        all_offs = [o for offs in grid['de_officials'].values() for o in offs]
        eve = next(o for o in all_offs if o['name'] == "Eve")
        assert eve['club'] == "BBST"
        ivan = next(o for o in all_offs if o['name'] == "Ivan")
        assert ivan['club'] == "TSC"

    def test_no_club_annotation_gives_empty_string(self):
        grid = _parse_sample()
        all_offs = [o for offs in grid['de_officials'].values() for o in offs]
        dave = next(o for o in all_offs if o['name'] == "Dave")
        assert dave['club'] == ""

    def test_position_is_name_only(self):
        grid = _parse_sample()
        all_offs = [o for offs in grid['de_officials'].values() for o in offs]
        frank = next(o for o in all_offs if o['name'] == "Frank")
        assert frank['position'] == "Timer"
        assert "Lane" not in frank['position']

    def test_lane_extracted_from_sub_position(self):
        grid = _parse_sample()
        all_offs = [o for offs in grid['de_officials'].values() for o in offs]
        frank = next(o for o in all_offs if o['name'] == "Frank")
        assert frank['lane'] == "1"
        ivan = next(o for o in all_offs if o['name'] == "Ivan")
        assert ivan['lane'] == "2"
