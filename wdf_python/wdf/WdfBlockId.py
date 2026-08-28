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
Block identity values

Renishaw will only use uppercase letter values. Third-parties may
define their own block ids but should use lower-case letter values.
"""


FILE = 0x31464457  # 'W' 'D' 'F' '1'
DATA = 0x41544144  # 'D' 'A' 'T' 'A'
YLIST = 0x54534c59  # 'Y' 'L' 'S' 'T'
XLIST = 0x54534c58  # 'X' 'L' 'S' 'T'
ORIGIN = 0x4e47524f  # 'O' 'R' 'G' 'N'
COMMENT = 0x54584554  # 'T' 'E' 'X' 'T'
WIREDATA = 0x41445857  # 'W' 'X' 'D' 'A'
DATASETDATA = 0x42445857  # 'W' 'X' 'D' 'B'
MEASUREMENT = 0x4d445857  # 'W' 'X' 'D' 'M'
CALIBRATION = 0x53435857  # 'W' 'X' 'C' 'S'
INSTRUMENT = 0x53495857  # 'W' 'X' 'I' 'S'
MAPAREA = 0x50414d57  # 'W' 'M' 'A' 'P'
WHITELIGHT = 0x4c544857  # 'W' 'H' 'T' 'L'
THUMBNAIL = 0x4c49414e  # 'N' 'A' 'I' 'L'
MAP = 0x2050414d  # 'M' 'A' 'P' ' '
CURVEFIT = 0x52414643  # 'C' 'F' 'A' 'R'
COMPONENT = 0x534c4344  # 'D' 'C' 'L' 'S'
PCA = 0x52414350  # 'P' 'C' 'A' 'R'
EM = 0x4552434d  # 'M' 'C' 'R' 'E'
ZELDAC = 0x43444c5a  # 'Z' 'L' 'D' 'C'
RESPONSECAL = 0x4c414352  # 'R' 'C' 'A' 'L'
CAP = 0x20504143  # 'C' 'A' 'P' ' '
PROCESSING = 0x50524157  # 'W' 'A' 'R' 'P'
ANALYSIS = 0x41524157  # 'W' 'A' 'R' 'A'
SPECTRUMLABELS = 0x4C424C57  # 'W' 'L' 'B' 'L'
CHECKSUM = 0x4b484357  # 'W' 'C' 'H' 'K'
RXCALDATA = 0x44435852  # 'R' 'X' 'C' 'D'
RXCALFIT = 0x46435852  # 'R' 'X' 'C' 'F'
XCAL = 0x4C414358  # 'X' 'C' 'A' 'L'
SPECSEARCH = 0x48435253  # 'S' 'R' 'C' 'H'
TEMPPROFILE = 0x504d4554  # 'T' 'E' 'M' 'P'
UNITCONVERT = 0x56434e55  # 'U' 'N' 'C' 'V'
ARPLATE = 0x52505241  # 'A' 'R' 'P' 'R'
ELECSIGN = 0x43454c45  # 'E' 'L' 'E' 'C'
BKXLIST = 0x4c584b42  # 'B' 'K' 'X' 'L'
AUXILARYDATA = 0x20585541  # 'A' 'U' 'X' ' '
CHANGELOG = 0x474c4843  # 'C' 'H' 'L' 'G'
SURFACE = 0x46525553  # 'S' 'U' 'R' 'F'
ARCALPLATE = 0x50435241  # 'A' 'R' 'C' 'P'
PMC = 0x20434d50  # 'P' 'M' 'C' ' '
CAMERAFIXEDFREQDATA = 0x44464643  # 'C' 'F' 'F' 'D'
CLUSTER = 0x53554c43  # 'C' 'L' 'U' 'S'
HIERARCHICALCLUSTER = 0x20414348  # 'H' 'C' 'A' ' '
TEMPPTR = 0x52545054  # 'T' 'P' 'T' 'R'
UNKNOWN = 0x3f4b4e55  # 'U' 'N' 'K' '?'
WMSK = 0x4b534d57  # 'W' 'M' 'S' 'K'
STDV = 0x56445453  # 'S' 'T' 'D' 'V'
EDIT = 0x54494445  # 'E' 'D' 'I' 'T'
WSLS = 0x534c5357  # 'W' 'S' 'L' 'S'
WPAC = 0x43415057  # 'W' 'P' 'A' 'C'
ANY = 0xffffffff  # reserved value for @ref Wdf_FindSection
