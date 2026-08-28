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
Data accessor classes for Renishaw WDF spectral data files.
"""


import struct
import datetime
import copy
from dataclasses import dataclass
from io import BufferedReader, BytesIO, RawIOBase
from collections import namedtuple
from enum import IntFlag, IntEnum
from uuid import UUID
from os import SEEK_SET, SEEK_CUR, SEEK_END
from typing import List, Iterable
from .pset import Pset, windows_filetime_to_datetime
from .origin import WdfOriginSet
from .wdfenums import WdfFlags
from . import WdfBlockId


# All of the fields found in the wdf file header
_FIELDS = [
    'signature', 'version', 'size', 'flags_', 'uuid_',  # 'unused0', 'unused1'
    'ntracks', 'status', 'npoints', 'nspectra', 'ncollected', 'naccum',
    'ylistcount', 'xlistcount', 'origincount', 'appname_',
    'appver_maj', 'appver_min', 'appver_patch', 'appver_build',
    'scantype', 'type', 'time_start_', 'time_end_', 'units',
    'laser_wavenumber', 'user_', 'title_',
    # padding, free, reserved
]


def _tostr(data):
    """Convert a binary buffer with null terminated utf-8 encoded text to a string."""
    try:
        result = data.decode('utf-8').rstrip('\0')
    except UnicodeDecodeError:
        result = u''
    return result


class InvalidSectionError(Exception):
    """Error raised when an attempt is made to open an invalid section."""
    def __init__(self, message):
        super(InvalidSectionError, self).__init__(message)
        self.message = message


@dataclass
class WdfBlock:
    """Representation of the WDF section header structure."""
    id: int  # block type id (see WdfBlockId)
    uid: int  # unique id for this specific block (withing the id type set)
    size: int  # total size of the block (including the header size) in bytes
    position: int  # offset of this block in the file (start of header)
    _psetlen: int = None

    _PACKFMT = '<IIQ'  # decoding format for a block header
    _SIZE = 16  # size of the block header in bytes

    @staticmethod
    def fromstream(stream: BytesIO) -> 'WdfBlock':
        position = stream.tell()
        data = stream.read(WdfBlock._SIZE)
        if len(data) != WdfBlock._SIZE:
            raise IOError()
        id, uid, size = struct.unpack(WdfBlock._PACKFMT, data)
        return WdfBlock(id, uid, size, position)


class WdfHeader(namedtuple('WdfHeader', _FIELDS)):
    """Representation of the WDF file header structure."""
    _packstr = '<IIQQ16s12x IIIQQI III24s4H IIQQI f48x32s160s 48x32x32x'
    _size = 512

    @property
    def appversion(self):
        return "%d.%d.%d.%d" % (self.appver_maj,
                                self.appver_min,
                                self.appver_patch,
                                self.appver_build)

    @property
    def flags(self):
        return WdfFlags(self.flags_)

    @property
    def title(self):
        return _tostr(self.title_)

    @property
    def user(self):
        return _tostr(self.user_)

    @property
    def appname(self):
        return _tostr(self.appname_)

    @property
    def uuid(self) -> UUID:
        return UUID(bytes_le=self.uuid_)

    @property
    def time_start(self) -> datetime.datetime:
        return windows_filetime_to_datetime(self.time_start_)

    @property
    def time_end(self) -> datetime.datetime:
        return windows_filetime_to_datetime(self.time_end_)


class WdfIter:
    """Iterator for spectra in a WDF file."""
    def __init__(self, parent, index=0):
        self.wdf = parent
        self.index = index

    def next(self):
        """Python2 iterator support."""
        return self.__next__()

    def __next__(self):
        if self.index >= self.wdf.hdr.ncollected:
            raise StopIteration
        result = self.wdf[self.index]
        self.index += 1
        return result


class WdfStream(RawIOBase):
    """A stream restricted to the data region for a specified section of a Wdf file.

    If the section has no property set then this stream will start at the first byte after
    the section header and end at size - sizeof(section header).
    If the section contains a property set then this is excluded and the stream starts
    after the pset data."""
    def __init__(self, stream: RawIOBase, section: WdfBlock):
        self.stream = stream
        self.section = section
        self.pos = 0

    def __len__(self):
        return self.section.size

    @staticmethod
    def open(stream: RawIOBase, section: WdfBlock) -> 'WdfStream':
        section = copy.copy(section)  # do not modify the provided section instance
        stream.seek(section.position + WdfBlock._SIZE, SEEK_SET)
        if Pset.is_pset(stream):
            length = struct.unpack('<I', stream.read(4))[0]
            section.position += WdfBlock._SIZE + 4 + 4 + length
            section.size -= WdfBlock._SIZE + 4 + 4 + length
            section._psetlen = length
        else:
            stream.seek(section.position + WdfBlock._SIZE, SEEK_SET)  # restore position
            section.position += WdfBlock._SIZE
            section.size -= WdfBlock._SIZE
        return WdfStream(stream, section)

    def seek(self, offset: int, origin=SEEK_SET):
        if origin == SEEK_SET:
            self.pos = offset
        elif origin == SEEK_CUR:
            self.pos += offset
        elif origin == SEEK_END:
            self.pos = self.section.size + offset
        else:
            raise ValueError(f"Unexpected origin: {origin}")
        if self.pos < 0:
            self.pos = 0
        if self.pos > self.section.size:
            self.pos = self.section.size
        return self.pos

    def read(self, length: int):
        self.stream.seek(self.section.position + self.pos, SEEK_SET)
        data = self.stream.read(
            length if self.pos + length <= self.section.size else self.section.size - self.pos)
        self.pos += len(data)
        return data


class MapData:
    """Represent a map from the file."""

    def __init__(self, fd: BufferedReader, section: WdfBlock):
        self.fd = fd
        self.section = section
        self.fd.seek(section.position + WdfBlock._SIZE)
        self.properties = Pset.fromstream(self.fd)
        self.count = struct.unpack('<Q', self.fd.read(8))[0]
        self.start = self.fd.tell()

    def __len__(self):
        return self.count

    @property
    def label(self):
        return self.properties.items['Label'].value

    @property
    def values(self):
        self.fd.seek(self.start, SEEK_SET)
        return list(struct.unpack(f"<{self.count}f", self.fd.read(self.count * 4)))

    def __getitem__(self, key):
        if isinstance(key, int):
            start, stop, step = slice(key, None, None).indices(self.count)
            stop = start + 1
        elif isinstance(key, slice):
            start, stop, step = key.indices(self.count)
        else:
            raise TypeError("MapData indices must be integers or slices")

        if stop > self.count:
            raise IndexError("MapData index out of range")

        if step == 1:
            # for step 1 use a single read.
            length = stop - start
            self.fd.seek(self.start + (start * 4), SEEK_SET)
            values = struct.unpack(f"<{length}f", self.fd.read(length * 4))
        else:
            values = []
            for index in range(start, stop, step):
                self.fd.seek(self.start + (index * 4), SEEK_SET)
                data = self.fd.read(4)
                values.append(struct.unpack('<f', data)[0])
        return values[0] if len(values) == 1 else tuple(values)


class MapAreaFlags(IntFlag):
    """Set of flags used to defined the layout of map points in a file."""

    NoFlag = 0

    RandomPoints = (1 << 0)
    """File contains random points.
    default (false) is rectangle area, otherwise is random points within a bound"""

    ColumnMajor = (1 << 1)
    """Data collection order. default (false) is X first then Y, otherwise is Y first then X"""

    Alternating = (1 << 2)
    """Data collection order of alternate major axis.
    default (false) is raster, otherwise is snake (alternating)."""

    LineFocusMapping = (1 << 3)
    """Flag marks data collection order using line-focus mapping."""

    # The following two values are deprecated; negative step-size is sufficient information.
    # [Deprecated] InvertedRows = (1 << 4) # True if rows collected right to left
    # [Deprecated] InvertedColumns = (1 << 5) # True if columns collected bottom to top

    SurfaceProfile = (1 << 6)
    """Flag to mark data with irregular Z positions (surface maps)."""

    XYLine = (1 << 7)
    """line or depth slice forming a single line along the XY plane
    length.x contains number of points along line; length.y = 1 """


@dataclass
class FloatVector:
    x: float
    y: float
    z: float

    def __iter__(self):
        yield "x", self.x
        yield "y", self.y
        yield "z", self.z


@dataclass
class IntVector:
    x: int
    y: int
    z: int

    def __iter__(self):
        yield "x", self.x
        yield "y", self.y
        yield "z", self.z


@dataclass
class MapArea:
    start: FloatVector
    step: FloatVector
    count: IntVector
    flags: MapAreaFlags
    lfcount: int

    def __iter__(self):
        yield "start", dict(self.start)
        yield "step", dict(self.step)
        yield "count", dict(self.count)
        yield "flags", self.flags
        yield "lfcount", self.lfcount

    @staticmethod
    def fromstream(stream: BytesIO) -> 'MapArea':
        flags, _ = struct.unpack('<II', stream.read(8))
        startPos = struct.unpack('<fff', stream.read(12))
        stepSize = struct.unpack('<fff', stream.read(12))
        nSteps = struct.unpack('<LLL', stream.read(12))
        lfcount = struct.unpack('<I', stream.read(4))[0]
        return MapArea(FloatVector(*startPos),
                       FloatVector(*stepSize),
                       IntVector(*nSteps),
                       MapAreaFlags(flags),
                       lfcount)


class Wdf:
    """Python accessor class for WDF file data."""
    def __init__(self, path='', mode='rb'):
        self.x = MapAreaFlags.RandomPoints
        self.path = path
        self.fd = None
        self.hdr = None
        self.owned = True
        if path != "":
            self.open(path, mode)

    def __enter__(self):
        return self

    def __exit__(self, vtype, value, traceback):
        self.close()

    def __iter__(self):
        return WdfIter(self)

    def __len__(self):
        return self.hdr.nspectra

    def __getitem__(self, index):
        """return the spectrum at specified index or slice"""
        return self.spectrum(index)

    def open(self, path, mode='rb'):
        """open the specified path as a wdf file.
        mode: provide the file access mode: 'rb' for read-only
        or 'r+b' for read-write"""
        self.open_fd(open(path, mode), owned=True)

    def open_fd(self, fd, owned=False):
        """open the provided file-descriptor as a wdf file."""
        self.fd = fd
        self.owned = owned
        data = self.fd.read(WdfHeader._size)
        self.hdr = WdfHeader._make(struct.unpack(WdfHeader._packstr, data))

    def close(self):
        """close the file descriptor (if owned by this object)"""
        if self.owned:
            self.fd.close()
        self.fd = None

    def spectrum(self, index):
        """Retrieve the unpacked spectrum i-list values.
        If the index is an integer returns a single spectrum as a tuple of floats.
        If the index is a slice object then returns a tuple of tuples for the set
        of specified spectra."""
        if isinstance(index, int):
            start, stop, step = slice(index, None, None).indices(self.hdr.nspectra)
            stop = start + 1
        elif isinstance(index, slice):
            start, stop, step = index.indices(self.hdr.nspectra)
        else:
            raise TypeError("Wdf spectrum index must be an integer or slice")

        if start < 0 or stop > self.hdr.nspectra:
            raise IndexError("Wdf spectrum index out of range")

        size = self.hdr.npoints * 4
        _, pos = self.find_section(WdfBlockId.DATA)
        result = []
        for ndx in range(start, stop, step):
            self.fd.seek(pos + WdfBlock._SIZE + (ndx * size), SEEK_SET)
            data = self.fd.read(size)
            data = struct.unpack(f'{self.hdr.npoints}f', data)
            result.append(data)
        return result[0] if len(result) == 1 else tuple(result)

    def update_spectrum(self, index: int, data: Iterable[float]):
        """Update the i-list for a spectrum.
        data: a sequence of npoints values"""
        if not self.fd.writable:
            raise IOError('WDF object not writable')
        if index < 0 or index >= self.hdr.nspectra:
            raise IndexError('Wdf spectrum index out of range')
        self.find_section(WdfBlockId.DATA)
        self.fd.seek(index * (self.hdr.npoints * 4), SEEK_CUR)
        self.fd.write(struct.pack(f'{self.hdr.npoints}f', *data))

    def xlist(self, track=0):
        """Get the spectral x-list values.
        If the file is a multitrack file then the track may also be specified or will
        default to track 0. When multitrack the xlist block will contain xlistcount * ntracks
        values and we should offset to the correct start point for a specified track.
        For a filter image..."""
        _ = self.find_section(WdfBlockId.XLIST)[0]
        _, _ = struct.unpack('<II', self.fd.read(8))
        count = self.hdr.xlistcount
        if self.hdr.flags & WdfFlags.Multitrack:
            self.fd.seek(count * 4 * track, SEEK_CUR)
        return struct.unpack('<%df' % count, self.fd.read(count * 4))

    def ylist(self):
        """Get the spectral y-list values."""
        block = self.find_section(WdfBlockId.YLIST)[0]
        _, _ = struct.unpack('<II', self.fd.read(8))
        return struct.unpack('<%df' % self.hdr.ylistcount, self.fd.read(block.size - 24))

    def comment(self):
        """Get the file comment block as text."""
        try:
            block = self.find_section(WdfBlockId.COMMENT)[0]
        except EOFError:
            return ""
        size = block.size - WdfBlock._SIZE
        data = self.fd.read(size)
        try:
            result = _tostr(data)
        except UnicodeDecodeError:
            pass
        return result

    def find_section(self, id: int, uid: int = -1, pos=0):
        """Find a Wdf block using its id and optionally the uid.
        On return, the starting file seek position can be specified
        but is at the start of the block data by default.
        The block structure and the position of the start
        of the block is returned"""
        try:
            while True:
                self.fd.seek(pos, SEEK_SET)
                block = WdfBlock.fromstream(self.fd)
                if block.id == id and (uid == -1 or uid == block.uid):
                    return (block, pos)
                pos += block.size
        except IOError:
            pass
        raise EOFError()

    def sections(self) -> List[WdfBlock]:
        """Return a list of sections as (id,uid,size,pos)"""
        pos = 0
        sections = []
        try:
            while True:
                self.fd.seek(pos, SEEK_SET)
                block = WdfBlock.fromstream(self.fd)
                sections.append(block)
                pos += block.size
        except IOError:
            pass
        return sections

    # Checkout numpy.fromfile for reading whole arrays.
    # def read_all(self):
    #    block = self.find_section(b'DATA') # puts file pointer at start of data
    #    npoints = self.hdr.ncollected * self.hdr.npoints
    #    return np.fromfile(self.fd, dtype=float, count=npoints)
    #
    # eg: data = wdf.read_add()
    #     plt.plot(wdf.xlist(), data[wdf.hdr.npoints])

    def get_map_data(self, uid=-1) -> MapData:
        """Returns a MapData object holding information for a Wdf map.
        The uid parameter selects a specific map. If uid is -1 then the first map is returned.
        If no such map is present an InvalidSectionError exception is raised."""
        map_sections = [section for section in self.sections() if section.id == WdfBlockId.MAP]
        valid = [section.uid for section in map_sections]
        if valid and uid == -1:
            uid = valid[0]
        if uid not in valid:
            raise InvalidSectionError(f"map {uid} not present")
        section = [section for section in map_sections if section.uid == uid][0]
        return MapData(self.fd, section)

    def get_section_properties(self, id, uid) -> Pset:
        """If a section has a property collection, returns it else returns None"""
        _ = self.find_section(id, uid)
        return Pset.fromstream(self.fd)

    def get_section_stream(self, id, uid) -> WdfStream:
        """Get the data part of a section.
        If the section has a property set this is skipped over (use get_section_properties to read this)
        and a WdfStream is returned that allows data to be read from the section
        while keeping wihin the defined section area."""
        section, _ = self.find_section(id, uid)
        return WdfStream.open(self.fd, section)

    @property
    def origins(self) -> WdfOriginSet:
        return WdfOriginSet(self)

    @property
    def map_area(self) -> MapArea:
        """Get the map area definition for this file."""
        try:
            _ = self.find_section(WdfBlockId.MAPAREA)[0]
            return MapArea.fromstream(self.fd)
        except EOFError:
            raise EOFError('No map area data present')
