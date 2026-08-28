"""
Converts Horiba LabSpec 6 (XploRA Plus) ASCII exports into the Unified Raman HDF5
Standard, so LabSpec data can be analyzed with the same scripts as Renishaw WDF
data produced by wdfProcessing.py.

LabSpec writes three flavors of .txt, distinguished by the '#AxisType[n]' header lines:

    Single   Intens, Spectr           -> N rows of "wavenumber intensity"
    Points   Intens, Spectr, Points   -> wavenumber row, then M rows of "index + intensities"
    XY map   Intens, Spectr, X, Y     -> wavenumber row, then M rows of "Y X + intensities"

Note that the leading coordinate columns of an XY export are ordered (Y, X) with X
varying fastest, even though the header lists AxisType[2]=X before AxisType[3]=Y.

Only numpy + h5py are required, so this runs in any environment (no renishawWiRE).
"""

import json
import re
import sys
import traceback
import numpy as np
import h5py
from pathlib import Path
from typing import Any, Dict, Optional, Union

# LabSpec writes cp1252/latin-1 text (µm, °C) rather than UTF-8
LABSPEC_ENCODING = "latin-1"


# =========================================================================
# HEADER HELPERS
# =========================================================================
def _to_float(value: Any, default: float = 0.0) -> float:
    """
    Pull the first number out of a LabSpec header value.
    Tolerates the trailing spaces and unit decorations LabSpec leaves behind,
    e.g. '785 ' -> 785.0, 'x20' -> 20.0, '100%' -> 100.0, '1200 gr/mm' -> 1200.0.
    """
    if value is None:
        return default

    match = re.search(r"[-+]?\d*\.?\d+", str(value))
    return float(match.group()) if match else default


def _to_int(value: Any, default: int = 0) -> int:
    """Integer variant of _to_float (LabSpec writes '1' for accumulations, etc.)."""
    return int(round(_to_float(value, default)))


def _parse_full_time(header: Dict[str, str]) -> float:
    """
    Convert the LabSpec '#Full time' entry into seconds.

    The key itself carries the format, so all of these are handled:
        '#Full time(s)=        27'       -> 27.0
        '#Full time(mm:ss)=    1:38'     -> 98.0
        '#Full time(mm:ss)=    40:02'    -> 2402.0
        '#Full time(h:mm:ss)=  1:02:03'  -> 3723.0
    """
    for key, value in header.items():
        if not key.startswith("Full time"):
            continue

        text = str(value).strip()
        if not text:
            return 0.0

        # Colon-separated clock format: accumulate from the smallest unit up
        if ":" in text:
            total = 0.0
            for part in text.split(":"):
                total = total * 60.0 + _to_float(part)
            return total

        return _to_float(text)

    return 0.0


def _is_labspec_txt(filepath: Union[str, Path]) -> bool:
    """
    Cheap sniff so unrelated .txt files (notes, README) in a data folder are
    skipped instead of raising. A LabSpec export always opens with '#Key=value'.
    """
    try:
        with open(filepath, "r", encoding=LABSPEC_ENCODING) as file:
            first_line = file.readline().strip()
    except OSError:
        return False

    return first_line.startswith("#") and "=" in first_line


# =========================================================================
# PARSING
# =========================================================================
def parse_labspec_txt(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Read a LabSpec .txt export and auto-detect which of the three flavors it is.

    Parameters:
    -----------
    filepath : str or Path
        The LabSpec ASCII export.

    Returns:
    --------
    Dict[str, Any] with keys:
        'header'       : dict of the raw '#Key=Value' header, keys stripped of '#'
        'kind'         : 'single', 'points' or 'map'
        'wavenumbers'  : 1D float32 array of the Raman shift axis
        'intensities'  : 2D float32 array, always (sample, wavenumber), acquisition order
        'x', 'y'       : 1D float32 stage coordinates per sample ('map' only, else None)
        'point_index'  : 1D float32 acquisition index ('points' only, else None)
        'grid'         : (n_y, n_x) if the XY scan is a regular grid, else None
    """
    path = Path(filepath)

    header: Dict[str, str] = {}
    data_lines = []

    with open(path, "r", encoding=LABSPEC_ENCODING) as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("#"):
                # Header values are 'Key=<tab>Value'; keys can contain '=' free text
                if "=" in stripped:
                    key, value = stripped.split("=", 1)
                    header[key.removeprefix("#").strip()] = value.strip()
                continue

            data_lines.append(stripped)

    if not data_lines:
        raise ValueError(f"No numeric data found in {path.name}")

    first_row = data_lines[0].split()

    # -----------------------------------------------------------------
    # Flavor 1: single spectrum, two columns of "wavenumber intensity"
    # -----------------------------------------------------------------
    if len(first_row) == 2:
        table = np.array([line.split() for line in data_lines], dtype=np.float32)
        return {
            "header": header,
            "kind": "single",
            "wavenumbers": table[:, 0],
            "intensities": table[:, 1].reshape(1, -1),
            "x": None,
            "y": None,
            "point_index": None,
            "grid": None,
        }

    # -----------------------------------------------------------------
    # Flavors 2 & 3: leading wavenumber row, then one row per spectrum.
    # The number of leading coordinate columns identifies the flavor.
    # -----------------------------------------------------------------
    wavenumbers = np.array(first_row, dtype=np.float32)
    n_wavenumbers = len(wavenumbers)

    spectra_rows = [line.split() for line in data_lines[1:]]
    if not spectra_rows:
        raise ValueError(f"{path.name} declares a wavenumber axis but holds no spectra")

    n_lead = len(spectra_rows[0]) - n_wavenumbers
    if n_lead not in (1, 2):
        raise ValueError(
            f"Unexpected layout in {path.name}: {n_lead} leading columns "
            f"for {n_wavenumbers} wavenumbers"
        )

    lead = np.array([row[:n_lead] for row in spectra_rows], dtype=np.float32)
    intensities = np.array([row[n_lead:] for row in spectra_rows], dtype=np.float32)

    if n_lead == 1:
        # 'Points' export: a bare acquisition index, no stage coordinates
        return {
            "header": header,
            "kind": "points",
            "wavenumbers": wavenumbers,
            "intensities": intensities,
            "x": None,
            "y": None,
            "point_index": lead[:, 0],
            "grid": None,
        }

    # XY export: columns are (Y, X) with X varying fastest
    y_positions = lead[:, 0]
    x_positions = lead[:, 1]

    unique_y = np.unique(y_positions)
    unique_x = np.unique(x_positions)
    grid = None
    if len(unique_y) * len(unique_x) == len(intensities) and len(unique_y) > 1:
        # Regular, complete grid -> safe to fold into a spectral cube
        grid = (len(unique_y), len(unique_x))

    return {
        "header": header,
        "kind": "map",
        "wavenumbers": wavenumbers,
        "intensities": intensities,
        "x": x_positions,
        "y": y_positions,
        "point_index": None,
        "grid": grid,
    }


# =========================================================================
# DIAGNOSTIC REPORT
# =========================================================================
def explore_labspec_contents(filepath: Union[str, Path]) -> None:
    """
    Prints everything readable from a LabSpec .txt export, mirroring
    explore_wdf_contents() in wdfProcessing.py. Use this to sanity-check a new
    dataset before committing to a batch conversion.
    """
    path = Path(filepath)
    if not path.is_file():
        print(f"File not found: {path}")
        return

    print(f"\n{'='*60}")
    print(f" LABSPEC DIAGNOSTIC REPORT: {path.name}")
    print(f"{'='*60}\n")

    try:
        parsed = parse_labspec_txt(path)
    except Exception as e:
        print(f"Failed to read file: {type(e).__name__} - {e}")
        return

    header = parsed["header"]
    intensities = parsed["intensities"]
    wavenumbers = parsed["wavenumbers"]

    # --- 1. CORE METADATA ---
    print("📋 [1] CORE METADATA")
    print("-" * 30)
    print(f"  Title:              {header.get('Title', '')}")
    print(f"  Project / Sample:   {header.get('Project', '')} / {header.get('Sample', '')}")
    print(f"  Instrument:         {header.get('Instrument', '')} ({header.get('Detector', '')})")
    print(f"  Measurement Type:   {_MEASUREMENT_TYPES[parsed['kind']]} (LabSpec '{parsed['kind']}' export)")
    print(f"  Laser Wavelength:   {_to_float(header.get('Laser (nm)')):.2f} nm")
    print(f"  Objective/Grating:  {header.get('Objective', '')} / {header.get('Grating', '')}")
    print(f"  Spectra Collected:  {len(intensities)}")
    print(f"  Accumulations:      {_to_int(header.get('Accumulations'), 1)}")
    print(f"  Acq. Time:          {_to_float(header.get('Acq. time (s)')):.2f} s per spectrum")
    print(f"  Acquired:           {header.get('Acquired', header.get('Date', ''))}")
    print()

    # --- 2. SPECTRAL DATA ---
    print("📈 [2] SPECTRAL DATA & AXES")
    print("-" * 30)
    print(f"  Points per spec:    {len(wavenumbers)}")
    print(f"  X-Axis (Shift):     {len(wavenumbers)} points | "
          f"Range: {wavenumbers.min():.2f} to {wavenumbers.max():.2f} [1/cm]")
    print(f"  Spectral res.:      {_to_float(header.get('Spectral res.(cm-¹)')):.2f} cm-1")
    print(f"  Data Matrix Shape:  {intensities.shape} (Sample, Shift)")
    print(f"  Data Min/Max:       {intensities.min():.2f} / {intensities.max():.2f}")
    print()

    # --- 3. HARDWARE TRACKING & ACQUISITION TIME ---
    print("📍 [3] HARDWARE TRACKING & ORIGINS")
    print("-" * 30)
    print(f"  Header Stage XYZ:   ({_to_float(header.get('X (µm)')):.2f}, "
          f"{_to_float(header.get('Y (µm)')):.2f}, {_to_float(header.get('Z (µm)')):.2f}) µm")

    if parsed["x"] is not None:
        print(f"  Stage X Array:      {len(parsed['x'])} points | "
              f"Range: {parsed['x'].min():.2f} to {parsed['x'].max():.2f} [Micron]")
        print(f"  Stage Y Array:      {len(parsed['y'])} points | "
              f"Range: {parsed['y'].min():.2f} to {parsed['y'].max():.2f} [Micron]")
    elif parsed["point_index"] is not None:
        print(f"  Point Index Array:  {len(parsed['point_index'])} points | "
              f"Range: {parsed['point_index'].min():.0f} to {parsed['point_index'].max():.0f}")
        print("  Note: LabSpec 'Points' exports carry no per-point stage coordinates.")
    else:
        print("  No per-spectrum tracking arrays (single spectrum).")

    duration = _parse_full_time(header)
    print(f"\n  Total Duration:     {duration:.2f} seconds ({duration/60:.2f} mins)")
    if len(intensities) > 0 and duration > 0:
        print(f"  Avg per Spectrum:   {duration/len(intensities):.3f} s")
    print("  Note: LabSpec exports no per-spectrum timestamps, so no Time array is written.")
    print()

    # --- 4. MAPPING SPATIAL DATA ---
    if parsed["kind"] == "map":
        print("🗺️  [4] MAPPING / GRID INFORMATION")
        print("-" * 30)
        if parsed["grid"]:
            n_y, n_x = parsed["grid"]
            print(f"  Grid Shape:         {n_x} x {n_y} (Width x Height)")
            print(f"  Start Coords:       X: {parsed['x'][0]:.2f} | Y: {parsed['y'][0]:.2f}")
            print(f"  Step Size:          X: {_mean_step(parsed['x']):.4f} | Y: {_mean_step(parsed['y']):.4f}")
            print(f"  Total Span:         X: {np.ptp(parsed['x']):.2f} [Micron] | "
                  f"Y: {np.ptp(parsed['y']):.2f} [Micron]")
        else:
            print("  Irregular / incomplete grid -> will be stored as a point list.")
        print()

    # --- 5. OPTICAL IMAGE DATA ---
    print("📷 [5] NATIVE WHITELIGHT IMAGE")
    print("-" * 30)
    print("  Image Found:        No (LabSpec ASCII exports contain no imagery)")

    print(f"\n{'='*60}")


def _mean_step(positions: np.ndarray) -> float:
    """Average spacing between the unique positions along one map axis."""
    unique = np.unique(positions)
    return float(np.diff(unique).mean()) if len(unique) > 1 else 0.0


# LabSpec flavor -> the measurement_type vocabulary the WDF standard already uses
_MEASUREMENT_TYPES = {"single": "Single", "points": "Series", "map": "Mapping"}


# =========================================================================
# CONVERSION TO THE UNIFIED HDF5 STANDARD
# =========================================================================
def convert_labspec_to_h5(
    txt_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    source_root: Optional[Union[str, Path]] = None,
) -> Optional[Path]:
    """
    Converts a LabSpec .txt export into the Unified Raman HDF5 Standard,
    dynamically handling Maps, Point Series and Single Shots.

    Parameters:
    -----------
    txt_path : str or Path
        The LabSpec ASCII export.
    output_dir : str or Path, optional
        Destination for the .h5 file. Defaults to a 'processed_h5' folder
        beside the input file.
    source_root : str or Path, optional
        Batch input root, recorded as the 'source_relative_path' attribute so
        identically named files from different sample folders stay traceable.
    """
    input_path = Path(txt_path)

    if output_dir is None:
        output_dir = input_path.parent / "processed_h5"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    h5_path = output_dir / f"{input_path.stem}_unified.h5"

    try:
        parsed = parse_labspec_txt(input_path)
    except Exception as e:
        print(f"[!] Failed to read {input_path.name}: {e}")
        return None

    header = parsed["header"]
    intensities = parsed["intensities"]
    spectra_count = len(intensities)

    duration = _parse_full_time(header)
    accumulations = _to_int(header.get("Accumulations"), 1)
    if duration > 0 and spectra_count > 0:
        avg_time = duration / spectra_count
    else:
        # Fall back to the requested exposure when LabSpec omits the total time
        avg_time = _to_float(header.get("Acq. time (s)")) * max(accumulations, 1)

    with h5py.File(h5_path, "w") as f:
        # ---------------------------------------------------------
        # 1. GLOBAL ROOT ATTRIBUTES (Metadata & Completion Status)
        # ---------------------------------------------------------
        f.attrs["original_filename"] = input_path.name
        f.attrs["title"] = header.get("Title", input_path.stem)
        f.attrs["measurement_type"] = _MEASUREMENT_TYPES[parsed["kind"]]
        # LabSpec has no scan-type enum; '#Range' distinguishes a single
        # grating position from a stitched extended scan
        f.attrs["scan_type"] = "Static" if header.get("Range", "Off") == "Off" else "Extended"
        f.attrs["laser_wavelength_nm"] = _to_float(header.get("Laser (nm)"))
        f.attrs["accumulations"] = accumulations
        f.attrs["is_completed"] = True
        f.attrs["spectra_count"] = spectra_count
        f.attrs["duration_seconds"] = duration
        f.attrs["avg_time_per_spectrum"] = avg_time

        # LabSpec-specific extras. 'instrument' / 'source_format' are how
        # downstream scripts tell Horiba data apart from Renishaw data.
        f.attrs["instrument"] = header.get("Instrument", "XploRA Plus")
        f.attrs["instrument_vendor"] = "Horiba"
        f.attrs["source_format"] = "labspec_txt"
        if source_root is not None:
            f.attrs["source_relative_path"] = str(input_path.relative_to(Path(source_root)))

        f.attrs["objective"] = header.get("Objective", "")
        f.attrs["grating"] = header.get("Grating", "")
        f.attrs["detector"] = header.get("Detector", "")
        f.attrs["detector_temperature_C"] = _to_float(header.get("Detector temperature (°C)"))
        f.attrs["acq_time_s"] = _to_float(header.get("Acq. time (s)"))
        f.attrs["slit_um"] = _to_float(header.get("Slit (µm)"))
        f.attrs["hole_um"] = _to_float(header.get("Hole (µm)"))
        f.attrs["filter_pct"] = _to_float(header.get("Filter"))
        f.attrs["spectral_resolution_cm1"] = _to_float(header.get("Spectral res.(cm-¹)"))
        f.attrs["spectro_center_cm1"] = _to_float(header.get("Spectro (cm-¹)"))
        f.attrs["project"] = header.get("Project", "")
        f.attrs["sample"] = header.get("Sample", "")
        f.attrs["site"] = header.get("Site", "")
        f.attrs["remark"] = header.get("Remark", "")
        f.attrs["date"] = header.get("Date", "")
        f.attrs["acquired"] = header.get("Acquired", "")
        f.attrs["stage_x_um"] = _to_float(header.get("X (µm)"))
        f.attrs["stage_y_um"] = _to_float(header.get("Y (µm)"))
        f.attrs["stage_z_um"] = _to_float(header.get("Z (µm)"))
        # Nothing from the instrument is discarded: keep the raw header verbatim
        f.attrs["labspec_header_json"] = json.dumps(header, ensure_ascii=False)

        # ---------------------------------------------------------
        # 2. SPECTRAL DATA
        # ---------------------------------------------------------
        grp_spectra = f.create_group("spectra")
        grp_spectra.create_dataset("wavenumbers", data=parsed["wavenumbers"], compression="gzip")

        if parsed["grid"] is not None:
            # Grid Map: fold into (Y, X, wavenumbers). Valid because the export
            # orders rows with Y as the slow axis and X varying fastest.
            n_y, n_x = parsed["grid"]
            cube = intensities.reshape(n_y, n_x, -1)
            dset = grp_spectra.create_dataset("spectral_cube", data=cube, compression="gzip")
            dset.attrs["description"] = "(y_grid, x_grid, wavenumber)"

            x_positions, y_positions = parsed["x"], parsed["y"]
            dset.attrs["map_x_start"] = float(x_positions[0])
            dset.attrs["map_y_start"] = float(y_positions[0])
            dset.attrs["map_x_pad"] = _mean_step(x_positions)
            dset.attrs["map_y_pad"] = _mean_step(y_positions)
            dset.attrs["map_x_span"] = float(np.ptp(x_positions))
            dset.attrs["map_y_span"] = float(np.ptp(y_positions))
        else:
            # Single shot, point series, or an aborted/irregular map
            dset = grp_spectra.create_dataset("spectral_matrix", data=intensities, compression="gzip")
            dset.attrs["description"] = "(sample, wavenumber)"

        # ---------------------------------------------------------
        # 3. HARDWARE TRACKING
        # ---------------------------------------------------------
        grp_coords = f.create_group("coordinates")

        if parsed["x"] is not None:
            # Flattened and aligned 1:1 with the cube's spatial axes
            for name, array, annotation in (
                ("Spatial_X", parsed["x"], "X"),
                ("Spatial_Y", parsed["y"], "Y"),
            ):
                dset_coord = grp_coords.create_dataset(name, data=array, compression="gzip")
                dset_coord.attrs["unit"] = "Micron"
                dset_coord.attrs["annotation"] = annotation

        if parsed["point_index"] is not None:
            dset_coord = grp_coords.create_dataset(
                "Point_Index", data=parsed["point_index"], compression="gzip"
            )
            dset_coord.attrs["unit"] = "Index"
            dset_coord.attrs["annotation"] = "LabSpec point number (no stage coordinates exported)"

        # No /coordinates/Time: LabSpec exports no per-spectrum timestamps.
        # Use the duration_seconds / avg_time_per_spectrum root attributes instead.

        # ---------------------------------------------------------
        # 4. OPTICAL IMAGES
        # ---------------------------------------------------------
        # LabSpec ASCII exports hold no imagery, so /optical is omitted here.
        # Attach external snapshots afterwards with append_image_to_h5().

    print(f"✅ Successfully created: {h5_path.name}")
    return h5_path


def batch_process_labspec(input_folder, output_folder=None, recursive=True, preserve_tree=True):
    """
    Process all LabSpec .txt files in a folder and convert them to the unified
    HDF5 standard.

    Parameters:
    -----------
    input_folder : str or Path
        Directory containing the .txt files.
    output_folder : str or Path, optional
        Destination for the .h5 files. If None, creates a 'processed_h5'
        folder inside the input_folder.
    recursive : bool
        If True (default), searches for .txt files in all subdirectories as well.
    preserve_tree : bool
        If True (default), reproduces the input subfolder structure inside the
        output folder. Keep this on for recursive runs: LabSpec filenames repeat
        across sample folders, so a flat output would overwrite files.
    """
    input_path = Path(input_folder).resolve()

    # Set default output directory if none is provided
    if output_folder is None:
        output_path = input_path / "processed_h5"
    else:
        output_path = Path(output_folder).resolve()

    output_path.mkdir(parents=True, exist_ok=True)

    # Gather LabSpec text files
    search_pattern = "**/*.txt" if recursive else "*.txt"
    txt_files = sorted(
        p for p in input_path.glob(search_pattern) if output_path not in p.parents
    )

    if not txt_files:
        print(f"No .txt files found in {input_path}")
        return []

    print(f"Found {len(txt_files)} .txt files. Starting batch conversion...\n")

    successful_files = []
    failed_files = []
    skipped_files = []

    for txt_file in txt_files:
        if not _is_labspec_txt(txt_file):
            skipped_files.append(txt_file.name)
            continue

        try:
            # Mirror the input tree so same-named files from different folders coexist
            if preserve_tree:
                destination = output_path / txt_file.parent.relative_to(input_path)
            else:
                destination = output_path

            if convert_labspec_to_h5(txt_file, destination, source_root=input_path) is None:
                failed_files.append(txt_file.name)
            else:
                successful_files.append(txt_file.name)

        except Exception as e:
            print(f"    [!] Failed to process {txt_file.name}: {type(e).__name__} - {e}")
            # Uncomment the next line if you need deep debugging on failed files
            # traceback.print_exc()
            failed_files.append(txt_file.name)

    # Print Summary Report
    print(f"\n{'='*50}")
    print("Batch Processing Complete!")
    print(f"Successfully processed: {len(successful_files)}/{len(txt_files) - len(skipped_files)}")

    if skipped_files:
        print(f"Skipped, not LabSpec exports ({len(skipped_files)}):")
        for name in skipped_files:
            print(f"  - {name}")

    if failed_files:
        print(f"Failed files ({len(failed_files)}):")
        for name in failed_files:
            print(f"  - {name}")

    return successful_files


def append_image_to_h5(h5_path, image_path, dataset_name):
    """Append a standalone image to an existing unified HDF5 file."""
    from PIL import Image

    # Load and convert the new image
    img = Image.open(image_path)
    img_array = np.array(img)

    # Open the file in 'a' (read/write/create) mode
    with h5py.File(h5_path, 'a') as f:
        # Ensure the optical group exists
        if 'optical' not in f:
            grp_image = f.create_group('optical')
        else:
            grp_image = f['optical']

        # Create the new dataset for the image
        dset = grp_image.create_dataset(
            dataset_name,
            data=img_array,
            compression='gzip'
        )

        # Add relevant metadata as attributes
        dset.attrs['source'] = 'external_camera'
        dset.attrs['width'] = img.width
        dset.attrs['height'] = img.height

    print(f"Successfully appended {dataset_name} to {h5_path}")


if __name__ == "__main__":
    # Folder to Process:
    inputFolder = "/Users/antonygeorgiadis/Desktop/Stanford_Research/Data/RobJudsonTorresLab-MelanocytesProject"
    outputFolder = inputFolder + "/Extracted"

    # Command line overrides: labspecProcessing.py <inputFolder> [outputFolder]
    if len(sys.argv) > 1:
        inputFolder = sys.argv[1]
        outputFolder = sys.argv[2] if len(sys.argv) > 2 else inputFolder + "/Extracted"

    # Process the folders
    batch_process_labspec(inputFolder, outputFolder, recursive=True, preserve_tree=True)
