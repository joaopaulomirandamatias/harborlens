"""Shared argparse pieces for HarborLens console scripts.

Expected domain errors exit 2 through ``ArgumentParser.error``. ``--debug``
prints the traceback after that line and still exits 2. ``KeyboardInterrupt``
is never caught here.
"""
from __future__ import annotations

import sys
import traceback

from harborlens import __version__


def add_version_argument(parser):
    """``-V`` / ``--version`` prints ``{prog} {package_version}`` and exits 0."""
    parser.add_argument(
        "-V", "--version", action="version", version="%(prog)s " + __version__,
    )


def add_debug_argument(parser):
    parser.add_argument(
        "--debug", action="store_true",
        help="print a traceback after a domain error (still exit 2)",
    )


def report_domain_error(parser, exc, debug=False):
    """Exit 2 with argparse's usage line and one error line.

    The message is ``str(exc)`` with no program prefix; ``parser.error`` adds
    ``{prog}: error:``. With ``debug``, the traceback is printed after that
    line. The process still exits 2.
    """
    if not debug:
        parser.error(str(exc))
    original_exit = parser.exit

    def _exit(status=0, message=None):
        if message:
            parser._print_message(message, sys.stderr)
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        raise SystemExit(status)

    parser.exit = _exit
    try:
        parser.error(str(exc))
    finally:
        parser.exit = original_exit
