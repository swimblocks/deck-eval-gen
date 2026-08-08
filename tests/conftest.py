"""Shared fixtures. Nothing here touches the network or a Google account."""
import csv
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def sheet_export_path() -> Path:
    """A synthetic published-Sheet CSV export, in the ROW grid layout."""
    return FIXTURES / 'sheet_export.csv'


@pytest.fixture
def sheet_export_rows(sheet_export_path) -> list[list[str]]:
    with sheet_export_path.open(encoding='utf-8-sig', newline='') as fh:
        return list(csv.reader(fh))


@pytest.fixture
def grid_json_path() -> Path:
    """The same grid, hand-written as a grid document."""
    return FIXTURES / 'grid.json'
