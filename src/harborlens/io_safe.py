"""Bounded NOAA-style CSV readers for locally supplied research data.

Protect against oversized files and ZIP expansion bombs before consuming data.
This is not a security sandbox for public upload services.
"""
from __future__ import annotations

import csv
import gzip
import io
import zipfile
from contextlib import contextmanager
from pathlib import Path

MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_EXPANSION_RATIO = 100
MAX_CSV_FIELD_CHARS = 1_048_576


class AISInputError(ValueError):
    """Input does not meet the research CLI ingestion safety contract."""


class LimitedReader:
    """A binary reader that refuses to emit more bytes than its cap."""

    def __init__(self, stream, cap: int):
        self.stream = stream
        self.cap = cap
        self.total = 0

    def readable(self):
        return True

    def read(self, size=-1):
        if size is None or size < 0:
            size = self.cap - self.total + 1
        data = self.stream.read(min(size, self.cap - self.total + 1))
        self.total += len(data)
        if self.total > self.cap:
            raise AISInputError("Decompressed AIS payload exceeds maximum size")
        return data

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


@contextmanager
def _open_text_stream(path: Path):
    path = Path(path)
    try:
        compressed_bytes = path.stat().st_size
    except OSError as exc:
        raise AISInputError("Input file cannot be accessed") from exc
    if compressed_bytes > MAX_COMPRESSED_BYTES:
        raise AISInputError("Compressed/source AIS file exceeds maximum size")
    if not compressed_bytes:
        raise AISInputError("AIS file is empty")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("rb") as raw:
            with io.TextIOWrapper(io.BufferedReader(LimitedReader(raw, MAX_UNCOMPRESSED_BYTES)), encoding="utf-8-sig", newline="") as text:
                yield text
    elif suffix == ".gz":
        with gzip.open(path, "rb") as decompressed:
            with io.TextIOWrapper(io.BufferedReader(LimitedReader(decompressed, MAX_UNCOMPRESSED_BYTES)), encoding="utf-8-sig", newline="") as text:
                yield text
    elif suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1 or not members[0].filename.lower().endswith(".csv"):
                raise AISInputError("ZIP must contain exactly one CSV file")
            member = members[0]
            if member.flag_bits & 0x1:
                raise AISInputError("Encrypted ZIP archives are unsupported")
            if member.file_size > MAX_UNCOMPRESSED_BYTES:
                raise AISInputError("ZIP expanded content exceeds maximum size")
            if member.file_size > MAX_ZIP_EXPANSION_RATIO * max(1, member.compress_size):
                raise AISInputError("ZIP compression ratio exceeds safety limit")
            with archive.open(member, "r") as decompressed:
                with io.TextIOWrapper(io.BufferedReader(LimitedReader(decompressed, MAX_UNCOMPRESSED_BYTES)), encoding="utf-8-sig", newline="") as text:
                    yield text
    elif suffix == ".zst":
        try:
            import zstandard
        except ImportError as exc:
            raise AISInputError("Install the optional 'zstandard' dependency for .zst files") from exc
        with path.open("rb") as raw:
            with zstandard.ZstdDecompressor().stream_reader(raw) as decompressed:
                with io.TextIOWrapper(io.BufferedReader(LimitedReader(decompressed, MAX_UNCOMPRESSED_BYTES)), encoding="utf-8-sig", newline="") as text:
                    yield text
    else:
        raise AISInputError("Supported input formats: .csv, .gz, .zip, .zst")


def stream_rows(path: Path):
    """Yield CSV rows with a common bounded-decompression safety contract."""
    original_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_CSV_FIELD_CHARS)
        with _open_text_stream(path) as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise AISInputError("CSV header is missing")
            if len(reader.fieldnames) > 128:
                raise AISInputError("CSV has too many columns")
            if any(not field or not field.strip() for field in reader.fieldnames):
                raise AISInputError("CSV header contains an empty column name")
            for row in reader:
                if None in row:
                    raise AISInputError(f"CSV row {reader.line_num} has more values than header")
                yield row
    except (UnicodeError, csv.Error, EOFError, zipfile.BadZipFile, OSError) as exc:
        raise AISInputError(f"Invalid or corrupted AIS input: {type(exc).__name__}") from exc
    finally:
        csv.field_size_limit(original_limit)
