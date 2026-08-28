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


from types import MappingProxyType

_PREDEFINED = MappingProxyType({
    1: "WiRE2 Version",
    2: "ErrorCode",
    3: "CreationTime",
    4: "StartTime",
    5: "EndTime",
    6: "ETA",
    7: "wizardclsid",
    8: "ExpectedDatasetCount",
    9: "AcquisitionCount",
    10: "NumberOfPoints",
    11: "FileHandlerVersion",
    12: "autoSaveInterval",
    13: "MeasurementType",
    14: "responseCalibration",
    15: "restoreInstrumentState",
    16: "closeLaserShutter",
    17: "FocusTrackEnabled",
    18: "FocusTrackInterval",
    19: "LineFocusMode",
    20: "yStepSize",
    201: "DepthSeriesInterval",
    202: "DepthSeriesStartPos",
    203: "DepthSeriesFinalPos",

    301: "ScanCompletionStatus",
    302: "usingPixelIntensityVariationFunction",

    # "Result":400, see 1010
    401: "Results",
    402: "Property",
    403: "Properties",

    410: "Data",  # Map items #
    411: "Label",
    412: "MapType",
    420: "DataList0",
    421: "DataList1",
    422: "DataList2",
    423: "DataList3",
    424: "DataList4",

    430: "Operator",
    431: "Time",
    432: "Version",

    1001: "Name",
    1002: "Description",
    1003: "Language",
    1004: "Code",
    1005: "Status",
    1006: "System",
    1007: "DataFileFormat",
    1008: "DataSaveMode",
    1009: "DataSaveFile",
    1010: "Result",
    1011: "NamedItems",
    1012: "Image",
    1013: "AreaKey",
    1014: "InstrumentState",
    1015: "Laser Name",
    1016: "BeamPath",
    1017: "Focus Mode",
    1018: "Grating Name",
    1019: "Laser",
    1020: "Camera",
    1021: "Instrument",
    1022: "Objective magnification",
    1023: "Objective name",
    # NOTE: these are actually UTF8 encoded strings (they just happen to also be ASCII).
    #       For testing: here is a cyrillic string in utf-8 encoding (privyet).
    1024: b"\xd0\xbf\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82".decode('utf-8')
})


def getKeyName(key):
    """Returns the predefined name for a given key number in a property set present in a wdf file
    Predefined keys use positive key numbers while custom keys use negative numbers."""

    if key in _PREDEFINED:
        name = _PREDEFINED[key]
    else:
        name = None
    return name
