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
Output per-spectrum data (data origin values) for all collected spectra in a Wdf file
"""

import sys
import os
import argparse
import itertools
import struct

# allow demos to load the wdf package from the parent folder (not required for normal installation)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wdf import Wdf, WdfDataType, WdfSpectrumFlags


def datatype_arg(name: str) -> WdfDataType:
    """Convert a datatype by name into the enum value."""
    return getattr(WdfDataType, name)


def spectrumflags(value: WdfSpectrumFlags) -> str:
    """Convert a WdfSpectrumFlags value into a string."""
    return ", ".join([flag.name for flag in WdfSpectrumFlags if flag.value & value])


def main(args=None):
    """Application entry"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filename', type=str, help="Path to the Wdf file.")
    parser.add_argument(
        'datatype', type=datatype_arg, default=WdfDataType.Time, nargs='?',
        help="Specify the data origin by data type name eg: Spatial_X, Spatial_Y, Flags (default is Time)")
    options = parser.parse_args(args)

    with Wdf(options.filename) as wdf:
        # get the requested data origin
        origin = wdf.origins[options.datatype]
        # Iterate over the collected spectral data and output the data origin value
        # The Flags origin is converted to flag names and the checksum to hex strings.
        for value in itertools.islice(origin, wdf.hdr.ncollected):
            if options.datatype == WdfDataType.Flags:
                value = spectrumflags(WdfSpectrumFlags(value))
            elif options.datatype == WdfDataType.Checksum:
                value = "".join([f"{v:02x}" for v in struct.pack('<Q', value)])
            print(value)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
