# Copyright (c) 2022 Renishaw plc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Emit the data for a specified map as columns.

For a standard 2D spatial map the output will be X, Y, value
For a 1D sequence the output will be the varying data origin in column
one and the map value in column two.
"""

import sys
import os
import argparse
import itertools
import struct

# allow demos to load the wdf package from the parent folder (not required for normal installation)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wdf import Wdf, WdfDataType, WdfSpectrumFlags


def main(args=None):
    """Application entry"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filename', type=str, help="Path to the Wdf file.")
    parser.add_argument(
        'mapindex', type=int, default=-1, nargs='?',
        help="Specify the map index. -1 to select the first map in the file (default)")
    options = parser.parse_args(args)

    with Wdf(options.filename) as wdf:
        # Get the map data
        mapdata = wdf.get_map_data(options.mapindex)
        # Obtain a list of the primary data origins. Time or Temperature for time series or
        # temperature series. For a spatial map, Spatial_X, Spatial_Y and possibly Spatial_Z
        # for a 3D volume.
        datatypes = [datatype for datatype in wdf.origins if wdf.origins[datatype].is_primary]
        primary = [wdf.origins[datatype] for datatype in datatypes]
        # Generate a title for the columns
        title = "\t".join([t.name for t in datatypes])
        print(title + "\t Value")
        # Iterate over the collected data and output the values.
        for index in range(wdf.hdr.ncollected):
            for origin in primary:
                print(origin[index], end="\t")
            print(mapdata[index])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
