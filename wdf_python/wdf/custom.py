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


from enum import Enum
from types import MappingProxyType


_CUSTOM_FLAG = 0x40000000


class CustomEnum(Enum):
    """Enum class that allows for on-demand additional items that use the custom bit set"""

    def is_custom(self):
        """Returns true if the enumeration value is a custom value."""
        return self.value & _CUSTOM_FLAG == _CUSTOM_FLAG

    @classmethod
    def _missing_(cls, value):
        """Returns member (possibly creating it) if one can be found for value"""
        if not isinstance(value, int):
            raise ValueError("%r is not a valid %s" % (value, cls.__qualname__))
        iscustom = value & _CUSTOM_FLAG == _CUSTOM_FLAG
        if not iscustom:
            raise ValueError("%r is not a valid custom %s" % (value, cls.__qualname__))
        new_member = cls._create_pseudo_member(value)
        return new_member

    @classmethod
    def _create_pseudo_member(cls, value):
        """Create a custom member on demand"""
        member = cls._value2member_map_.get(value, None)
        if member is None:
            # Ensure we have the custom flag
            _, extra_flags = cls._decompose(value)
            if extra_flags & _CUSTOM_FLAG != _CUSTOM_FLAG:
                raise ValueError("%r is not a valid %s" % (value, cls.__qualname__))
            # construct a new member
            member = object.__new__(cls)
            member._name_ = "Custom%d" % (value & ~_CUSTOM_FLAG)
            member._value_ = value
            # use setdefault in case another thread already created a composite
            # with this value
            member = cls._value2member_map_.setdefault(value, member)
            # add the on-demand member into the enum type
            setattr(cls, member._name_, member)
            cls._member_map_[member._name_] = member
            cls._member_names_.append(member._name_)
        return member

    @classmethod
    def _decompose(cls, value):
        """Check the bits set in value and match with defined flags in the provided class.
        Returns a tuple with the matched flags and the unmatched bits in the second part."""
        matched = [m for m in cls if (value & m.value) == m.value]
        mask = 0
        for flag in matched:
            mask |= flag.value
        unmatched = value & ~mask
        return matched, unmatched
