"""Command-line entry point.

Three ways in, all producing the same grid model:

    deck-eval-gen <sheet_url>              published Google Sheet (needs network)
    deck-eval-gen --grid-json grid.json    a grid
    deck-eval-gen --grid-csv grid.csv      a grid as flat CSV

See ``docs/grid-schema.md`` for the schema.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deck_eval_gen.grid import Grid, GridError, load_grid_csv, load_grid_json
from deck_eval_gen.pdf import default_template, fill_session_pdf
from deck_eval_gen.sheet import is_incomplete_name, load_grid_url


def resolve_incomplete_names(grid: Grid) -> None:
    """Prompt for a full name for any official whose name looks truncated.

    Grid cells get typed in a hurry, so a published Sheet often carries "Zoe"
    or "Harsh G" where the evaluation form wants a full name. Each distinct
    incomplete name is asked once and the answer applied everywhere.

    Only worth doing for Sheet input: a grid comes from a system that
    knows officials' full names. The caller decides.
    """
    corrections: dict[str, str] = {}
    for session in grid.sessions:
        for off in session.officials:
            if not is_incomplete_name(off.name):
                continue
            if off.name not in corrections:
                answer = input(
                    f"  '{off.name}' ({off.position}) looks incomplete."
                    f" Full name [{off.name}]: "
                ).strip()
                corrections[off.name] = answer or off.name
            off.name = corrections[off.name]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='deck-eval-gen',
        description=(
            'Generate On-Deck Evaluation PDFs from a meet officials grid.\n'
            'Officials flagged for a deck evaluation are written into the output PDF(s).\n'
            'Takes a published Google Sheet, or a grid as JSON or CSV.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'url',
        nargs='?',
        help='URL of the published officials grid (shortener or direct Google Sheets URL)',
    )
    source = parser.add_argument_group('input (give exactly one)')
    source.add_argument(
        '--grid-json',
        metavar='PATH',
        help="grid as JSON; '-' reads stdin",
    )
    source.add_argument(
        '--grid-csv',
        metavar='PATH',
        help=(
            "grid as flat CSV; '-' reads stdin. Also accepts a "
            "published-sheet CSV export saved to a file"
        ),
    )
    parser.add_argument(
        '--session', '-s',
        type=int,
        metavar='N',
        help='generate only session N; default: every session with flagged officials',
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='.',
        metavar='DIR',
        help='directory for output PDFs (default: current directory)',
    )
    parser.add_argument(
        '--template', '-t',
        default=None,
        metavar='PATH',
        help='blank eval form PDF (default: the one shipped with this package)',
    )
    parser.add_argument(
        '--host-club',
        default='',
        metavar='NAME',
        help='host club; used for officials whose club the grid does not note',
    )
    parser.add_argument(
        '--coc',
        default='',
        metavar='NAME',
        help='Chief of Officials Committee name/contact for the COC field',
    )
    parser.add_argument(
        '--no-prompt',
        action='store_true',
        help='never prompt for truncated names; use them as the grid has them',
    )
    return parser


def _load(args: argparse.Namespace) -> tuple[Grid, bool]:
    """Return the grid and whether it came from a published Sheet."""
    if args.grid_json:
        return load_grid_json(args.grid_json), False
    if args.grid_csv:
        return load_grid_csv(args.grid_csv), False
    print("Fetching officials grid ...")
    return load_grid_url(args.url), True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if sum(map(bool, (args.url, args.grid_json, args.grid_csv))) != 1:
        print(
            "Error: give exactly one input — a sheet URL, --grid-json, or --grid-csv.",
            file=sys.stderr,
        )
        return 2

    template_path = Path(args.template) if args.template else default_template()
    if not template_path.exists():
        print(f"Error: template PDF not found at {template_path}", file=sys.stderr)
        return 1

    try:
        grid, from_sheet = _load(args)
    except GridError as exc:
        print(f"Error reading grid: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:                                # network, HTTP, bad URL
        print(f"Error fetching sheet: {exc}", file=sys.stderr)
        return 1

    grid = grid.with_defaults(host_club=args.host_club, coc=args.coc)

    total_flagged = sum(len(s.deck_eval_officials) for s in grid.sessions)
    print(f"  Competition : {grid.competition_name}")
    print(f"  Coordinator : {grid.competition_coordinator}")
    print(f"  Sessions    : {len(grid.sessions)} found")
    print(f"  DE officials: {total_flagged} across {len(grid.deck_eval_sessions)} session(s)")

    # Prompting only makes sense for a Sheet, and only with someone there to
    # answer — a piped or CI invocation must not block on stdin.
    if from_sheet and not args.no_prompt and sys.stdin.isatty():
        resolve_incomplete_names(grid)

    if args.session is not None:
        try:
            targets = [grid.session(args.session)]
        except GridError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if not targets[0].deck_eval_officials:
            print(f"Session {args.session} has no officials flagged for evaluation"
                  " - nothing to generate.")
            return 0
    else:
        targets = grid.deck_eval_sessions
        if not targets:
            print("No sessions with officials flagged for evaluation.")
            return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for session in targets:
        out_path = output_dir / f"session_{session.number}_evals.pdf"
        count = len(session.deck_eval_officials)
        print(f"  Session {session.number}: {count} official(s) -> {out_path}")
        fill_session_pdf(template_path, out_path, grid, session)

    print("Done.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
