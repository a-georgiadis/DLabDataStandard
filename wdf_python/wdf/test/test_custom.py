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
from ..wdf import Wdf
from ..custom import CustomEnum, _CUSTOM_FLAG


class F(CustomEnum):
    A = 0x01
    B = 0x02
    C = 0x04
    E = 0x10


class TestCustom(unittest.TestCase):

    def test_single_flag(self):
        """Check a flag is reconstructed from integer input"""
        f = F(2)
        self.assertEqual(f, F.B)

    def test_combined_flags(self):
        """Combinations are denied except the special custom flag bit."""
        self.assertRaises(ValueError, F, 3)

    def test_custom_flag(self):
        """Using the constructor with a custom flag will add the custom enum
        into the collection."""
        f = F(_CUSTOM_FLAG | 1)
        self.assertTrue(f.is_custom())
        self.assertEqual(f, F.Custom1)

    def test_custom_flag_does_not_collide(self):
        """Using the constructor with a custom flag will add the custom enum
        into the collection. The custom values are independent of the standard values."""
        _ = F(_CUSTOM_FLAG | 1)
        g = F(1)
        self.assertFalse(g.is_custom())
        self.assertEqual(g, F.A)

    def test_decompose_single_bit(self):
        expected = [F.A, F.E]
        r = F._decompose(0x19)
        self.assertEqual(r[1], 8)
        self.assertEqual(r[0], expected)

    def test_decompose_multiple_bits(self):
        expected = [F.A, F.E]
        r = F._decompose(0x39)
        self.assertEqual(r[1], 0x28)
        self.assertEqual(r[0], expected)


if __name__ == '__main__':
    unittest.main()
