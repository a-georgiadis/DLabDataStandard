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


"""Renishaw spectroscopy data file accessor classes

Provides access to data from Renishaw spectral data files.
"""


__title__ = "renishaw_wdf"
__version__ = "1.2.0"
__author__ = "Renishaw plc"
__author_email__ = "Raman.Support@renishaw.com"
__license__ = "Apache Software License"


from .wdf import (
    WdfBlock, WdfHeader, WdfIter, Wdf, WdfStream,
    MapAreaFlags, MapArea)
from .wdfenums import (
    WdfFlags, WdfType, WdfSpectrumFlags, WdfScanType)
from .pset import (Pset, PsetType, PsetFlags)
from .origin import (
    WdfOrigin, WdfDataType, WdfDataUnit)
