"""Minimal pure-stdlib FITS BINTABLE reader for Kepler light-curve files.

Only what this demo needs: parse 80-character header cards, locate the first
BINTABLE extension, and extract scalar columns (TIME, PDCSAP_FLUX,
SAP_QUALITY) from big-endian fixed-width table rows. No third-party packages
(astropy would be the usual choice; it is deliberately avoided here so the
fetch tool runs anywhere with zero installation).
"""

from __future__ import annotations

import math
import re
import struct
from pathlib import Path

_BLOCK = 2880
_CARD = 80
_TYPE_SIZES = {"L": 1, "X": 0, "B": 1, "I": 2, "J": 4, "K": 8, "A": 1, "E": 4, "D": 8, "C": 8, "M": 16}
_TYPE_FMT = {"B": "B", "I": "h", "J": "i", "K": "q", "E": "f", "D": "d"}
_TFORM_RE = re.compile(r"^(\d*)([LXBIJKAEDCM])$")


class FitsFormatError(ValueError):
    """Raised when the file is not a supported FITS BINTABLE."""


def _read_header(fh) -> list[str]:
    cards: list[str] = []
    while True:
        block = fh.read(_BLOCK)
        if len(block) < _BLOCK:
            raise FitsFormatError("truncated FITS header")
        for i in range(0, _BLOCK, _CARD):
            card = block[i : i + _CARD].decode("ascii", "replace")
            cards.append(card)
            if card.startswith("END"):
                return cards


def _value(cards: list[str], key: str, default=None):
    prefix = key.ljust(8)[:8] + "= "
    for card in cards:
        if card.startswith(prefix):
            raw = card[10:].split("/")[0].strip()
            if raw.startswith("'"):
                return raw.strip("'").strip()
            if raw in ("T", "F"):
                return raw == "T"
            try:
                return int(raw)
            except ValueError:
                try:
                    return float(raw.replace("D", "E"))
                except ValueError:
                    return raw
    return default


def _skip_data(fh, cards: list[str]) -> None:
    naxis = int(_value(cards, "NAXIS", 0))
    if naxis == 0:  # NAXIS=0 means the HDU carries no data array at all
        return
    bitpix = abs(int(_value(cards, "BITPIX", 8)))
    size = bitpix // 8
    for axis in range(1, naxis + 1):
        size *= int(_value(cards, f"NAXIS{axis}", 0))
    padded = ((size + _BLOCK - 1) // _BLOCK) * _BLOCK
    fh.seek(padded, 1)


def read_light_curve(
    path: str | Path,
    time_col: str = "TIME",
    flux_col: str = "PDCSAP_FLUX",
    quality_col: str = "SAP_QUALITY",
) -> tuple[list[float], list[float], dict]:
    """Read a Kepler-style light-curve FITS file.

    Returns (times, fluxes, meta) keeping only rows with quality flag 0 and
    finite time/flux values.
    """
    times: list[float] = []
    fluxes: list[float] = []
    with Path(path).open("rb") as fh:
        _skip_data(fh, _read_header(fh))  # primary HDU (no data expected)
        cards = _read_header(fh)
        if str(_value(cards, "XTENSION", "")).upper() != "BINTABLE":
            raise FitsFormatError("first extension is not a BINTABLE")
        row_len = int(_value(cards, "NAXIS1"))
        n_rows = int(_value(cards, "NAXIS2"))
        n_fields = int(_value(cards, "TFIELDS"))

        offsets: dict[str, int] = {}
        offset = 0
        for idx in range(1, n_fields + 1):
            name = str(_value(cards, f"TTYPE{idx}", f"COL{idx}"))
            tform = str(_value(cards, f"TFORM{idx}", ""))
            match = _TFORM_RE.match(tform)
            if not match:
                raise FitsFormatError(f"unsupported TFORM{idx}={tform!r}")
            repeat = int(match.group(1) or "1")
            code = match.group(2)
            if code in _TYPE_FMT:
                offsets[name] = (offset, _TYPE_FMT[code], repeat)
            offset += repeat * _TYPE_SIZES[code]

        for col in (time_col, flux_col):
            if col not in offsets:
                raise FitsFormatError(f"column {col!r} not found in BINTABLE")
        table = fh.read(((row_len * n_rows + _BLOCK - 1) // _BLOCK) * _BLOCK)

    n_quality_rejected = 0
    for row in range(n_rows):
        base = row * row_len

        def cell(col: str):
            off, fmt, repeat = offsets[col]
            if repeat != 1:
                raise FitsFormatError(f"column {col!r} is not scalar")
            return struct.unpack_from(">" + fmt, table, base + off)[0]

        t = float(cell(time_col))
        f = float(cell(flux_col))
        q = int(cell(quality_col)) if quality_col in offsets else 0
        if q != 0:
            n_quality_rejected += 1
            continue
        if math.isfinite(t) and math.isfinite(f):
            times.append(t)
            fluxes.append(f)

    meta = {
        "rows_total": n_rows,
        "rows_kept": len(times),
        "rows_quality_rejected": n_quality_rejected,
        "time_col": time_col,
        "flux_col": flux_col,
        "quality_col": quality_col if quality_col in offsets else None,
    }
    return times, fluxes, meta
