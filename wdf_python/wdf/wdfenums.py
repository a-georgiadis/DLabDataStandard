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


from enum import IntEnum, IntFlag


class WdfFlags(IntFlag):
    NoFlag = 0

    XYXY = (1 << 0)
    """Multiple X list and data blocks exist"""

    Checksum = (1 << 1)
    """checksum is enabled"""

    CosmicRayRemoval = (1 << 2)
    """hardware cosmic ray removal was enabled"""

    Multitrack = (1 << 3)
    """separate x-list for each spectrum"""

    Saturation = (1 << 4)
    """saturated datasets exist"""

    FileBackup = (1 << 5)
    """a complete backup file has been created"""

    Temporary = (1 << 6)
    """this is a temporary file set for Display Title else filename"""

    Slice = (1 << 7)
    """Indicates that file has been extracted from WdfVol file slice like X / Y / Z."""

    PQ = (1 << 8)
    """Indicates that the measurement was performed with a PQ."""


class WdfType(IntEnum):
    Unspecified = 0
    Single = 1
    """file contains a single spectrum"""
    Series = 2
    """file contains multiple spectra with one common data origin (time, depth, temperature etc)"""
    Map = 3
    """file contains multiple spectra with more that one common data origin. Typically area maps
    use X and Y spatial origins. Volume maps use X, Y and Z. The WMAP block normally defines the
    physical region.obeys the maparea object. check scan type for streamline, linefocus, etc."""


class WdfSpectrumFlags(IntFlag):

    NoFlag = 0

    Saturated = (1 << 0)
    """Saturation flag. Some part of the spectrum data was saturated"""

    Error = (1 << 1)
    """Error flag. An error occurred while collecting this spectrum"""

    CosmicRay = (1 << 2)
    """Cosmic ray flag. A cosmic ray was detected and accepted in software"""

    # Error codes for PAF autofocus
    LTSuccess = (1 << 3)
    """LiveTrack signal was successul"""

    PAFSignalError = (1 << 4)
    """PAF signal was insufficient to track focus for this spectrum"""

    PAFTooMuchSpread = (1 << 5)
    """Quality of PAF signal was too poor to track focus for this spectrum"""

    PAFDirectionsDisagree = (1 << 6)
    """PAF prospective moves differed in direction for this spectrum"""

    PAFSafeLimitsExceeded = (1 << 7)
    """PAF prospective move would have exceeded safe limits"""

    SaturationThresholdExceeded = (1 << 8)
    """Too large a number of saturated pixels were present"""

    SoftLimitReached = (1 << 9)
    """LiveTrack is at one of its soft-limits (in 'edge' mode)"""

    PointWasInterpolated = (1 << 10)
    """The z-value information for this point was interpolated from neighbouring points"""


class WdfScanType(IntEnum):
    Unspecified = 0
    """for data that does not represent a spectrum collected from a Renishaw system"""

    Static = 1
    """for single readout off the detector. Can be spectrum or image"""

    Continuous = 2
    """for readouts using continuous extended scanning. Can be spectrum or image
    (unlikely; impossible for x axis readout)"""

    StepRepeat = 3
    """for multiple statics taken at slightly overlapping ranges, then 'stitched'
    together to a single extended spectrum. Can be spectrum or image (unlikely)"""

    FilterScan = 4
    """filter image and filter scan both supported purely for historical reasons"""

    FilterImage = 5

    StreamLine = 6
    """must be a WdfType_Map measurement"""

    StreamLineHR = 7
    """must be a WdfType_Map measurement"""

    Point = 8
    """for scans performed with a point detector"""

    # The values below for multitrack and linefocus are flags that can be ORed with the above integer values
    #   - multitrack discrete on fixed grating systems will only be static
    #   - multitrack discrete could, on a fibre-probe system, be continuous, stitched, or static
    #   - linefocusmapping couild be continuous, stitched, or static, but at time of writing is static

    WdfScanType_MultitrackStitched = 0x0100
    """result is not a multitrack file"""
    WdfScanType_MultitrackDiscrete = 0x0200
    """result is multitrack file (wdf header has multitrack flag set)"""
    WdfScanType_LineFocusMapping = 0x0400
    """Could be Static, Continuous (not yet implemented, impossible for x axis
    readout), or StepAndRepeat (not yet implemented)"""
