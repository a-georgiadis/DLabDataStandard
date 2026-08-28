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
import struct
import zlib
from io import BytesIO
from ..pset import Pset, PsetItem, PsetType, PsetFlags


class TestPsetItem(unittest.TestCase):

    def test_bool_zero_is_false(self):
        data = BytesIO(b'?\x00\x01\x80\x00')
        item = PsetItem.fromstream(data)
        self.assertEqual(item.type, PsetType.Bool)
        self.assertEqual(item.key, 0x8001)
        self.assertFalse(item.value)

    def test_bool_is_true(self):
        data = BytesIO(b'?\x00\x01\x80\x01')
        item = PsetItem.fromstream(data)
        self.assertTrue(item.value)

    def test_bool_non_zero_is_true(self):
        data = BytesIO(b'?\x00\x01\x80\xff')
        item = PsetItem.fromstream(data)
        self.assertTrue(item.value)

    def test_bool_array(self):
        data = BytesIO(b'?\x80\x01\x80\x04\x00\x00\x00\xff\x00\x00\x01')
        item = PsetItem.fromstream(data)
        self.assertEqual(len(item.value), 4)
        self.assertSequenceEqual(item.value, (True, False, False, True))

    def test_short(self):
        item = PsetItem.fromstream(BytesIO(b's\x00\x01\x80\x0d\xf0'))
        self.assertEqual(item.type, PsetType.Short)
        self.assertEqual(item.value, -4083)

    def test_int(self):
        item = PsetItem.fromstream(BytesIO(b'i\x00\x01\x80\x04\x03\x02\x01'))
        self.assertEqual(item.type, PsetType.Int)
        self.assertEqual(item.value, 0x01020304)

    def test_float(self):
        item = PsetItem.fromstream(BytesIO(b'r\x00\x01\x80\x00\x00\x80?'))
        self.assertEqual(item.type, PsetType.Float)
        self.assertEqual(item.value, 1.0)

    def test_double(self):
        item = PsetItem.fromstream(BytesIO(b'q\x00\x01\x80\0\0\0\0\0\0\xf0?'))
        self.assertEqual(item.type, PsetType.Double)
        self.assertEqual(item.value, 1.0)

    def test_string(self):
        item = PsetItem.fromstream(BytesIO(b'u\x00\x01\x80\5\0\0\0hello'))
        self.assertEqual(item.type, PsetType.String)
        self.assertEqual(item.value, "hello")

    def test_string_unicode(self):
        data = b'u\x00\x01\x80\x13\0\0\0\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82'
        data = data + b' \xd0\xbc\xd0\xb8\xd1\x80'
        item = PsetItem.fromstream(BytesIO(data))
        self.assertEqual(item.type, PsetType.String)
        self.assertEqual(item.value, "привет мир")

    def test_int_struct(self):
        item = PsetItem.fromstream(BytesIO(struct.pack(
            '<BBHI', PsetType.Int.value, PsetFlags.Nil.value, 0x8001, 1024)))
        self.assertEqual(item.type, PsetType.Int)
        self.assertEqual(item.value, 1024)

    def test_string_compressed(self):
        expected = "testing testing testing"
        data = expected.encode('utf-8')
        zdata = zlib.compress(data)
        stream = struct.pack('<BBHII', PsetType.String.value, PsetFlags.Compressed.value,
                             0x8001, len(zdata) + 4, len(data)) + zdata
        item = PsetItem.fromstream(BytesIO(stream))
        self.assertEqual(item.type, PsetType.String)
        self.assertEqual(item.value, expected)

    def test_key(self):
        item = PsetItem.fromstream(BytesIO(b'k\x00\x01\x80\6\0\0\0\xd0\xbc\xd0\xb8\xd1\x80'))
        self.assertEqual(item.type, PsetType.Key)
        self.assertEqual(item.value, "мир")

    def test_pset(self):
        item = PsetItem.fromstream(BytesIO(b'p\x00\x01\x80\x0d\x00\x00\x00?\0\2\x80\1i\0\3\x80\x0a\0\0\0'))
        self.assertEqual(item.type, PsetType.Pset)
        self.assertEqual(len(item._value), 13)
        stream = BytesIO(item._value)
        subitem1 = PsetItem.fromstream(stream)
        subitem2 = PsetItem.fromstream(stream)
        self.assertEqual(subitem1.type, PsetType.Bool)
        self.assertEqual(subitem2.type, PsetType.Int)
        self.assertEqual(subitem2.key, 0x8003)
        self.assertEqual(subitem2.value, 10)


class TestPset(unittest.TestCase):
    def test_simple_pset(self):
        """Check Pset.fromstream with a simple set that has predefined and custom defined items"""
        stream = BytesIO(b'PSET\x1D\0\0\0u\0\x9B\1\4\0\0\0name?\0\1\x80\1k\0\1\x80\4\0\0\0test')
        pset = Pset.fromstream(stream)
        self.assertEqual(len(pset.items), 2)
        self.assertEqual(pset.items['test'].key, 0x8001)
        self.assertEqual(pset.items['test'].value, True)
        self.assertEqual(pset.items['Label'].value, 'name')

    def test_simple_pset_key_before(self):
        """Check a PSET where a custom key name is defined before the value that uses it."""
        stream = BytesIO(b'PSET\x1D\0\0\0u\0\x9B\1\4\0\0\0namek\0\1\x80\4\0\0\0test?\0\1\x80\xff')
        pset = Pset.fromstream(stream)
        self.assertEqual(len(pset.items), 2)
        self.assertEqual(pset.items['test'].key, 0x8001)
        self.assertEqual(pset.items['test'].value, True)
        self.assertEqual(pset.items['Label'].value, 'name')

    def test_pset_get_item(self):
        stream = BytesIO(b'PSET\x1D\0\0\0u\0\x9B\1\4\0\0\0namek\0\1\x80\4\0\0\0test?\0\1\x80\xff')
        pset = Pset.fromstream(stream)
        self.assertEqual(pset['test'].value, True)
        self.assertEqual(pset['Label'].value, 'name')

    def test_pset_iter(self):
        stream = BytesIO(b'PSET\x1D\0\0\0u\0\x9B\1\4\0\0\0namek\0\1\x80\4\0\0\0test?\0\1\x80\xff')
        pset = Pset.fromstream(stream)
        asdict = dict(pset)
        self.assertIn('test', asdict)

    def test_pset_nested_pset(self):
        stream = BytesIO(b'PSET\x26\0\0\0'  # pset stream header and length
                         + b'k\0\x01\x80\5\0\0\0child'  # child key name item
                         + b'p\0\x01\x80\x11\0\0\0'  # child item header and length
                         + b'?\0\x02\x80\1k\0\x02\x80\4\0\0\0test')  # child items (1 bool and a key name)
        pset = Pset.fromstream(stream)
        self.assertEqual(pset.items['child'].key, 0x8001)
        self.assertEqual(pset.items['child'].type, PsetType.Pset)
        child = pset.items['child'].value
        self.assertEqual(len(child.items), 1)
        self.assertEqual(child.items['test'].key, 0x8002)
        self.assertEqual(child.items['test'].value, True)

    def test_pset_nested_key_in_parent(self):
        stream = BytesIO(b'PSET\x26\0\0\0'  # pset stream header and length
                         + b'k\0\x01\x80\5\0\0\0child'  # child key name
                         + b'k\0\x02\x80\4\0\0\0test'  # child item key name
                         + b'p\0\x01\x80\x05\0\0\0'  # child item header and length
                         + b'?\0\x02\x80\1')  # child item (bool, key name in parent)
        pset = Pset.fromstream(stream)
        self.assertEqual(pset.items['child'].key, 0x8001)
        self.assertEqual(pset.items['child'].type, PsetType.Pset)
        child = pset.items['child'].value
        self.assertEqual(len(child.items), 1)
        self.assertEqual(child.items['test'].key, 0x8002)
        self.assertEqual(child.items['test'].value, True)

    def test_pset_doubly_nested_key_in_parent(self):
        stream = BytesIO(b'PSET\x2e\0\0\0'  # pset stream header and length
                         + b'k\0\x01\x80\5\0\0\0child'  # child key name
                         + b'k\0\x02\x80\4\0\0\0test'  # child item key name
                         + b'p\0\x01\x80\x0d\0\0\0'  # child item header and length
                         + b'p\0\x01\x80\x05\0\0\0'  # child item header and length
                         + b'?\0\x02\x80\1')  # child item (bool, key name in parent)
        pset = Pset.fromstream(stream)
        child1 = pset.items['child'].value
        child2 = child1.items['child'].value
        item = child2.items['test']
        self.assertEqual(item.type, PsetType.Bool)
        self.assertEqual(item.key, 0x8002)
        self.assertEqual(item.value, True)


if __name__ == '__main__':
    unittest.main()
