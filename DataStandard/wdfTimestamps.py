"""
Absolute acquisition times (and a few other header facts) straight out of a ``.wdf``.

Why this module exists
----------------------
``renishawWiRE`` reads the ORGN ``Time`` channel and then throws the epoch away
(``wdfReader.py``, ``_parse_orgin_list``)::

    if self.origin_list_header[i][1] == DataType.Time:
        array = numpy.array([...int64...]) / 1e7
        array = array - array[0]          # <-- absolute reference lost

So ``reader.origin_list_header`` -- and therefore ``/coordinates/Time`` in every
``_unified.h5`` written so far -- holds *relative seconds within one file*, always
starting at 0.0. That is fine for one acquisition and useless for ordering spectra
across the dozens of files a session produces.

The raw values are Windows FILETIME: unsigned 64-bit counts of 100-nanosecond ticks
since 1601-01-01 00:00:00 UTC. This module re-reads them without the subtraction, and
also picks up two ``uint64`` FILETIMEs in the WDF1 header (``time_start`` at 0x88,
``time_end`` at 0x90) that ``renishawWiRE`` skips entirely -- it jumps from
``measurement_type`` at 0x88 straight to ``Offsets.spectral_info = 0x98``.

Everything here is pure ``struct``/``numpy`` parsing of the file. Nothing imports
``renishawWiRE``, which matters because ``WDFReader.__init__`` raises
``ValueError("WMAP Xpos is not same as in ORGN!")`` on a good fraction of real files --
these functions still work on those.

Verified against ``20260805_CART_SCRNATrial1/Sample1_20x_1s_100p_.wdf``: header start
2026-08-05 22:23:00.016 UTC, end 22:24:17.857 UTC, per-spectrum ORGN times
22:23:01.32 -> 22:24:17.82 with 1.44-1.73 s spacing, and a filesystem mtime of
22:24:16 UTC. All three agree.
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

__all__ = [
    "FILETIME_EPOCH",
    "FILETIME_EPOCH_US",
    "TICKS_PER_SECOND",
    "filetime_ticks_to_unix",
    "filetime_ticks_to_datetime64",
    "filetime_ticks_to_datetime",
    "read_block_table",
    "read_wdf_header",
    "read_wdf_origins",
    "read_wdf_spectrum_times",
    "read_wdf_map_geometry",
    "summarize_wdf",
]

# ----------------------------------------------------------------------
# FILETIME
# ----------------------------------------------------------------------

FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
#: microseconds between the FILETIME epoch (1601-01-01) and the Unix epoch (1970-01-01)
FILETIME_EPOCH_US = 11_644_473_600_000_000
TICKS_PER_SECOND = 10_000_000  # 100 ns ticks


def filetime_ticks_to_unix(ticks) -> np.ndarray:
    """
    FILETIME ticks -> Unix epoch seconds (UTC), float64.

    Accepts a scalar or any array-like. Ticks are cast through ``uint64`` first: the
    values are ~1.34e17, which overflows int32 and loses sub-second precision in
    float32, so the intermediate dtype is not optional.
    """
    t = np.asarray(ticks, dtype=np.uint64)
    # Convert in integer microseconds before going to float, so we keep full
    # microsecond resolution instead of dividing a 1.3e17 float by 1e7.
    micros = t // np.uint64(10)
    return (micros.astype(np.float64) - FILETIME_EPOCH_US) / 1e6


def filetime_ticks_to_datetime64(ticks) -> np.ndarray:
    """FILETIME ticks -> ``datetime64[us]`` (UTC, tz-naive as numpy requires)."""
    t = np.asarray(ticks, dtype=np.uint64)
    micros = (t // np.uint64(10)).astype(np.int64)
    return np.datetime64("1601-01-01T00:00:00", "us") + micros.astype("timedelta64[us]")


def filetime_ticks_to_datetime(tick: int) -> datetime:
    """A single FILETIME tick -> tz-aware ``datetime`` in UTC."""
    return FILETIME_EPOCH + timedelta(microseconds=int(tick) / 10)


# ----------------------------------------------------------------------
# Block table
# ----------------------------------------------------------------------

_BLOCK_HEADER = struct.Struct("<4sIQ")  # id, uid, length (length includes the 16 bytes)
_HEADER_SIZE = 0x200


def read_block_table(path: Union[str, Path]) -> Dict[str, Tuple[int, int, int]]:
    """
    Walk the top-level block chain.

    Returns ``{block_id: (uid, offset, length)}`` where ``offset`` is the start of the
    16-byte block header, so the payload begins at ``offset + 0x10``. Later blocks with
    a duplicate id win, matching ``renishawWiRE.block_info``.
    """
    path = Path(path)
    size = path.stat().st_size
    blocks: Dict[str, Tuple[int, int, int]] = {}
    with open(path, "rb") as fh:
        pos = 0
        while pos + _BLOCK_HEADER.size <= size:
            fh.seek(pos)
            raw = fh.read(_BLOCK_HEADER.size)
            if len(raw) < _BLOCK_HEADER.size:
                break
            block_id, uid, length = _BLOCK_HEADER.unpack(raw)
            if length < _BLOCK_HEADER.size:
                # A zero/garbage length would spin forever.
                break
            name = block_id.decode("ascii", "ignore").strip("\x00").strip()
            blocks[name] = (uid, pos, length)
            pos += length
    return blocks


# ----------------------------------------------------------------------
# WDF1 header
# ----------------------------------------------------------------------

# Offsets inside the 512-byte WDF1 block. The ones renishawWiRE exposes come from
# renishawWiRE.types.Offsets; time_start/time_end are the 16-byte gap it skips.
_OFF_MEASUREMENT_INFO = 0x3C
_OFF_TIME_START = 0x88
_OFF_TIME_END = 0x90
_OFF_SPECTRAL_INFO = 0x98
_OFF_FILE_INFO = 0xD0
_OFF_USR_NAME = 0xF0

_SCAN_TYPES = {
    0: "Unspecified", 1: "Static", 2: "Continuous", 3: "StepRepeat",
    4: "FilterScan", 5: "FilterImage", 6: "StreamLine", 7: "StreamLineHR",
    8: "Point",
}
_MEASUREMENT_TYPES = {0: "Unspecified", 1: "Single", 2: "Series", 3: "Mapping"}


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf8", "ignore").strip()


def read_wdf_header(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Parse the WDF1 block.

    The keys ``time_start_utc`` / ``time_end_utc`` are the point of this function --
    absolute tz-aware UTC datetimes for when the acquisition began and ended, which no
    other reader in this codebase exposes. ``*_unix`` variants are the same instants as
    epoch seconds.

    ``count`` is how many spectra were actually collected and ``capacity`` how many were
    planned; they differ on aborted acquisitions, and **every array must be truncated to
    ``count``** (``capacity`` rows exist on disk but the tail is uninitialised).
    """
    path = Path(path)
    with open(path, "rb") as fh:
        head = fh.read(_HEADER_SIZE)
    if len(head) < _HEADER_SIZE:
        raise ValueError(f"{path.name}: shorter than a WDF1 header ({len(head)} bytes)")
    signature = head[:4]
    if signature != b"WDF1":
        raise ValueError(f"{path.name}: not a WDF file (signature {signature!r})")

    (npoints,) = struct.unpack_from("<I", head, _OFF_MEASUREMENT_INFO)
    capacity, count = struct.unpack_from("<qq", head, _OFF_MEASUREMENT_INFO + 4)
    accumulations, ylist_length, xlist_length, n_origins = struct.unpack_from(
        "<IIII", head, _OFF_MEASUREMENT_INFO + 20
    )
    app_name = _cstr(head[0x60:0x78])
    app_version = struct.unpack_from("<4H", head, 0x78)
    (scan_type,) = struct.unpack_from("<I", head, 0x80)
    (measurement_type,) = struct.unpack_from("<I", head, 0x84)
    time_start, time_end = struct.unpack_from("<QQ", head, _OFF_TIME_START)
    (spectral_unit,) = struct.unpack_from("<I", head, _OFF_SPECTRAL_INFO)
    (laser_wavenumber,) = struct.unpack_from("<f", head, _OFF_SPECTRAL_INFO + 4)
    username = _cstr(head[_OFF_FILE_INFO:_OFF_USR_NAME])
    title = _cstr(head[_OFF_USR_NAME:_HEADER_SIZE])

    return {
        "path": str(path),
        "filename": path.name,
        "points_per_spectrum": int(npoints),
        "capacity": int(capacity),
        "count": int(count),
        "is_completed": int(count) == int(capacity),
        "accumulations": int(accumulations),
        "ylist_length": int(ylist_length),
        "xlist_length": int(xlist_length),
        "n_origins": int(n_origins),
        "application_name": app_name,
        "application_version": ".".join(str(v) for v in app_version),
        "scan_type": _SCAN_TYPES.get(scan_type, f"Unknown({scan_type})"),
        "measurement_type": _MEASUREMENT_TYPES.get(
            measurement_type, f"Unknown({measurement_type})"
        ),
        "spectral_unit": int(spectral_unit),
        "laser_wavenumber_cm1": float(laser_wavenumber),
        "laser_wavelength_nm": (
            1e7 / float(laser_wavenumber) if laser_wavenumber else None
        ),
        "username": username,
        "title": title,
        "time_start_ticks": int(time_start),
        "time_end_ticks": int(time_end),
        "time_start_utc": filetime_ticks_to_datetime(time_start),
        "time_end_utc": filetime_ticks_to_datetime(time_end),
        "time_start_unix": float(filetime_ticks_to_unix(time_start)),
        "time_end_unix": float(filetime_ticks_to_unix(time_end)),
        "duration_seconds": (int(time_end) - int(time_start)) / TICKS_PER_SECOND,
    }


# ----------------------------------------------------------------------
# ORGN
# ----------------------------------------------------------------------

# DataType enum values used by the ORGN rows (renishawWiRE.types.DataType).
_DATA_TYPES = {
    0: "Arbitrary", 1: "Frequency", 2: "Intensity",
    3: "Spatial_X", 4: "Spatial_Y", 5: "Spatial_Z",
    6: "Spatial_R", 7: "Spatial_Theta", 8: "Spatial_Phi",
    9: "Temperature", 10: "Pressure", 11: "Time", 12: "Derived",
    13: "Polarization", 14: "FocusTrack", 15: "RampRate",
    16: "Checksum", 17: "Flags", 18: "ElapsedTime",
    19: "Frequency2", 20: "Mp_Well_Spatial_X", 21: "Mp_Well_Spatial_Y",
    22: "Mp_LocationIndex", 23: "Mp_WellReference", 24: "PAFZActual",
    25: "PAFZError", 26: "PAFSignalUsed", 27: "ExposureTime",
    28: "ExternalSignal", 29: "Custom",
}
_UNIT_TYPES = {
    0: "Arbitrary", 1: "RamanShift", 2: "Wavenumber", 3: "Nanometre",
    4: "ElectronVolt", 5: "Micron", 6: "Counts", 7: "Electrons",
    8: "Millimetres", 9: "Metres", 10: "Kelvin", 11: "Pascal",
    12: "Seconds", 13: "Milliseconds", 14: "Hours", 15: "Days",
    16: "Pixels", 17: "Intensity", 18: "RelativeIntensity",
    19: "Degrees", 20: "Radians", 21: "Celsius", 22: "Fahrenheit",
    23: "KelvinPerMinute", 24: "FileTime", 25: "Microseconds",
}

_ORGN_INFO_OFFSET = 0x14      # first row starts here, relative to the block start
_ORGN_ROW_PREAMBLE = 0x18     # int32 type | int32 unit | char[16] annotation


def read_wdf_origins(
    path: Union[str, Path], header: Optional[Dict[str, Any]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Read every ORGN channel, keeping ``Time`` as **raw FILETIME ticks**.

    Returns ``{name: {'data': array, 'unit': str, 'annotation': str,
    'is_alt_axis': bool, 'datatype': int}}``, with arrays truncated to ``count``.

    ``Time`` gets two entries: ``ticks`` (uint64, as stored) and ``data`` (Unix epoch
    seconds, float64). Every other channel is float64.

    Two details that are easy to get wrong and produce silent garbage:

    * the row stride is ``0x18 + 8 * capacity`` -- **capacity**, not ``count``, so the
      stride must be computed from the header even when fewer spectra were collected;
    * the type word must be read **unsigned**. Its top bit is an "alternate axis" flag,
      so ``Spatial_X`` rows have it set; reading the word as int32 and masking with
      ``~(1 << 31)`` (as ``renishawWiRE`` does) yields ``-4294967293`` instead of 3.
    """
    path = Path(path)
    header = header or read_wdf_header(path)
    blocks = read_block_table(path)
    if "ORGN" not in blocks:
        return {}

    _uid, offset, _length = blocks["ORGN"]
    count = header["count"]
    capacity = header["capacity"]
    n_origins = header["n_origins"]
    stride = _ORGN_ROW_PREAMBLE + 8 * capacity

    out: Dict[str, Dict[str, Any]] = {}
    with open(path, "rb") as fh:
        for i in range(n_origins):
            fh.seek(offset + _ORGN_INFO_OFFSET + i * stride)
            preamble = fh.read(_ORGN_ROW_PREAMBLE)
            if len(preamble) < _ORGN_ROW_PREAMBLE:
                break
            type_word, unit_word = struct.unpack_from("<II", preamble, 0)
            annotation = _cstr(preamble[8:0x18])
            datatype = type_word & 0x7FFF_FFFF
            is_alt_axis = bool(type_word >> 31)
            name = _DATA_TYPES.get(datatype, f"Unknown_{datatype}")
            unit = _UNIT_TYPES.get(unit_word, f"Unknown({unit_word})")

            payload = fh.read(8 * count)
            if len(payload) < 8 * count:
                break

            entry: Dict[str, Any] = {
                "unit": unit,
                "annotation": annotation,
                "is_alt_axis": is_alt_axis,
                "datatype": datatype,
            }
            if datatype == 11:  # Time
                ticks = np.frombuffer(payload, dtype="<u8", count=count).copy()
                entry["ticks"] = ticks
                entry["data"] = filetime_ticks_to_unix(ticks)
                entry["datetime64"] = filetime_ticks_to_datetime64(ticks)
            else:
                entry["data"] = np.frombuffer(
                    payload, dtype="<f8", count=count
                ).copy()
            out[name] = entry
    return out


def read_wdf_spectrum_times(
    path: Union[str, Path], header: Optional[Dict[str, Any]] = None
) -> Optional[np.ndarray]:
    """
    Per-spectrum absolute acquisition times as Unix epoch seconds (UTC), float64.

    Shape ``(count,)``. Returns ``None`` when the file has no ORGN ``Time`` channel
    (only the day-3 ``test.wdf`` single-point file in this project).
    """
    origins = read_wdf_origins(path, header=header)
    time_entry = origins.get("Time")
    if time_entry is None:
        return None
    return time_entry["data"]


# ----------------------------------------------------------------------
# WMAP
# ----------------------------------------------------------------------

def read_wdf_map_geometry(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Parse WMAP into a usable shape, and classify the acquisition.

    ``kind`` is ``'raster'`` when the map is a real grid (``nsteps`` has at least two
    axes > 1, and their product matches the spectrum count), else ``'points'`` -- an
    irregular list of hand-picked positions, which is what ``nsteps == (1, 1, 1)``
    means. ``map_shape`` is ``(rows, cols)`` for rasters and ``None`` for point lists.

    Returns ``kind='points'`` with everything else ``None`` when there is no WMAP block.
    """
    path = Path(path)
    blocks = read_block_table(path)
    if "WMAP" not in blocks:
        return {"kind": "points", "map_shape": None, "origin": None,
                "step": None, "nsteps": None, "linefocus_size": None}

    header = read_wdf_header(path)
    _uid, offset, _length = blocks["WMAP"]
    with open(path, "rb") as fh:
        fh.seek(offset + 0x10)
        flag, unused = struct.unpack("<II", fh.read(8))
        origin = struct.unpack("<3f", fh.read(12))
        step = struct.unpack("<3f", fh.read(12))
        nsteps = struct.unpack("<3I", fh.read(12))
        (linefocus_size,) = struct.unpack("<I", fh.read(4))

    grid_axes = [n for n in nsteps if n > 1]
    n_grid = int(np.prod(grid_axes)) if grid_axes else 0
    is_raster = len(grid_axes) >= 2 and n_grid == header["capacity"]
    # nsteps is (x, y, z); rows follow y, columns follow x, matching the
    # (y_grid, x_grid, wavenumber) cube layout of the unified standard.
    map_shape = (int(nsteps[1]), int(nsteps[0])) if is_raster else None

    return {
        "kind": "raster" if is_raster else "points",
        "map_shape": map_shape,
        "flag": int(flag),
        "origin": tuple(float(v) for v in origin),
        "step": tuple(float(v) for v in step),
        "nsteps": tuple(int(v) for v in nsteps),
        "linefocus_size": int(linefocus_size),
    }


# ----------------------------------------------------------------------
# Convenience
# ----------------------------------------------------------------------

def summarize_wdf(path: Union[str, Path]) -> Dict[str, Any]:
    """
    One flat dict per file: header + map geometry + time bounds derived from ORGN.

    Handy for building a session index. ``spectrum_time_first/last_unix`` come from the
    ORGN channel (per-spectrum truth) while ``time_start/end_unix`` come from the
    header, so comparing them is a cheap consistency check.
    """
    header = read_wdf_header(path)
    geometry = read_wdf_map_geometry(path)
    times = read_wdf_spectrum_times(path, header=header)

    summary = dict(header)
    summary["kind"] = geometry["kind"]
    summary["map_shape"] = geometry["map_shape"]
    summary["nsteps"] = geometry["nsteps"]
    summary["has_spectrum_times"] = times is not None
    if times is not None and times.size:
        summary["spectrum_time_first_unix"] = float(times[0])
        summary["spectrum_time_last_unix"] = float(times[-1])
        summary["spectrum_time_span_s"] = float(times[-1] - times[0])
    else:
        summary["spectrum_time_first_unix"] = None
        summary["spectrum_time_last_unix"] = None
        summary["spectrum_time_span_s"] = None
    return summary
