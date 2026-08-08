#!/usr/bin/env python3
"""Compatibility shim: `python eval_gen.py ...` still works.

The code moved into the installable ``src/deck_eval_gen/`` package so that
``officials-admin`` can depend on it as a library. This file stays because
existing docs, notes and muscle memory all say ``python eval_gen.py <sheet_url>``.
Prefer the installed entry point: ``deck-eval-gen <sheet_url>``.
"""
import sys
from pathlib import Path

# Work from a bare checkout too — before `pip install -e .` has been run there
# is no installed package to import.
_SRC = Path(__file__).resolve().parent / 'src'
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from deck_eval_gen.cli import main  # noqa: E402  (path set up above)

if __name__ == '__main__':
    raise SystemExit(main())
