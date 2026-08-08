"""Tests for the CLI: input selection, and the interactive name prompt."""
from unittest.mock import patch

from deck_eval_gen.cli import build_parser, main, resolve_incomplete_names
from deck_eval_gen.grid import Grid, Official, Session


def _grid(*names: str) -> Grid:
    return Grid(competition_name='M', sessions=[
        Session(number=1, officials=[Official(name=n, position='Timer') for n in names]),
    ])


# ---------------------------------------------------------------------------
# resolve_incomplete_names
# ---------------------------------------------------------------------------

class TestResolveIncompleteNames:
    def test_complete_name_not_prompted(self):
        grid = _grid('Casey Cedar')
        with patch('builtins.input') as mock_input:
            resolve_incomplete_names(grid)
            mock_input.assert_not_called()
        assert grid.session(1).officials[0].name == 'Casey Cedar'

    def test_incomplete_name_prompted_and_replaced(self):
        grid = _grid('Riley')
        with patch('builtins.input', return_value='Noor Nettle'):
            resolve_incomplete_names(grid)
        assert grid.session(1).officials[0].name == 'Noor Nettle'

    def test_empty_input_keeps_original(self):
        grid = _grid('Riley')
        with patch('builtins.input', return_value=''):
            resolve_incomplete_names(grid)
        assert grid.session(1).officials[0].name == 'Riley'

    def test_same_name_prompted_only_once_across_sessions(self):
        grid = Grid(competition_name='M', sessions=[
            Session(number=1, officials=[Official(name='Zoe', position='Timer')]),
            Session(number=2, officials=[Official(name='Zoe', position='Timer')]),
        ])
        with patch('builtins.input', return_value='Noor Nettle') as mock_input:
            resolve_incomplete_names(grid)
            assert mock_input.call_count == 1
        assert grid.session(1).officials[0].name == 'Noor Nettle'
        assert grid.session(2).officials[0].name == 'Noor Nettle'

    def test_different_incomplete_names_each_prompted(self):
        grid = _grid('Riley', 'Robin M')
        with patch('builtins.input', side_effect=['Noor Nettle', 'Oakley Oak']) as mock_input:
            resolve_incomplete_names(grid)
            assert mock_input.call_count == 2
        assert [o.name for o in grid.session(1).officials] == ['Noor Nettle', 'Oakley Oak']


# ---------------------------------------------------------------------------
# Input selection
# ---------------------------------------------------------------------------

class TestInputSelection:
    def test_no_input_is_refused(self, capsys):
        assert main([]) == 2
        assert 'exactly one input' in capsys.readouterr().err

    def test_two_inputs_are_refused(self, grid_json_path, capsys):
        # Would otherwise silently pick one and ignore the other.
        assert main(['https://example.test/pub', '--grid-json', str(grid_json_path)]) == 2
        assert 'exactly one input' in capsys.readouterr().err

    def test_json_input_needs_no_network(self, grid_json_path, tmp_path):
        # No requests mock anywhere: reaching the network would raise.
        assert main([
            '--grid-json', str(grid_json_path),
            '--output-dir', str(tmp_path),
            '--host-club', 'Centennial',
        ]) == 0
        assert {p.name for p in tmp_path.glob('*.pdf')} == {
            'session_1_evals.pdf', 'session_2_evals.pdf',
        }

    def test_csv_input_needs_no_network(self, sheet_export_path, tmp_path):
        assert main([
            '--grid-csv', str(sheet_export_path),
            '--output-dir', str(tmp_path),
        ]) == 0
        assert (tmp_path / 'session_1_evals.pdf').exists()

    def test_single_session_selection(self, grid_json_path, tmp_path):
        assert main([
            '--grid-json', str(grid_json_path),
            '--session', '2',
            '--output-dir', str(tmp_path),
        ]) == 0
        assert {p.name for p in tmp_path.glob('*.pdf')} == {'session_2_evals.pdf'}

    def test_unknown_session_is_an_error(self, grid_json_path, tmp_path, capsys):
        assert main([
            '--grid-json', str(grid_json_path),
            '--session', '9',
            '--output-dir', str(tmp_path),
        ]) == 1
        assert 'No session 9' in capsys.readouterr().err

    def test_malformed_grid_reports_the_problem(self, tmp_path):
        path = tmp_path / 'grid.json'
        path.write_text('{"schema_version": 1}', encoding='utf-8')
        assert main(['--grid-json', str(path), '--output-dir', str(tmp_path)]) == 1

    def test_missing_template_is_reported(self, grid_json_path, tmp_path, capsys):
        assert main([
            '--grid-json', str(grid_json_path),
            '--template', str(tmp_path / 'absent.pdf'),
        ]) == 1
        assert 'template PDF not found' in capsys.readouterr().err

    def test_structured_input_never_prompts(self, grid_json_path, tmp_path):
        # A grid document comes from a system that knows full names, and a
        # library or CI caller has nobody at a keyboard to answer.
        with patch('builtins.input', side_effect=AssertionError('must not prompt')):
            assert main([
                '--grid-json', str(grid_json_path),
                '--output-dir', str(tmp_path),
            ]) == 0


class TestParser:
    def test_url_is_optional(self):
        assert build_parser().parse_args(['--grid-json', 'g.json']).url is None

    def test_url_is_still_positional(self):
        args = build_parser().parse_args(['https://example.test/pub'])
        assert args.url == 'https://example.test/pub'
