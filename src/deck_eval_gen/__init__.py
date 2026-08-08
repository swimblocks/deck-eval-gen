"""deck-eval-gen: printable on-deck evaluation forms from a meet officials grid.

The library contract is the *grid document* — see :mod:`deck_eval_gen.grid` and
``docs/grid-schema.md``. A caller that already holds the grid (``officials-admin``
serving ``/meets/{id}/grid.json``) builds the model and renders straight from it,
with no Google account and no network:

    from deck_eval_gen import fill_session_pdf, grid_from_dict

    grid = grid_from_dict(payload)
    for session in grid.deck_eval_sessions:
        fill_session_pdf(template, out_dir / f"session_{session.number}.pdf", grid, session)

Reading a published Google Sheet is one adapter onto the same model, in
:mod:`deck_eval_gen.sheet`, and the only path that needs ``requests``.
"""
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
from deck_eval_gen.pdf import ROWS_PER_PAGE, default_template, fill_session_pdf

__version__ = '0.1.0'

__all__ = [
    'ROWS_PER_PAGE',
    'SCHEMA_VERSION',
    'Grid',
    'GridError',
    'Official',
    'Session',
    '__version__',
    'default_template',
    'fill_session_pdf',
    'grid_from_csv_rows',
    'grid_from_dict',
    'grid_to_csv',
    'grid_to_dict',
    'load_grid_csv',
    'load_grid_json',
]
