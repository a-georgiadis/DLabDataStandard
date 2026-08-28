import matplotlib.pyplot as plt
from PIL import Image
import h5py
from typing import Tuple, Dict, Any, Union
import numpy as np
from pathlib import Path

# Some Examples of Code for Exporting
def get_experiment_metadata(h5_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Extracts global experiment and kinetic metadata from the root of the HDF5 file.
    
    This function reads the root attributes which act as the high-level index for the 
    dataset. It is highly optimized for fast database ingestion scripts, as it does 
    not load any heavy NumPy arrays into memory.

    Parameters:
    -----------
    h5_path : str or Path
        The file path to the unified .h5 file.

    Returns:
    --------
    Dict[str, Any]
        A dictionary containing global attributes. Expected keys include:
        - 'original_filename' (str)
        - 'measurement_type' (str: 'Single', 'Series', 'Mapping')
        - 'laser_wavelength_nm' (float)
        - 'duration_seconds' (float)
        - 'avg_time_per_spectrum' (float)
        - 'is_completed' (bool)
    """
    with h5py.File(h5_path, 'r') as f:
        return dict(f.attrs.items())

def get_main_spectra(h5_path: Union[str, Path]) -> Tuple[np.ndarray, np.ndarray, bool, Dict[str, Any]]:
    """
    Extracts the main spectral data matrix, the independent wavenumber axis, 
    and any associated spatial mapping attributes.

    This function abstracts away the difference between 1D/2D point lists and 
    3D micro-maps, returning a standardized output ready for immediate integration 
    into downstream PyQt plotting widgets or Napari Image layers.

    Parameters:
    -----------
    h5_path : str or Path
        The file path to the unified .h5 file.

    Returns:
    --------
    wavenumbers : np.ndarray
        1D array of the Raman shift / wavenumber axis.
    raman_data : np.ndarray
        The intensity data. 
        - If is_map is True: Shape is (Y_grid, X_grid, Shift).
        - If is_map is False: Shape is (Sample, Shift).
    is_map : bool
        True if the data was collected as a spatial grid (spectral_cube).
    map_meta : Dict[str, Any]
        Dictionary of spatial bounding attributes if is_map is True. Expected keys 
        include 'map_x_start', 'map_x_pad', 'map_x_span' and the y equivalents.
        Empty if is_map is False.
        
    Raises:
    -------
    KeyError
        If neither 'spectral_cube' nor 'spectral_matrix' datasets are found.
    """
    map_meta = {}
    with h5py.File(h5_path, 'r') as f:
        grp = f['spectra']
        
        # [:] slices the entire array from the disk into a NumPy array in RAM
        wavenumbers = grp['wavenumbers'][:]
        
        if 'spectral_cube' in grp:
            dset = grp['spectral_cube']
            raman_data = dset[:]
            is_map = True
            map_meta = dict(dset.attrs.items())
        elif 'spectral_matrix' in grp:
            dset = grp['spectral_matrix']
            raman_data = dset[:]
            is_map = False
        else:
            raise KeyError("No standard spectral dataset ('spectral_cube' or 'spectral_matrix') found in /spectra.")
            
    return wavenumbers, raman_data, is_map, map_meta

def get_coordinates(h5_path: Union[str, Path]) -> Dict[str, Dict[str, Any]]:
    """
    Extracts explicit hardware tracking dimensions (e.g., stage coordinates, kinetic timestamps).
    
    The arrays returned here align 1:1 with the 'Sample' axis of the spectral_matrix, 
    or the flattened spatial axes of the spectral_cube. This is particularly useful 
    for plotting discrete 'Points' layers over visual context images or calculating 
    kinetic reaction rates using the 'Time' array.

    Parameters:
    -----------
    h5_path : str or Path
        The file path to the unified .h5 file.

    Returns:
    --------
    Dict[str, Dict[str, Any]]
        A nested dictionary structured by tracking dimension. 
        Example format: 
        {
            'Spatial_X': {'data': np.ndarray, 'unit': 'Micron', 'annotation': 'X'},
            'Time': {'data': np.ndarray, 'unit': 'FileTime', 'annotation': 'Time'}
        }
    """
    coords = {}
    with h5py.File(h5_path, 'r') as f:
        if 'coordinates' in f:
            for key, dset in f['coordinates'].items():
                coords[key] = {
                    'data': dset[:],
                    'unit': dset.attrs.get('unit', 'Unknown'),
                    'annotation': dset.attrs.get('annotation', '')
                }
    return coords

def get_optical_context(h5_path: Union[str, Path]) -> Dict[str, Dict[str, Any]]:
    """
    Extracts native whitelight context images and their spatial alignment metadata.

    The metadata dictionary returned with each image is explicitly designed to feed 
    directly into correlative rendering tools. The attributes map cleanly to the 
    `scale` and `translate` arguments required to align this optical feed with 
    the spatial Raman heatmaps.

    Parameters:
    -----------
    h5_path : str or Path
        The file path to the unified .h5 file.

    Returns:
    --------
    Dict[str, Dict[str, Any]]
        A dictionary containing images and their physical bounds.
        Example format:
        {
            'whitelight': {
                'data': np.ndarray,  # 2D or 3D RGB image array
                'meta': {
                    'physical_width': float, 
                    'origin_x': float,
                    'map_crop_box_px': tuple,
                    'unit': 'Micron'
                }
            }
        }
    """
    images = {}
    with h5py.File(h5_path, 'r') as f:
        if 'optical' in f:
            for img_name, dset in f['optical'].items():
                images[img_name] = {
                    'data': dset[:],
                    'meta': dict(dset.attrs.items())
                }
    return images

def _demo(file_path: str) -> None:
    """Prints a summary of one unified .h5 file, exercising all four readers."""
    print("--- 1. GLOBAL METADATA & KINETICS ---")
    meta = get_experiment_metadata(file_path)
    print(f"File:              {meta.get('original_filename')}")
    print(f"Measurement Type:  {meta.get('measurement_type')}")
    print(f"Laser:             {meta.get('laser_wavelength_nm')} nm")
    print(f"Total Duration:    {meta.get('duration_seconds'):.2f} s")
    print(f"Acquisition Speed: {meta.get('avg_time_per_spectrum'):.3f} s/point")

    print("\n--- 2. RAMAN SPECTRA ---")
    wavs, data, is_map, map_meta = get_main_spectra(file_path)
    if is_map:
        print(f"Loaded a 3D Spectral Map with shape: {data.shape} (Y, X, Shift)")
        # Attribute names are map_x_span / map_y_span -- 'map_span_x' never existed
        # in any file written by either converter, so it always printed None.
        print(f"Map Spatial Span: {map_meta.get('map_x_span')} x {map_meta.get('map_y_span')} microns")
        # Generate a dummy heatmap (e.g., peak intensity)
        heatmap = data.max(axis=2) 
    else:
        print(f"Loaded Point Spectra with shape: {data.shape} (Samples, Shift)")
        mean_spectrum = data.mean(axis=0)

    print("\n--- 3. HARDWARE TRACKING ---")
    coords = get_coordinates(file_path)
    for axis, c_dict in coords.items():
        arr = c_dict['data']
        unit = c_dict['unit']
        print(f"Found {axis}: {len(arr)} points | Range: {arr.min():.2f} to {arr.max():.2f} [{unit}]")

    print("\n--- 4. OPTICAL IMAGES & ALIGNMENT ---")
    images = get_optical_context(file_path)
    for name, img_dict in images.items():
        img_array = img_dict['data']
        i_meta = img_dict['meta']
        print(f"Loaded '{name}': {img_array.shape}")
        print(f"  -> Physical Size: {i_meta.get('physical_width'):.2f} x {i_meta.get('physical_height'):.2f} {i_meta.get('unit')}")
        print(f"  -> Origin (X,Y):  ({i_meta.get('origin_x'):.2f}, {i_meta.get('origin_y'):.2f})")
    
        # Optional: Preview image
        # Image.fromarray(img_array).show()


if __name__ == "__main__":
    import sys

    # Demo only. Import the four reader functions from ramanlib instead of running this.
    target = sys.argv[1] if len(sys.argv) > 1 else "0_Ethanol_50x_Map_Rd2_unified.h5"
    _demo(target)
