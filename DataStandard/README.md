## Methods used for Exporting Raman Data to a Standard
This folder contains methods for exporting data to a standardized h5 file so that data from every
instrument can be analyzed with the same downstream scripts.

- Author: a-georgiadis (Assisted by Claude Code)
- Date: 08/17/26

| Script | Instrument | Input |
| --- | --- | --- |
| `wdfProcessing.py` / `wdfProcessing.ipynb` | Renishaw (WiRE) | `.wdf` |
| `labspecProcessing.py` | Horiba XploRA Plus (LabSpec 6) | `.txt` ASCII export |

Both write the same `filename_unified.h5` schema described below, and both are runnable directly
(`python labspecProcessing.py [inputFolder] [outputFolder]`) or importable as a module.
Use the `instrument` / `source_format` root attributes to tell the two apart downstream.

By default the batch functions **mirror the input subfolder structure** into the output folder
(`preserve_tree=True`). Keep this on for recursive runs: Raman filenames repeat across sample
folders, so a flat output would silently overwrite files.

H5 and Zarr file formats are both commonly used with zarr file formats taking a large foothold in the cloud space due to their ability to load individual subchunks and not being entirely binary. The metadata is stored as json instead of binary so they files are still partially machine readable


### Unified h5 Data Standard (written by both scripts)
filename_unified.h5
├── /                        # Root Attributes (Global Metadata)
│   ├── original_filename    # e.g., "scan_01.wdf"
│   ├── measurement_type     # "Single", "Series", or "Mapping"
│   ├── laser_wavelength_nm  # Excitation wavelength
│   ├── duration_seconds     # Total elapsed time of the scan
│   └── avg_time_per_spectrum# Calculated acquisition speed
│
├── /spectra                 # Spectral data and independent variables
│   ├── wavenumbers          # 1D array: Raman shift / Wavenumber axis
│   ├── spectral_cube        # 3D array: (Y, X, Intensities) [Present if mapped]
│   │                        # Attributes: map_x_start, map_x_pad, map_x_span
│   │                        #             map_y_start, map_y_pad, map_y_span
│   └── spectral_matrix      # 2D array: (sample, Intensities) [Present if single/list]
│
├── /coordinates             # Hardware tracking data (Aligned with Spectra)
│   ├── Spatial_X            # 1D array: Absolute X stage coordinates
│   ├── Spatial_Y            # 1D array: Absolute Y stage coordinates
│   ├── Time                 # 1D array: Relative timestamps (seconds)
│   └── [Other]              # Attributes on all: 'unit' and 'annotation'
│
└── /optical                 # Correlative imagery (Native & External)
    ├── whitelight           # 2D/3D array: Native microscope camera snapshot
    │                        # Attributes: physical_width, physical_height, origin_x, map_crop_box_px
    └── [custom_images]      # Appended datasets (e.g., pre_experiment_fluorescence)


### LabSpec / Horiba XploRA (`labspecProcessing.py`)
LabSpec 6 writes ASCII, cp1252/latin-1 encoded, as a `#Key=<tab>Value` header followed by a numeric
block. The trailing `#AxisType[n]` header lines declare which of three flavors a file is, and
`parse_labspec_txt()` detects this from the data block itself:

| LabSpec export | Data block | Stored as | `measurement_type` |
| --- | --- | --- | --- |
| `Intens, Spectr` | N rows of `wavenumber intensity` | `spectral_matrix` (1, n_wav) | `Single` |
| `+ Points` | wavenumber row, then M rows of `index` + intensities | `spectral_matrix` (M, n_wav) | `Series` |
| `+ X, Y (µm)` | wavenumber row, then M rows of `Y X` + intensities | `spectral_cube` (n_y, n_x, n_wav) | `Mapping` |

Instrument quirks worth knowing:
- **The leading coordinate columns of an XY export are ordered (Y, X), with X varying fastest** —
  even though the header lists `AxisType[2]=X` before `AxisType[3]=Y`. Reading them in header order
  transposes every map.
- An XY export is only folded into a `spectral_cube` when the grid is regular and complete;
  an aborted scan falls back to `spectral_matrix` plus the `Spatial_X` / `Spatial_Y` arrays.
- **`Points` exports carry no per-point stage coordinates**, only an acquisition index. These get
  `/coordinates/Point_Index` instead of `Spatial_X`/`Spatial_Y`; the single stage position from the
  header is kept in the `stage_x_um` / `stage_y_um` / `stage_z_um` root attributes.
- **No `/coordinates/Time`**: LabSpec exports no per-spectrum timestamps. Only the `duration_seconds`
  and `avg_time_per_spectrum` root attributes are set, derived from `#Full time` (which appears as
  `(s)`, `(mm:ss)` or `(h:mm:ss)` depending on scan length).
- **No `/optical` group**: the ASCII export contains no imagery. Attach external snapshots with
  `append_image_to_h5()`.
- Each file carries its own wavenumber axis (they differ between sessions), so do not assume a
  shared grid across files.
- `.l6v` siblings are LabSpec's proprietary binary format and are ignored.

Extra LabSpec-only root attributes, on top of the standard ones: `instrument`, `instrument_vendor`,
`source_format`, `source_relative_path`, `objective`, `grating`, `detector`,
`detector_temperature_C`, `acq_time_s`, `slit_um`, `hole_um`, `filter_pct`,
`spectral_resolution_cm1`, `spectro_center_cm1`, `project`, `sample`, `site`, `remark`, `date`,
`acquired`, `stage_x_um`, `stage_y_um`, `stage_z_um`, and `labspec_header_json` (the complete raw
header, so nothing from the instrument is ever discarded).

### Reading these files

The canonical reader is `ramanlib/h5io.py` (one directory up), which provides
`get_experiment_metadata`, `get_main_spectra`, `get_coordinates` and `get_optical_context`.
`example_extraction_renishaw.py` in this folder holds the same four functions with a runnable
demo under `if __name__ == "__main__":`; prefer importing from `ramanlib` so there is one copy.

Use `ramanlib.h5io.map_extent(map_meta)` rather than reading the `map_x_*` attributes directly —
earlier code looked for `map_span_x` / `map_start_x`, which no writer has ever emitted, so those
lookups silently returned `None`.