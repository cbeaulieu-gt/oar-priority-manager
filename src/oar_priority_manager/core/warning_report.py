"""Warning-aggregation helpers for the Scan Issues log pane (issue #51).

Structures each submod's warning strings into ``WarningEntry`` rows with
parsed file paths, error categories, and line numbers — the data contract
consumed by ``ui.scan_issues_pane.ScanIssuesPane``.

The source of truth is still ``SubMod.warnings: list[str]`` — this module
only *derives* a display-time view from those strings; it never mutates
any SubMod.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from oar_priority_manager.core.models import SubMod

# ---------------------------------------------------------------------------
# Parsing regexes — one per known warning producer in parser.py / scanner.py.
# Kept in order of specificity. First match wins.
# ---------------------------------------------------------------------------

_JSON_PARSE_RE = re.compile(
    r"^JSON parse error in (?P<path>.+?):\s+(?P<detail>.+)$"
)
_LINE_COLUMN_RE = re.compile(r"line (?P<line>\d+) column \d+")

_FILE_NOT_FOUND_RE = re.compile(r"^File not found:\s+(?P<path>.+)$")
_CANNOT_READ_RE = re.compile(r"^Cannot read (?P<path>.+?):\s+.*$")
_EMPTY_FILE_RE = re.compile(r"^Empty file:\s+(?P<path>.+)$")
_EXPECTED_OBJECT_RE = re.compile(
    r"^Expected JSON object in (?P<path>.+?), got \w+$"
)
_PRIORITY_NOT_INT_RE = re.compile(
    r"^Priority is not an integer in (?P<path>.+?):\s+.*$"
)


@dataclass(frozen=True)
class WarningEntry:
    """Structured view of one warning for the log pane.

    Attributes:
        submod: The SubMod that produced the warning.
        file_path: Absolute path to the offending file.
        error_type: Short category — one of ``"JSON parse error"``,
            ``"Missing field"``, ``"Type error"``, ``"Read error"``,
            or ``"Other"``.
        line: 1-based line number when parseable from the message,
            otherwise ``None``.
        message: The original warning string, unmodified.
        severity: Reserved for future use. Always ``"warning"`` in MVP.
    """

    submod: SubMod
    file_path: Path
    error_type: str
    line: int | None
    message: str
    severity: str = "warning"


def _parse_one(submod: SubMod, message: str) -> WarningEntry:
    """Parse a single warning string into a WarningEntry.

    Args:
        submod: The owning submod — used both to fill in the ``submod``
            field and as the fallback file_path when the message does
            not embed one.
        message: The raw warning string produced by parser/scanner.

    Returns:
        A WarningEntry with file_path, error_type, and line best-effort
        extracted. Falls back to error_type="Other" and
        file_path=submod.config_path for unknown shapes.
    """
    if m := _JSON_PARSE_RE.match(message):
        path = Path(m.group("path"))
        line: int | None = None
        if ln := _LINE_COLUMN_RE.search(m.group("detail")):
            line = int(ln.group("line"))
        return WarningEntry(
            submod=submod,
            file_path=path,
            error_type="JSON parse error",
            line=line,
            message=message,
        )

    for regex, etype in (
        (_FILE_NOT_FOUND_RE, "Read error"),
        (_CANNOT_READ_RE, "Read error"),
        (_EMPTY_FILE_RE, "Read error"),
        (_EXPECTED_OBJECT_RE, "Type error"),
        (_PRIORITY_NOT_INT_RE, "Type error"),
    ):
        if m := regex.match(message):
            return WarningEntry(
                submod=submod,
                file_path=Path(m.group("path")),
                error_type=etype,
                line=None,
                message=message,
            )

    return WarningEntry(
        submod=submod,
        file_path=submod.config_path,
        error_type="Other",
        line=None,
        message=message,
    )


def collect_warning_entries(submods: Iterable[SubMod]) -> list[WarningEntry]:
    """Flatten every submod's warnings list into a sorted list of WarningEntry.

    See module docstring for parsing rules. Sort key is
    ``(submod.display_path, str(file_path), line or 0)`` so the log pane
    shows warnings grouped by submod, then by file, then by line number.

    Args:
        submods: Iterable of SubMod records, typically ``self._submods`` on
            MainWindow.

    Returns:
        A new list of WarningEntry. Empty when no submod has warnings.
    """
    entries: list[WarningEntry] = []
    for sm in submods:
        for msg in sm.warnings:
            entries.append(_parse_one(sm, msg))
    entries.sort(
        key=lambda e: (e.submod.display_path, str(e.file_path), e.line or 0)
    )
    return entries
