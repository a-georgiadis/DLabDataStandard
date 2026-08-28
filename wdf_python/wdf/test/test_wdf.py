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
import struct
import datetime
from tempfile import NamedTemporaryFile
from ..wdf import Wdf, WdfHeader, WdfFlags, MapData, MapAreaFlags
from ..origin import WdfOrigin, WdfDataType, WdfDataUnit
from ..pset import Pset, PsetItem
from .. import WdfBlockId


def _copy(filename, dstfd):
    """Copy a file to the destination file descriptor."""
    with open(filename, 'rb') as srcfd:
        data = None
        while not data or len(data) == 16384:
            data = srcfd.read(16384)
            dstfd.write(data)
    dstfd.seek(0, 0)


class TestWdf(unittest.TestCase):
    testfile = os.path.join(os.path.dirname(__file__), r'Si-map.wdf')

    def test_open(self):
        wdf = Wdf()
        wdf.open(self.testfile)
        wdf.close()

    def test_create(self):
        wdf = Wdf(self.testfile)
        wdf.close()

    def test_with_support(self):
        with Wdf(self.testfile):
            pass

    def test_open_size(self):
        with Wdf(self.testfile) as wdf:
            self.assertEqual(wdf.hdr.signature, WdfBlockId.FILE)
            self.assertEqual(wdf.hdr.nspectra, 88)
            self.assertEqual(wdf.hdr.npoints, 575)
            self.assertEqual(wdf.hdr.size, 512)

    def test_first_spectrum(self):
        with Wdf(self.testfile) as wdf:
            spectrum = wdf.spectrum(0)
            self.assertEqual(wdf.hdr.npoints, len(spectrum))
            self.assertSequenceEqual([1595, 1565, 1590, 1580], [int(x) for x in spectrum[0:4]])

    def test_spectrum_outofrange(self):
        with Wdf(self.testfile) as wdf:
            self.assertRaises(IndexError, wdf.spectrum, len(wdf))

    def test_spectrum_indextype(self):
        with Wdf(self.testfile) as wdf:
            self.assertRaises(TypeError, wdf.spectrum, 1.2)

    def test_wdf_index(self):
        with Wdf(self.testfile) as wdf:
            spectrum = wdf[0]
            self.assertSequenceEqual([1595, 1565, 1590, 1580], [int(x) for x in spectrum[0:4]])

    def test_wdf_index_last(self):
        with Wdf(self.testfile) as wdf:
            spectrum = wdf[-1]
            self.assertSequenceEqual([1612, 1615, 1514, 1553], [int(x) for x in spectrum[0:4]])

    def test_wdf_index_slice(self):
        with Wdf(self.testfile) as wdf:
            points = [int(spectrum[0]) for spectrum in wdf[0:4]]
            self.assertSequenceEqual([1595, 1583, 1640, 2120], points)

    def test_wdf_index_slice_step(self):
        with Wdf(self.testfile) as wdf:
            points = [int(spectrum[0]) for spectrum in wdf[0:6:2]]
            self.assertSequenceEqual([1595, 1640, 1669], points)

    def test_find_block_hdr(self):
        with Wdf(self.testfile) as wdf:
            block, pos = wdf.find_section(WdfBlockId.FILE)
            self.assertEqual(pos, 0)
            self.assertEqual(block.id, WdfBlockId.FILE)
            self.assertEqual(block.size, 512)

    def test_find_block_xlist(self):
        with Wdf(self.testfile) as wdf:
            block = wdf.find_section(WdfBlockId.XLIST)[0]
            self.assertEqual(block.id, WdfBlockId.XLIST)

    def test_find_block_invalid(self):
        with Wdf(self.testfile) as wdf:
            self.assertRaises(EOFError, wdf.find_section, b'_z_z', 0)

    def test_xlist(self):
        with Wdf(self.testfile) as wdf:
            xlist = wdf.xlist()
            self.assertEqual(wdf.hdr.xlistcount, len(xlist))

    def test_comment(self):
        check = 'This is a mapping measurement created by the map setup wizard'
        with Wdf(self.testfile) as wdf:
            comment = wdf.comment()
            self.assertEqual(comment, check)

    def test_sections(self):
        with Wdf(self.testfile) as wdf:
            sections = [section.id for section in wdf.sections()]
            self.assertIn(WdfBlockId.FILE, sections)
            self.assertIn(WdfBlockId.MAPAREA, sections)
            self.assertIn(WdfBlockId.ORIGIN, sections)

    def test_iterator(self):
        with Wdf(self.testfile) as wdf:
            values = [int(x[0]) for x in wdf]
            self.assertEqual(len(values), wdf.hdr.nspectra)

    def test_indexing(self):
        with Wdf(self.testfile) as wdf:
            self.assertEqual(len(wdf[0]), wdf.hdr.npoints)
            self.assertEqual(len(wdf[1]), wdf.hdr.npoints)
            self.assertEqual(len(wdf[-1]), wdf.hdr.npoints)
            self.assertEqual(len(wdf[-2]), wdf.hdr.npoints)
            self.assertRaises(IndexError, wdf.__getitem__, wdf.hdr.nspectra)

    def test_len(self):
        with Wdf(self.testfile) as wdf:
            self.assertEqual(len(wdf), wdf.hdr.nspectra)

    def test_update_spectrum(self):
        with NamedTemporaryFile(suffix=".wdf") as tmpfd:
            _copy(self.testfile, tmpfd)
            with Wdf() as wdf:
                wdf.open_fd(tmpfd)
                expected = [100.0] * wdf.hdr.npoints
                # orig = wdf.spectrum(10)
                wdf.update_spectrum(10, expected)
                new = wdf.spectrum(10)
                self.assertSequenceEqual(new, expected)

    def test_update_spectrum_error_points(self):
        with NamedTemporaryFile(suffix=".wdf") as tmpfd:
            _copy(self.testfile, tmpfd)
            with Wdf() as wdf:
                wdf.open_fd(tmpfd)
                self.assertRaises(struct.error, wdf.update_spectrum, wdf.hdr.nspectra - 1,
                                  [1.0] * (wdf.hdr.npoints - 10))

    def test_update_spectrum_error(self):
        with NamedTemporaryFile(suffix=".wdf") as tmpfd:
            _copy(self.testfile, tmpfd)
            with Wdf() as wdf:
                wdf.open_fd(tmpfd)
                self.assertRaises(IndexError, wdf.update_spectrum, wdf.hdr.nspectra, [1.0] * wdf.hdr.npoints)

    def test_get_map_data(self):
        with Wdf(self.testfile) as wdf:
            testMap = wdf.get_map_data()
            self.assertIsInstance(testMap, MapData)
            self.assertIsInstance(testMap.properties, Pset)
            self.assertEqual(testMap.label, 'Intensity At Point 520')
            self.assertEqual(len(testMap), wdf.hdr.nspectra)
            self.assertIsInstance(testMap[0:-1], tuple)
            # first and last, and 1 in from each end
            self.assertAlmostEqual(testMap[0], 44131.98828125, 6)
            self.assertAlmostEqual(testMap[-1], 44229.421875, 6)
            self.assertAlmostEqual(testMap[1], 43564.88671875, 6)
            self.assertAlmostEqual(testMap[-2], 44257.41796875, 6)
            # check the slice parsing is ok
            self.assertEqual(len(testMap[:]), len(testMap))
            self.assertEqual(len(testMap[0:]), len(testMap))
            self.assertEqual(len(testMap[0::2]), len(testMap) / 2)
            self.assertEqual(len(testMap[-8::2]), 4)

    def test_origins_valid(self):
        with Wdf(self.testfile) as wdf:
            self.assertEqual(len(wdf.origins), 5)
            self.assertIsInstance(wdf.origins[WdfDataType.Spatial_X], WdfOrigin)

    def test_origins_invalid(self):
        with Wdf(self.testfile) as wdf:
            self.assertRaises(KeyError, lambda: wdf.origins[WdfDataType.Pressure])

    def test_map_area(self):
        with Wdf(self.testfile) as wdf:
            area = wdf.map_area
            self.assertAlmostEqual(area.start.x, -7.090, 3)
            self.assertAlmostEqual(area.step.x, 2.0, 3)
            self.assertEqual(area.count.x, 8)
            self.assertEqual(area.flags, MapAreaFlags.NoFlag)

            self.assertEqual(area.count.y, 11)
            self.assertEqual(area.count.z, 0)


class TestWdfHeader(unittest.TestCase):
    """Test WdfHeader fields are parsed correctly."""
    testfile = os.path.join(os.path.dirname(__file__), r'Si-map.wdf')

    def __init__(self, methodName: str) -> None:
        super(TestWdfHeader, self).__init__(methodName)
        with open(self.testfile, 'rb') as testdata:
            data = testdata.read(WdfHeader._size)
            self.hdr = WdfHeader._make(struct.unpack(WdfHeader._packstr, data))

    def test_header_string_fields(self):
        self.assertEqual(self.hdr.title, 'Simple mapping measurement 2')
        self.assertEqual(self.hdr.user, 'Raman')
        self.assertEqual(self.hdr.appname, 'WiRE')
        self.assertEqual(self.hdr.appversion, '3.0.0.0')

    def test_header_times(self):
        self.assertEqual(self.hdr.time_start,
                         datetime.datetime(2005, 10, 27, 13, 54, 51, tzinfo=datetime.timezone.utc))
        self.assertEqual(self.hdr.time_end,
                         datetime.datetime(2005, 10, 27, 13, 58, 55, tzinfo=datetime.timezone.utc))

    def test_header_flags(self):
        self.assertEqual(self.hdr.flags, 0)

    def test_header_fields(self):
        self.assertEqual(str(self.hdr.uuid), '81544741-4838-4849-a34d-0da021ab50d5')

    def test_header_parse_flags(self):
        data = bytearray(512)
        data[0:24] = b'WDF1\1\0\0\0' + b'\0\2\0\0\0\0\0\0' + b'\2\0\0\0\0\0\0\0'
        hdr = WdfHeader._make(struct.unpack(WdfHeader._packstr, data))
        self.assertEqual(hdr.flags, WdfFlags.Checksum)


if __name__ == '__main__':
    unittest.main()
