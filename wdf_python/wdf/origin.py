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


import sys
from dataclasses import dataclass
from enum import Enum
from os import SEEK_SET, SEEK_CUR
from io import BytesIO
from struct import unpack
from datetime import datetime, timezone, timedelta
from .custom import CustomEnum
from . import WdfBlockId


_PRIMARY_FLAG = 0x80000000


class WdfDataType(CustomEnum):
    Arbitrary = 0           # < arbitrary type */
    Spectral = 1            # < DEPRECATED: Use Frequency instead (spectral data type) */
    Intensity = 2           # < intensity */
    Spatial_X = 3           # < X position */
    Spatial_Y = 4           # < Y axis position */
    Spatial_Z = 5           # < Z axis (vertical) position */
    Spatial_R = 6           # < rotary stage R axis position */
    Spatial_Theta = 7       # < rotary stage theta angle */
    Spatial_Phi = 8         # < rotary stage phi angle */
    Temperature = 9         # < temperature */
    Pressure = 10           # < pressure */
    Time = 11               # < time */
    Derived = 12            # < derivative type */
    Polarization = 13       # < polarization */
    FocusTrack = 14         # < focus track Z position */
    RampRate = 15           # < temperature ramp rate */
    Checksum = 16           # < spectrum data checksum */
    Flags = 17              # < bit flags */
    ElapsedTime = 18        # < elapsed time intervals */
    Frequency = 19          # < frequency */

    # Microplate mapping origins
    Mp_Well_Spatial_X = 20
    Mp_Well_Spatial_Y = 21
    Mp_LocationIndex = 22
    Mp_WellReference = 23

    # PAF autofocus distance from focus
    PAFZActual = 24         # < PAF distance from focus */
    PAFZError = 25          # < PAF distance between current and last requested positions
    PAFSignalUsed = 26      # < PAF signal used (0 = None, 1 = Top, 2 = Bottom, 3 = Correlation)

    # Calculated exposure time used in exposure time normalisation
    ExposureTime = 27   # < Measured exposure time in microseconds.

    ExternalSignal = 28


class WdfDataUnit(Enum):
    Arbitrary = 0           # < arbitrary units
    RamanShift = 1          # < Raman shift (cm-1)
    Wavenumber = 2          # < wavenumber (nm)
    Nanometre = 3           # < 10-9 metres (nm)
    ElectronVolt = 4        # < electron volts (eV)
    Micron = 5              # < 10-6 metres (µm)
    Counts = 6              # < counts
    Electrons = 7           # < electrons
    Millimetres = 8         # < 10-3 metres (mm)
    Metres = 9              # < metres (m)
    Kelvin = 10             # < degrees Kelvin (K)
    Pascal = 11             # < Pascals (Pa)
    Seconds = 12            # < seconds (s)
    Milliseconds = 13       # < 10-3 seconds (ms)
    Hours = 14
    Days = 15
    Pixels = 16
    Intensity = 17
    RelativeIntensity = 18
    Degrees = 19
    Radians = 20
    Celcius = 21
    Farenheit = 22
    KelvinPerMinute = 23
    FileTime = 24           # < date-time expressed as a Windows FILETIME
    Microseconds = 25       # < 10-6 seconds (µs)
    Volts = 26
    Amps = 27
    MilliAmps = 28
    Strain = 29
    Ohms = 30
    DegreesR = 31
    Coulombs = 32
    PicoCoulombs = 33


class WdfOrigin:
    """Present a Wdf file data origin as a list type object with additional properties.

    The datatype, units, label and a flag for primary origins are provided as properties."""
    _EPOCH = datetime(year=1601, month=1, day=1, tzinfo=timezone.utc)

    def __init__(self, stream: BytesIO, count: int, position: int):
        self._stream = stream  # source of data
        self._count = count  # number of elements stored
        self._position = position  # start of the origin data header
        stream.seek(position, SEEK_SET)
        data = stream.read(24)
        datatype, dataunits = unpack('<II', data[:8])
        self.is_primary = bool(datatype & _PRIMARY_FLAG)
        self.datatype = WdfDataType(datatype & ~_PRIMARY_FLAG)
        self.dataunit = WdfDataUnit(dataunits)
        # truncate the label at the first \0 or end and decode as utf-8
        label = data[8:] + b'\0'
        ndx = label.index(b'\0')
        label = label[:ndx]
        self.label = label.decode('utf-8')

    def __str__(self):
        return f"WdfOrigin(label='{self.label}' type='{self.datatype}', units='{self.dataunit}')"

    def __repr__(self):
        return f"{self.__module__}.{self.__class__.__name__}({self._stream}, {self._count}, {self._position})"

    def __len__(self):
        """Return the number of elements in the data origin."""
        return self._count

    def __getitem__(self, index: int):
        """Return an element of the collection. Supports slices.
        eg: origin[0:10] for the first 10 values,
            origin[::2] for every other value, etc.
        This allows the collection to be iterable as well."""

        if isinstance(index, int):
            start, stop, step = slice(index, index + 1, None).indices(self._count)
        elif isinstance(index, slice):
            start, stop, step = index.indices(self._count)
        else:
            raise TypeError("WdfOrigin indices must be integers or slices")

        self._stream.seek(self._position + 24 + (start * 8), SEEK_SET)
        if step == 1:
            result = self._readvals(stop - start)
        else:
            result = []
            for ndx in range(start, stop, step):
                result.append(self._readvals(1)[0])
                self._stream.seek(step * 8, SEEK_CUR)

        return result if isinstance(index, slice) else result[0]

    def _readvals(self, len: int, format='d'):
        """Read data origin values and convert as appropriate for the type and/or units.

        FileTime data is converted to python datetime objects.
        Flags and Checksum types are read as 64 bit integers. All others are read as floating-point values.
        The 'format' parameter can be used to change the default."""
        if self.dataunit == WdfDataUnit.FileTime \
                or self.datatype == WdfDataType.Flags \
                or self.datatype == WdfDataType.Checksum:
            format = 'Q'
        result = unpack(f"<{len}{format}", self._stream.read(len * 8))
        if self.dataunit == WdfDataUnit.FileTime:
            result = [WdfOrigin._EPOCH + timedelta(microseconds=(t / 10)) for t in result]
        return result


class WdfOriginSet(dict):
    """Provides access to the data origin set from a WDF file.

    The origins are indexed by a DataType value. There can only be one origin for any
    specific DataType. This class reads the origin data from the file on demand."""

    def __init__(self, parent):
        self.parent = parent
        stream = parent.fd
        _ = parent.find_section(WdfBlockId.ORIGIN)
        origin_size = parent.hdr.nspectra * 8
        count = unpack('<I', stream.read(4))[0]
        for _ in range(count):
            origin = WdfOrigin(stream, parent.hdr.nspectra, stream.tell())
            self[origin.datatype] = origin
            stream.seek(origin_size, SEEK_CUR)
