"""Tests for the grid document: the model, its validation, and both codecs."""
import csv
import io
import json
from datetime import date

import pytest

from deck_eval_gen.grid import (
    SCHEMA_VERSION,
    Grid,
    GridError,
    Official,
    Session,
    grid_from_csv_rows,
    grid_from_dict,
    grid_to_csv,
    grid_to_dict,
    load_grid_csv,
    load_grid_json,
)
from deck_eval_gen.sheet import grid_from_sheet_rows


def _doc(**overrides) -> dict:
    doc = {
        'schema_version': SCHEMA_VERSION,
        'competition_name': 'Autumn Opener 2026',
        'sessions': [
            {
                'number': 1,
                'date': '2026-10-03',
                'officials': [
                    {'name': 'Casey Cedar', 'position': 'Starter', 'deck_eval': True},
                ],
            },
        ],
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# Model behaviour
# ---------------------------------------------------------------------------

class TestSession:
    def test_label_defaults_to_the_session_number(self):
        assert Session(number=3).label == "Session 3"

    def test_explicit_label_is_kept(self):
        assert Session(number=3, label="Finals").label == "Finals"

    def test_date_session_line(self):
        session = Session(number=2, date=date(2026, 10, 3))
        assert session.date_session() == "Sat, Oct 3, 2026 / Session 2"

    def test_date_session_without_a_date_is_the_label_alone(self):
        assert Session(number=2).date_session() == "Session 2"

    def test_a_real_date_wins_over_the_free_text_fallback(self):
        session = Session(number=1, date=date(2026, 10, 3), date_text="Day 1 of 3")
        assert session.date_session() == "Sat, Oct 3, 2026 / Session 1"

    def test_deck_eval_officials_keeps_grid_order(self):
        session = Session(number=1, officials=[
            Official(name='A', position='Timer'),
            Official(name='B', position='Timer', deck_eval=True),
            Official(name='C', position='Timer', deck_eval=True),
        ])
        assert [o.name for o in session.deck_eval_officials] == ['B', 'C']


class TestGrid:
    def test_session_lookup(self):
        grid = Grid(competition_name='M', sessions=[Session(number=4)])
        assert grid.session(4).number == 4

    def test_session_lookup_names_what_is_available(self):
        grid = Grid(competition_name='M', sessions=[Session(number=4), Session(number=7)])
        with pytest.raises(GridError, match=r"No session 5 in this grid \(has: 4, 7\)"):
            grid.session(5)

    def test_with_defaults_fills_empty_fields(self):
        grid = Grid(competition_name='M').with_defaults(host_club='Centennial', coc='Jane')
        assert (grid.host_club, grid.coc) == ('Centennial', 'Jane')

    def test_caller_values_override_the_document(self):
        # A CLI flag is a deliberate act; the Sheet path has no other way in.
        grid = Grid(competition_name='M', host_club='Old', coc='Old')
        assert grid.with_defaults(host_club='New').host_club == 'New'
        assert grid.with_defaults(host_club='New').coc == 'Old'

    def test_with_defaults_leaves_the_original_alone(self):
        grid = Grid(competition_name='M')
        grid.with_defaults(host_club='Centennial')
        assert grid.host_club == ''


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

class TestGridFromDict:
    def test_minimal_document(self):
        grid = grid_from_dict(_doc())
        assert grid.competition_name == 'Autumn Opener 2026'
        assert grid.session(1).date == date(2026, 10, 3)
        assert grid.session(1).officials[0].name == 'Casey Cedar'

    def test_optional_fields_default(self):
        official = grid_from_dict(_doc()).session(1).officials[0]
        assert (official.club, official.lane) == ('', '')

    def test_sessions_are_sorted_by_number(self):
        doc = _doc(sessions=[
            {'number': 3, 'officials': []},
            {'number': 1, 'officials': []},
        ])
        assert [s.number for s in grid_from_dict(doc).sessions] == [1, 3]

    def test_missing_schema_version_is_rejected(self):
        doc = _doc()
        del doc['schema_version']
        with pytest.raises(GridError, match="'schema_version' is required"):
            grid_from_dict(doc)

    def test_future_schema_version_is_rejected_not_guessed_at(self):
        with pytest.raises(GridError, match="unsupported schema_version"):
            grid_from_dict(_doc(schema_version=SCHEMA_VERSION + 1))

    def test_missing_competition_name_is_rejected(self):
        doc = _doc()
        del doc['competition_name']
        with pytest.raises(GridError, match="'competition_name' is required"):
            grid_from_dict(doc)

    def test_empty_sessions_is_rejected(self):
        with pytest.raises(GridError, match="non-empty list"):
            grid_from_dict(_doc(sessions=[]))

    def test_duplicate_session_number_is_rejected(self):
        doc = _doc(sessions=[{'number': 1, 'officials': []}, {'number': 1, 'officials': []}])
        with pytest.raises(GridError, match="duplicate session number 1"):
            grid_from_dict(doc)

    @pytest.mark.parametrize('number', [0, -1, '1', 1.5, True])
    def test_bad_session_number_is_rejected(self, number):
        doc = _doc(sessions=[{'number': number, 'officials': []}])
        with pytest.raises(GridError, match="'number' must be an integer"):
            grid_from_dict(doc)

    def test_bad_date_names_the_session(self):
        doc = _doc(sessions=[{'number': 1, 'date': '2026-13-40', 'officials': []}])
        with pytest.raises(GridError, match=r"sessions\[0\]: 'date' is not a valid"):
            grid_from_dict(doc)

    def test_missing_official_name_names_the_row(self):
        doc = _doc(sessions=[{'number': 1, 'officials': [{'position': 'Timer'}]}])
        with pytest.raises(GridError, match=r"sessions\[0\].officials\[0\]: 'name' is required"):
            grid_from_dict(doc)

    def test_missing_official_position_is_rejected(self):
        doc = _doc(sessions=[{'number': 1, 'officials': [{'name': 'Casey Cedar'}]}])
        with pytest.raises(GridError, match="'position' is required"):
            grid_from_dict(doc)

    @pytest.mark.parametrize('value,expected', [
        (True, True), (False, False), ('true', True), ('False', False),
        ('yes', True), ('no', False), ('1', True), ('0', False), (None, False), ('', False),
    ])
    def test_deck_eval_accepts_json_and_csv_spellings(self, value, expected):
        doc = _doc(sessions=[{
            'number': 1,
            'officials': [{'name': 'C', 'position': 'Timer', 'deck_eval': value}],
        }])
        assert grid_from_dict(doc).session(1).officials[0].deck_eval is expected

    def test_nonsense_deck_eval_is_rejected(self):
        doc = _doc(sessions=[{
            'number': 1,
            'officials': [{'name': 'C', 'position': 'Timer', 'deck_eval': 'maybe'}],
        }])
        with pytest.raises(GridError, match="must be true or false"):
            grid_from_dict(doc)

    def test_not_an_object_is_rejected(self):
        with pytest.raises(GridError, match="expected an object"):
            grid_from_dict([1, 2, 3])


class TestJsonRoundTrip:
    def test_dict_round_trip_preserves_everything(self, sheet_export_rows):
        original = grid_from_sheet_rows(sheet_export_rows)
        assert grid_to_dict(grid_from_dict(grid_to_dict(original))) == grid_to_dict(original)

    def test_serialised_form_declares_the_version(self, sheet_export_rows):
        doc = grid_to_dict(grid_from_sheet_rows(sheet_export_rows))
        assert doc['schema_version'] == SCHEMA_VERSION

    def test_load_from_file(self, grid_json_path):
        grid = load_grid_json(grid_json_path)
        assert grid.competition_name == 'Autumn Opener 2026'
        assert len(grid.sessions) == 2

    def test_bad_json_says_so(self, tmp_path):
        path = tmp_path / 'grid.json'
        path.write_text('{not json', encoding='utf-8')
        with pytest.raises(GridError, match="not valid JSON"):
            load_grid_json(path)

    def test_missing_file_says_so(self, tmp_path):
        with pytest.raises(GridError, match="no such file"):
            load_grid_json(tmp_path / 'absent.json')

    def test_reads_stdin(self, monkeypatch):
        monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(_doc())))
        assert load_grid_json('-').competition_name == 'Autumn Opener 2026'


# ---------------------------------------------------------------------------
# Flat CSV
# ---------------------------------------------------------------------------

def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


_FLAT_CSV = (
    'schema_version,competition_name,competition_coordinator,host_club,coc,'
    'session_number,session_date,session_label,name,position,club,lane,deck_eval\n'
    '1,Autumn Opener 2026,Alex Aspen,Centennial,Jane Smith,'
    '1,2026-10-03,Session 1,Casey Cedar,Starter,,,true\n'
    '1,Autumn Opener 2026,Alex Aspen,Centennial,Jane Smith,'
    '1,2026-10-03,Session 1,Emery Elm,Stroke Judge,BBST,,true\n'
    '1,Autumn Opener 2026,Alex Aspen,Centennial,Jane Smith,'
    '2,2026-10-04,Session 2,Drew Dogwood,Timer,,3,false\n'
)


class TestGridFromCsvRows:
    def test_meet_fields_come_from_the_repeated_columns(self):
        grid = grid_from_csv_rows(_csv_rows(_FLAT_CSV))
        assert grid.competition_name == 'Autumn Opener 2026'
        assert grid.competition_coordinator == 'Alex Aspen'
        assert grid.host_club == 'Centennial'
        assert grid.coc == 'Jane Smith'

    def test_rows_group_into_sessions(self):
        grid = grid_from_csv_rows(_csv_rows(_FLAT_CSV))
        assert [s.number for s in grid.sessions] == [1, 2]
        assert [o.name for o in grid.session(1).officials] == ['Casey Cedar', 'Emery Elm']
        assert grid.session(2).date == date(2026, 10, 4)

    def test_deck_eval_flag(self):
        grid = grid_from_csv_rows(_csv_rows(_FLAT_CSV))
        assert [o.deck_eval for o in grid.session(1).officials] == [True, True]
        assert grid.session(2).officials[0].deck_eval is False

    def test_disagreeing_meet_field_is_an_error_not_a_silent_winner(self):
        text = _FLAT_CSV.replace('Centennial,Jane Smith,2,', 'Riverside,Jane Smith,2,')
        with pytest.raises(GridError, match="must agree on every row"):
            grid_from_csv_rows(_csv_rows(text))

    def test_disagreeing_session_date_is_an_error(self):
        text = _FLAT_CSV.replace('1,2026-10-03,Session 1,Emery Elm', '1,2026-10-05,Session 1,Emery Elm')
        with pytest.raises(GridError, match="is dated 2026-10-05 here but 2026-10-03"):
            grid_from_csv_rows(_csv_rows(text))

    def test_missing_required_column_is_named(self):
        text = _FLAT_CSV.replace('name,position', 'official,position')
        with pytest.raises(GridError, match="missing required column"):
            grid_from_csv_rows(_csv_rows(text))

    def test_wrong_schema_version_is_rejected(self):
        text = _FLAT_CSV.replace('\n1,Autumn', '\n2,Autumn', 1)
        with pytest.raises(GridError, match="unsupported schema_version"):
            grid_from_csv_rows(_csv_rows(text))

    def test_no_data_rows_is_an_error(self):
        with pytest.raises(GridError, match="no data rows"):
            grid_from_csv_rows([])

    def test_row_number_in_the_error_matches_the_spreadsheet(self):
        # Row 1 is the header, so the first data row is row 2 — what the
        # person looking at the file in a spreadsheet sees.
        text = _FLAT_CSV.replace(',Casey Cedar,Starter', ',,Starter')
        with pytest.raises(GridError, match="row 2: 'name' is required"):
            grid_from_csv_rows(_csv_rows(text))


class TestCsvRoundTrip:
    def test_round_trip_preserves_everything(self, grid_json_path):
        original = load_grid_json(grid_json_path)
        restored = grid_from_csv_rows(_csv_rows(grid_to_csv(original)))
        assert grid_to_dict(restored) == grid_to_dict(original)

    def test_free_text_date_survives_the_round_trip(self):
        grid = Grid(competition_name='M', sessions=[
            Session(number=1, date_text='Day 1 of 3',
                    officials=[Official(name='C', position='Timer')]),
        ])
        restored = grid_from_csv_rows(_csv_rows(grid_to_csv(grid)))
        assert restored.session(1).date_text == 'Day 1 of 3'


class TestLoadGridCsvDetectsShape:
    def test_reads_the_flat_csv(self, tmp_path):
        path = tmp_path / 'grid.csv'
        path.write_text(_FLAT_CSV, encoding='utf-8')
        assert load_grid_csv(path).competition_name == 'Autumn Opener 2026'

    def test_reads_a_published_sheet_export_saved_to_a_file(self, sheet_export_path):
        # Someone doing offline work saves the Sheet's CSV export and points
        # --grid-csv at it. It is not the flat CSV, and it should still work.
        grid = load_grid_csv(sheet_export_path)
        assert grid.competition_name == 'Autumn Opener 2026'
        assert [s.number for s in grid.sessions] == [1, 2]

    def test_empty_file_says_so(self, tmp_path):
        path = tmp_path / 'grid.csv'
        path.write_text('', encoding='utf-8')
        with pytest.raises(GridError, match="empty CSV"):
            load_grid_csv(path)

    def test_byte_order_mark_is_tolerated(self, tmp_path):
        # Sheets exports and Excel round-trips both carry a BOM.
        path = tmp_path / 'grid.csv'
        path.write_text('﻿' + _FLAT_CSV, encoding='utf-8')
        assert load_grid_csv(path).competition_name == 'Autumn Opener 2026'
