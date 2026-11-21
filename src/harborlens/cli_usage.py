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

    The message is ``str(exc)`` with no program prefix. Without ``debug``,
    ``parser.error`` prints the usage line and ``{prog}: error: {message}``.
    With ``debug``, the same bytes are written with the public API, then the
    traceback, and the process still exits 2.
    """
    message = str(exc)
    if not debug:
        parser.error(message)
    parser.print_usage(sys.stderr)
    sys.stderr.write(f"{parser.prog}: error: {message}\n")
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    raise SystemExit(2)
