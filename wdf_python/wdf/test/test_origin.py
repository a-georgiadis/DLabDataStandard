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


import unittest
import os
from datetime import datetime, timezone
from pytest import approx
from ..wdf import Wdf
from ..origin import WdfDataType, WdfDataUnit, WdfOrigin


class TestWdfOrigin(unittest.TestCase):
    testfile = os.path.join(os.path.dirname(__file__), r'Si-map.wdf')

    def test_origin_repr(self):
        with Wdf(self.testfile) as wdf:
            origin = wdf.origins[WdfDataType.Spatial_X]
            self.assertRegex(repr(origin), r"wdf.origin.WdfOrigin\(<[^>]+>, 88, 215231\)")

    def test_origin_str(self):
        with Wdf(self.testfile) as wdf:
            origin = wdf.origins[WdfDataType.Spatial_X]
            expected = r"WdfOrigin(label='X' type='WdfDataType.Spatial_X', units='WdfDataUnit.Micron')"
            self.assertEqual(str(origin), expected)

    def test_origin_instance(self):
        with Wdf(self.testfile) as wdf:
            xorigin = wdf.origins[WdfDataType.Spatial_X]
            self.assertEqual(len(xorigin), wdf.hdr.nspectra)
            self.assertEqual(xorigin.datatype, WdfDataType.Spatial_X)
            self.assertEqual(xorigin.dataunit, WdfDataUnit.Micron)
            self.assertEqual(xorigin.label, 'X')
            self.assertTrue(xorigin.is_primary)
            self.assertEqual(xorigin[0], approx(-7.090))

    def test_origin_slice(self):
        with Wdf(self.testfile) as wdf:
            count = wdf.hdr.nspectra
            origin = wdf.origins[WdfDataType.Flags]
            self.assertEqual(len(origin), count)
            self.assertEqual(len([v for v in origin]), count)
            self.assertEqual(len(origin[0:4]), 4)
            self.assertEqual(len(origin[0:9:2]), 5)
            self.assertEqual(len(origin[0:]), count)
            self.assertEqual(len(origin[0::2]), count // 2)

    def test_origin_type_conversion(self):
        with Wdf(self.testfile) as wdf:
            origin = wdf.origins[WdfDataType.Time]
            self.assertIsInstance(origin[0], datetime)
            self.assertEqual(origin[0], datetime(2005, 10, 27, 13, 54, 51, tzinfo=timezone.utc))

    def test_origin_custom_type(self):
        custom = WdfDataType(0x40000001)  # Custom type with integer 1
        self.assertEqual(custom.name, "Custom1")
        self.assertEqual(custom.value, 0x40000001)
        self.assertIn(custom.name, WdfDataType.__members__, "New enum should be in collection")

    def test_origin_custom_reject_invalid(self):
        self.assertRaises(ValueError, WdfDataType, 0x01000001)


if __name__ == '__main__':
    unittest.main()
