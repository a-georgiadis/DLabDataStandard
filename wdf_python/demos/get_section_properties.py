# Copyright (c) 2023 Renishaw plc.
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
Print all the properties from a specified section in a Renishaw Wdf file.

Demonstrates decoding of nested property sets in Renishaw Wdf data.
"""


import sys
import os
import argparse

# allow demos to load the wdf package from the parent folder (not required for normal installation)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wdf import Wdf, WdfBlockId, PsetType


PSET_CLSID_KEY = '\u0441lsid'


def dump_pset(props, level):
    """Recursively print all properties with indentation."""
    for name, item in props:
        if item.type == PsetType.Pset:
            print(f"{' ' * level}{name}:")
            dump_pset(item.value, level + 2)
        else:
            indent = ' ' * level
            if item.type == PsetType.String and name.startswith("\u0441"):
                name = "clsid"  # \u0441 is a cyrillic 's' and not printable in cp1252 (Windows)
            if item.type == PsetType.Double:
                output = "{0}{1} {2:.3f}".format(indent, name, item.value)
            else:
                output = "{0}{1} {2}".format(indent, name, item.value)
            try:
                print(output)
            except UnicodeEncodeError:
                print(f"error: failed to encode item '{item.type:c}:{item.key:#04x}'"
                      f" to {sys.stdout.encoding}", file=sys.stderr)
    return


def section(name):
    """Convert a string name into a WdfBlockId"""
    return getattr(WdfBlockId, name)


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-f', '--filename', help="Path to the Wdf file.")
    parser.add_argument('-i', '--instrument-state', dest='section', action='store_const',
                        const=WdfBlockId.INSTRUMENT, help="Select the Instrument State section")
    parser.add_argument('-c', '--calibration-state', dest='section', action='store_const',
                        const=WdfBlockId.CALIBRATION, help="Select the Calibration State section.")
    parser.add_argument('-p', '--properties', dest='section', action='store_const',
                        const=WdfBlockId.WIREDATA, help="Select the file properties section.")
    parser.add_argument('-s', '--section', dest='section', type=section,
                        help="Specify a file section by WdfBlockId name (eg: WIREDATA, COMPONENT etc)")
    parser.add_argument('-u', '--uid', dest='uid', type=int, default=-1,
                        help="Optional unique section id (eg: -s MAP -u 2 to read map 2)")
    options = parser.parse_args(args)

    if not options.section:
        options.section = WdfBlockId.WIREDATA

    with Wdf(options.filename) as wdf:
        props = wdf.get_section_properties(options.section, options.uid)
        dump_pset(props, 0)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
