import os
import glob
import json
import sys
import pandas as pd
import numpy as np
import traceback
import h5py
from pathlib import Path
from PIL import Image
import struct
from natsort import natsorted
from typing import Tuple, Dict, Any, Union

from wdf import Wdf, WdfBlockId, WdfFlags, WdfDataUnit, WdfType, WdfScanType, WdfDataType, WdfSpectrumFlags
from renishawWiRE.wdfReader import WDFReader
# ==========================================
# MONKEY-PATCH: Bypass strict WMAP assertions (Safe for Jupyter/Interactive)
# ==========================================
if not getattr(WDFReader._parse_wmap, '_is_patched', False):
    original_parse_wmap = WDFReader._parse_wmap

    def safe_parse_wmap(self):
        try:
            original_parse_wmap(self)
        except ValueError as e:
            if "WMAP" in str(e):
                self._wmap_warning = str(e)
            else:
                raise e

    # Tag the wrapper so we know it has already been applied
    safe_parse_wmap._is_patched = True
    WDFReader._parse_wmap = safe_parse_wmap
# ==========================================
import matplotlib.pyplot as plt

# renishawWiRE zeroes the ORGN Time reference (``array = array - array[0]``), so
# reader.origin_list_header only ever gives seconds-within-this-file. wdfTimestamps
# re-reads the raw FILETIME ticks so we can also store an absolute UTC timeline.
from wdfTimestamps import read_wdf_header, read_wdf_spectrum_times

def convert_wdf_to_h5(wdf_path, output_dir=None):
    """
    Converts a WDF file into the Unified Raman HDF5 Standard, 
    dynamically handling Maps, Point Series, and Single Shots.
    Calculates and stores true acquisition times.
    """
    input_path = Path(wdf_path)
    
    if output_dir is None:
        output_dir = input_path.parent / "processed_h5"
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    h5_path = output_dir / f"{input_path.stem}_unified.h5"

    try:
        reader = WDFReader(str(input_path))
    except Exception as e:
        print(f"[!] Failed to read {input_path.name}: {e}")
        return None

    with h5py.File(h5_path, 'w') as f:
        # ---------------------------------------------------------
        # 1. GLOBAL ROOT ATTRIBUTES (Metadata & Completion Status)
        # ---------------------------------------------------------
        f.attrs['original_filename'] = input_path.name
        f.attrs['title'] = reader.title
        f.attrs['measurement_type'] = reader.measurement_type.name
        f.attrs['scan_type'] = reader.scan_type.name
        f.attrs['laser_wavelength_nm'] = float(reader.laser_length) if reader.laser_length else 0.0
        f.attrs['accumulations'] = reader.accumulation_count
        f.attrs['is_completed'] = reader.is_completed
        f.attrs['spectra_count'] = reader.count

        # Absolute acquisition window, from the two uint64 FILETIMEs at WDF1 0x88/0x90
        # that renishawWiRE never parses. Without these, /coordinates/Time (which is
        # relative to each file's own first spectrum) cannot order spectra across files.
        try:
            _hdr = read_wdf_header(input_path)
            f.attrs['time_start_utc'] = _hdr['time_start_utc'].isoformat()
            f.attrs['time_end_utc'] = _hdr['time_end_utc'].isoformat()
            f.attrs['time_epoch'] = 'unix_seconds_utc'
        except Exception as e:
            print(f"    [!] Could not read absolute timestamps from {input_path.name}: {e}")
            _hdr = None

        # ---------------------------------------------------------
        # 2. SPECTRAL DATA
        # ---------------------------------------------------------
        grp_spectra = f.create_group('spectra')
        grp_spectra.create_dataset('wavenumbers', data=reader.xdata, compression='gzip')

        spectra_data = reader.spectra

        # renishawWiRE's __reshape_spectra can leave the stack flat when an acquisition
        # was aborted (count < capacity), which silently produced a (1, count*npoints)
        # 'spectral_matrix'. Restore the intended 2-D shape before dispatching on ndim.
        n_points = getattr(reader, 'point_per_spectrum', 0) or 0
        if (spectra_data.ndim == 1 and n_points and reader.count > 1
                and spectra_data.size == reader.count * n_points):
            print(f"    [i] Reshaping flat spectra to ({reader.count}, {n_points})")
            spectra_data = spectra_data.reshape(reader.count, n_points)

        # Standardize matrix shapes
        if spectra_data.ndim == 1:
            # Single Shot: Force into (1, wavenumbers)
            spectra_data = spectra_data.reshape(1, -1)
            dset = grp_spectra.create_dataset('spectral_matrix', data=spectra_data, compression='gzip')
            dset.attrs['description'] = '(sample, wavenumber)'
        elif spectra_data.ndim == 2:
            # Point Series: Already (samples, wavenumbers)
            dset = grp_spectra.create_dataset('spectral_matrix', data=spectra_data, compression='gzip')
            dset.attrs['description'] = '(sample, wavenumber)'
        elif spectra_data.ndim == 3:
            # Grid Map: (Y, X, wavenumbers)
            dset = grp_spectra.create_dataset('spectral_cube', data=spectra_data, compression='gzip')
            dset.attrs['description'] = '(y_grid, x_grid, wavenumber)'

            # Append Map Dimensions if available
            if hasattr(reader, 'map_info'):
                mi = reader.map_info
                for key in ['x_start', 'y_start', 'x_pad', 'y_pad', 'x_span', 'y_span']:
                    if key in mi:
                        dset.attrs[f'map_{key}'] = mi[key]

        # ---------------------------------------------------------
        # 3. HARDWARE TRACKING & ACQUISITION TIME
        # ---------------------------------------------------------
        grp_coords = f.create_group('coordinates')
        
        # Set defaults in case the Time array is missing or empty
        f.attrs['duration_seconds'] = 0.0
        f.attrs['avg_time_per_spectrum'] = 0.0
        
        if hasattr(reader, 'origin_list_header') and reader.origin_list_header:
            for origin in reader.origin_list_header:
                is_xy, data_type, unit_type, annotation, array = origin
                
                if array is not None:
                    dset_coord = grp_coords.create_dataset(data_type.name, data=array, compression='gzip')
                    dset_coord.attrs['unit'] = unit_type.name
                    dset_coord.attrs['annotation'] = annotation

                    # Parse Time array to calculate kinetics and map speeds
                    if data_type.name == "Time" and len(array) > 0:
                        if len(array) > 1:
                            # Time spans from first to last point
                            total_duration = float(array[-1] - array[0])
                            avg_acq_time = total_duration / len(array)
                        else:
                            # Single point scans won't have a delta, duration defaults to 0
                            total_duration = 0.0
                            avg_acq_time = 0.0
                            
                        f.attrs['duration_seconds'] = total_duration
                        f.attrs['avg_time_per_spectrum'] = avg_acq_time

        # Absolute per-spectrum timestamps, alongside (not replacing) the relative
        # 'Time' channel above -- every reader and every previously written file expects
        # 'Time' to keep starting at 0.0.
        if _hdr is not None:
            try:
                t_utc = read_wdf_spectrum_times(input_path, header=_hdr)
            except Exception as e:
                print(f"    [!] Could not read per-spectrum times from {input_path.name}: {e}")
                t_utc = None
            if t_utc is not None:
                dset_t = grp_coords.create_dataset('Time_utc', data=t_utc, compression='gzip')
                dset_t.attrs['unit'] = 'unix_seconds_utc'
                dset_t.attrs['annotation'] = 'Absolute acquisition time (UTC)'

        # ---------------------------------------------------------
        # 4. OPTICAL IMAGES & PERCEIVED DIMENSIONS
        # ---------------------------------------------------------
        if hasattr(reader, 'img') and reader.img is not None:
            grp_optical = f.create_group('optical')
            
            # Convert internal IO Bytes to NumPy array
            img_array = np.array(Image.open(reader.img))
            dset_img = grp_optical.create_dataset('whitelight', data=img_array, compression='gzip')
            
            # Store dimensions and physical origins directly on the image dataset
            if hasattr(reader, 'img_dimensions'):
                w, h = reader.img_dimensions
                dset_img.attrs['physical_width'] = w
                dset_img.attrs['physical_height'] = h
                dset_img.attrs['unit'] = reader.img_dimension_unit.name if hasattr(reader, 'img_dimension_unit') else "Micron"
                
            if hasattr(reader, 'img_origins'):
                x, y = reader.img_origins
                dset_img.attrs['origin_x'] = x
                dset_img.attrs['origin_y'] = y
                
            if hasattr(reader, 'img_cropbox'):
                # (left, upper, right, lower px)
                dset_img.attrs['map_crop_box_px'] = reader.img_cropbox

    reader.close()
    print(f"✅ Successfully created: {h5_path.name}")
    return h5_path

def batch_process_wdfs(input_folder, output_folder=None, recursive=False, preserve_tree=True):
    """
    Process all .wdf files in a folder and convert them to the unified HDF5 standard.

    Parameters:
    -----------
    input_folder : str or Path
        Directory containing the .wdf files.
    output_folder : str or Path, optional
        Destination for the .h5 files. If None, creates a 'processed_h5'
        folder inside the input_folder.
    recursive : bool
        If True, searches for .wdf files in all subdirectories as well.
    preserve_tree : bool
        If True (default), reproduces the input subfolder structure inside the
        output folder. This only has an effect when recursive=True, and keeps
        same-named files from different subfolders from overwriting each other.
    """
    input_path = Path(input_folder).resolve()

    # Set default output directory if none is provided
    if output_folder is None:
        output_path = input_path / "processed_h5"
    else:
        output_path = Path(output_folder).resolve()

    output_path.mkdir(parents=True, exist_ok=True)
    
    # Gather WDF files
    search_pattern = "**/*.wdf" if recursive else "*.wdf"
    wdf_files = list(input_path.glob(search_pattern))
    
    if not wdf_files:
        print(f"No WDF files found in {input_path}")
        return []
        
    print(f"Found {len(wdf_files)} WDF files. Starting batch conversion...\n")
    
    successful_files = []
    failed_files = []
    
    for wdf_file in wdf_files:
        try:
            # 1. Mirror the input tree so same-named files from different
            #    subfolders coexist in the output
            if preserve_tree:
                destination = output_path / wdf_file.parent.relative_to(input_path)
            else:
                destination = output_path

            # 2. Call the unified HDF5 export function
            convert_wdf_to_h5(wdf_file, destination)

            successful_files.append(wdf_file.name)

        except Exception as e:
            print(f"    [!] Failed to process {wdf_file.name}: {type(e).__name__} - {e}")
            # Uncomment the next line if you need deep debugging on failed files
            # traceback.print_exc() 
            failed_files.append(wdf_file.name)
            
    # Print Summary Report
    print(f"\n{'='*50}")
    print("Batch Processing Complete!")
    print(f"Successfully processed: {len(successful_files)}/{len(wdf_files)}")
    
    if failed_files:
        print(f"Failed files ({len(failed_files)}):")
        for f in failed_files:
            print(f"  - {f}")
            
    return successful_files

def append_image_to_h5(h5_path, image_path, dataset_name):
    """Append a standalone image to an existing unified HDF5 file."""
    
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
    inputFolder = "/Users/antonygeorgiadis/Desktop/Stanford_Research/Data/CART_Project/RamanData/20260807_CART_SCRNATrial1_Day2"
    outputFolder = inputFolder + "/Extracted"

    # Command line overrides: wdfProcessing.py <inputFolder> [outputFolder]
    if len(sys.argv) > 1:
        inputFolder = sys.argv[1]
        outputFolder = sys.argv[2] if len(sys.argv) > 2 else inputFolder + "/Extracted"

    # Process the folders
    batch_process_wdfs(inputFolder, outputFolder)