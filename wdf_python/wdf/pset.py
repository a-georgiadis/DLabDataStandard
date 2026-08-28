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


from struct import unpack
from os import SEEK_SET, SEEK_END, SEEK_CUR
from io import BytesIO
from typing import BinaryIO, Any
from dataclasses import dataclass
from enum import IntFlag, IntEnum
from .predefinedKeys import getKeyName
import datetime
import zlib


_UNIX_EPOCH = datetime.datetime(year=1601, month=1, day=1, tzinfo=datetime.timezone.utc)


class PsetFlags(IntFlag):
    Nil = 0
    Compressed = 0x40
    Array = 0x80
    CustomKey = 0x8000


class PsetType(IntEnum):
    Bool = ord(b'?')
    Char = ord(b'c')
    Short = ord('s')
    Int = ord(b'i')
    Wide = ord(b'w')
    Float = ord(b'r')
    Double = ord(b'q')
    Filetime = ord(b't')
    Pset = ord(b'p')
    Key = ord(b'k')
    Binary = ord(b'b')
    String = ord(b'u')


def windows_filetime_to_datetime(filetime) -> datetime.datetime:
    """Convert a Windows FILETIME value to a Python datetime"""
    return _UNIX_EPOCH + datetime.timedelta(microseconds=filetime / 10)


class PsetParseError(Exception):
    """Exception raise during pset parsing."""
    def __init__(self, message):
        super(PsetParseError, self).__init__(message)


@dataclass
class PsetItem:
    """Representation of an item from a WDF property set.
    Each item is a name:value pair from a limited set of types."""
    type: PsetType
    flags: PsetFlags
    key: int
    _value: Any = None
    _pset: "PsetItem" = None  # cache parsed pset (for PSET_ITEM_PSET)
    _parent: 'Pset' = None  # parent pset (for PSET_ITEM_PSET)
    _count: int = 0

    @property
    def value(self) -> Any:
        """Get the pset item value

        For nested property sets these are parsed and cached as required to avoid
        excessive up-front parsing of data that is never then used."""
        if self.type == PsetType.Pset:
            if not self._pset:
                self._pset = Pset.fromstream(BytesIO(self._value), self._parent, len(self._value))
            return self._pset
        return self._value

    @value.setter
    def value(self, val: Any):
        self._value = val

    @staticmethod
    def fromstream(stream: BinaryIO):
        """Returns an unpacked item from a wdf property set in
        a form appropriate for python.
        An array of data is returned in a tuple."""
        pos = stream.tell()
        data = stream.read(4)
        item = PsetItem(*unpack('<BBH', data))
        count = 1
        if item.flags & PsetFlags.Array:
            count = unpack('<I', stream.read(4))[0]
        is_compressed = (item.flags & PsetFlags.Compressed) != 0
        if item.type == PsetType.Bool:
            item.value = unpack(f'<{count}?', stream.read(1 * count))
        elif item.type == PsetType.Char:
            item.value = unpack(f'<{count}c', stream.read(1 * count))
        elif item.type == PsetType.Short:
            item.value = unpack(f'<{count}h', stream.read(2 * count))
        elif item.type == PsetType.Int:
            item.value = unpack(f'<{count}i', stream.read(4 * count))
        elif item.type == PsetType.Wide:
            item.value = unpack(f'<{count}q', stream.read(8 * count))
        elif item.type == PsetType.Float:
            item.value = unpack(f'<{count}f', stream.read(4 * count))
        elif item.type == PsetType.Double:
            item.value = unpack(f'<{count}d', stream.read(8 * count))
        elif item.type == PsetType.Filetime:
            fileTimes = unpack(f'<{count}Q', stream.read(8 * count))
            item.value = ()
            for fileTime in fileTimes:
                item.value = item._value + (windows_filetime_to_datetime(fileTime),)
        elif item.type == PsetType.String or item.type == PsetType.Key:
            len = unpack('<I', stream.read(4))[0]
            if is_compressed:
                _ = unpack('<I', stream.read(4))[0]  # size of uncompressed data
                data = zlib.decompress(stream.read(len - 4))
                item.value = data.decode('utf-8'),
            else:
                item.value = stream.read(len).decode('utf-8'),
        elif item.type == PsetType.Binary:
            len = unpack('<I', stream.read(4))[0]
            item.value = stream.read(len),
        elif item.type == PsetType.Pset:
            len = unpack('<I', stream.read(4))[0]
            item.value = stream.read(len),
        else:
            raise PsetParseError(f"invalid pset item type '{item.type}' at offset 0x{pos:08x}")
        item._count = count
        if count == 1:
            item.value = item._value[0]  # unpack list if not array or just 1 item
        return item


class Pset:
    """Renishaw WDF file property collection parser."""
    def __init__(self, parent=None):
        self.parent = parent
        self.items = {}  # collection of PsetItem instances
        self.names = {}  # custom key names defined in this pset

    def __getitem__(self, key):
        return self.items[key]

    def __iter__(self):
        for key in self.items.keys():
            yield key, self.items[key]

    @staticmethod
    def is_pset(stream: BinaryIO) -> bool:
        """Test a stream for an embedded property set.
        Reads 4 bytes from the stream. If the result is False it may be necessary
        to reposition the stream seek position"""
        magic = stream.read(4)
        return magic == b'PSET'

    @staticmethod
    def fromstream(stream: BinaryIO, parent: 'Pset' = None, size=None):
        """Parse a stream and return the Pset decoded or None

        If `size` is set to a value this is the length of the pset data in the stream.
        When this is set the `is_pset` check is skipped allowing decoding of nested pset data.
        """
        result = None
        if size or Pset.is_pset(stream):
            if not size:
                size = unpack('<I', stream.read(4))[0]
            final = stream.tell() + size
            result = Pset(parent=parent)
            items = []
            while stream.tell() < final:
                item = PsetItem.fromstream(stream)
                if item.type == PsetType.Key:
                    result.names[item.key] = item.value
                else:
                    items.append(item)
            for item in items:
                if item.key & PsetFlags.CustomKey:
                    name = Pset.custom_key_name(result, item.key)
                else:
                    name = getKeyName(item.key)
                if not name:
                    raise KeyError(f"Key {item.key:#04x} name not found")
                if item.type == PsetType.Pset:
                    item._parent = result
                result.items[name] = item
        return result

    @staticmethod
    def custom_key_name(pset: 'Pset', key: int):
        """Get a custom name for a pset item key recursively.

        Key names may be defined in a parent property to reduce replication among multiple children"""
        if key in pset.names:
            name = pset.names[key]
        elif pset.parent:
            name = Pset.custom_key_name(pset.parent, key)
        else:
            name = None
        return name
