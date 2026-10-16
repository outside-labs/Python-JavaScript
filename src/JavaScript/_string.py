"""Selected String methods using JavaScript UTF-16 code-unit indexing."""

from __future__ import annotations

import math

from ._array import Array
from ._values import WHITESPACE, integer, relative_index, to_number, to_string, undefined


def units(value: str) -> str:
    data = value.encode("utf-16-le", "surrogatepass")
    return "".join(chr(int.from_bytes(data[i:i + 2], "little")) for i in range(0, len(data), 2))


def from_units(value: str) -> str:
    return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def uint32(value):
    number = to_number(value)
    return math.trunc(number) % 2**32 if math.isfinite(number) and number else 0


def clamp(value, length):
    return max(0, min(integer(value), length))


class String(str):
    """A Python string exposing selected camelCase JavaScript String methods.

    JavaScript methods and bracket access use UTF-16 code units. Python's
    inherited operators and methods otherwise retain their Python behavior.
    """

    def __new__(cls, value=""):
        return super().__new__(cls, to_string(value))

    @property
    def length(self):
        return len(self.encode("utf-16-le", "surrogatepass")) // 2

    def __getitem__(self, key):
        key = to_string(key)
        if key == "length":
            return self.length
        if not key.isascii() or not key.isdecimal() or (len(key) > 1 and key.startswith("0")) or len(key) > 10:
            return undefined
        return self.at(int(key))

    def __iter__(self):
        return iter(from_units(units(self)))

    def at(self, index=undefined):
        index = integer(index)
        data = units(self)
        if index < 0:
            index += len(data)
        return String(data[index]) if 0 <= index < len(data) else undefined

    def charAt(self, index=undefined):
        index = integer(index)
        data = units(self)
        return String(data[index]) if 0 <= index < len(data) else String()

    def charCodeAt(self, index=undefined):
        value = self.charAt(index)
        return ord(value) if value else math.nan

    def codePointAt(self, index=undefined):
        index = integer(index)
        data = units(self)
        if not 0 <= index < len(data):
            return undefined
        first = ord(data[index])
        if 0xD800 <= first <= 0xDBFF and index + 1 < len(data):
            second = ord(data[index + 1])
            if 0xDC00 <= second <= 0xDFFF:
                return (first - 0xD800) * 0x400 + second - 0xDC00 + 0x10000
        return first

    def slice(self, start=0, end=undefined):
        data = units(self)
        start = relative_index(start, len(data))
        end = len(data) if end is undefined else relative_index(end, len(data))
        return String(from_units(data[start:end]))

    def substring(self, start=0, end=undefined):
        data = units(self)
        start = clamp(start, len(data))
        end = len(data) if end is undefined else clamp(end, len(data))
        start, end = min(start, end), max(start, end)
        return String(from_units(data[start:end]))

    def indexOf(self, searchString=undefined, position=0):
        data = units(self)
        return data.find(units(to_string(searchString)), clamp(position, len(data)))

    def lastIndexOf(self, searchString=undefined, position=undefined):
        data, search = units(self), units(to_string(searchString))
        number = to_number(position)
        start = len(data) if math.isnan(number) else clamp(number, len(data))
        return data.rfind(search, 0, min(start + len(search), len(data)))

    def includes(self, searchString=undefined, position=0):
        return self.indexOf(searchString, position) >= 0

    def startsWith(self, searchString=undefined, position=0):
        data = units(self)
        return data.startswith(units(to_string(searchString)), clamp(position, len(data)))

    def endsWith(self, searchString=undefined, endPosition=undefined):
        data = units(self)
        end = len(data) if endPosition is undefined else clamp(endPosition, len(data))
        return data[:end].endswith(units(to_string(searchString)))

    def split(self, separator=undefined, limit=undefined):
        count = 2**32 - 1 if limit is undefined else uint32(limit)
        if count == 0:
            return Array()
        if separator is undefined:
            return Array.of(String(self))
        data, separator = units(self), units(to_string(separator))
        if separator == "":
            return Array.of(*(String(char) for char in data[:count]))
        return Array.of(*(String(from_units(part)) for part in data.split(separator, count)[:count]))

    def concat(self, *values):
        return String(str(self) + "".join(to_string(value) for value in values))

    def repeat(self, count=0):
        count = integer(count)
        if count < 0 or math.isinf(count):
            raise ValueError("Invalid repeat count")
        return String(str(self) * count)

    def trim(self):
        return String(str(self).strip(WHITESPACE))

    def trimStart(self):
        return String(str(self).lstrip(WHITESPACE))

    def trimEnd(self):
        return String(str(self).rstrip(WHITESPACE))

    def toLowerCase(self):
        return String(str(self).lower())

    def toUpperCase(self):
        return String(str(self).upper())

    def toString(self):
        return self

    def valueOf(self):
        return str(self)

    @staticmethod
    def fromCharCode(*codes):
        return String(from_units("".join(chr(uint32(code) % 2**16) for code in codes)))

    @staticmethod
    def fromCodePoint(*codes):
        values = []
        for code in codes:
            number = to_number(code)
            if not math.isfinite(number) or number != int(number) or not 0 <= number <= 0x10FFFF:
                raise ValueError("Invalid code point")
            values.append(chr(int(number)))
        return String("".join(values))
