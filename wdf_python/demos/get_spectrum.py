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
Output a spectrum from a Wdf file as xlist and intensity values in two columns.

Demonstrates reading spectral data from the Wdf file
"""

import sys
import os
import argparse

# allow demos to load the wdf package from the parent folder (not required for normal installation)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wdf import Wdf


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filename', type=str, help="Path to the Wdf file.")
    parser.add_argument('spectrum', type=int, help="Spectrum index number")
    options = parser.parse_args(args)

    with Wdf(options.filename) as wdf:
        xlist = wdf.xlist()
        ilist = wdf[options.spectrum]
        for index in range(wdf.hdr.npoints):
            print(f"{xlist[index]:.3f}\t{ilist[index]:.3f}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
