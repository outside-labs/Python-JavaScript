"""Number conversion, predicates and prefix parsing."""

from __future__ import annotations

import math
import re
import sys

from ._values import WHITESPACE, is_number, number_string, to_number, to_string, truthy, undefined


class Number(float):
    """Binary64 conversion with selected JavaScript Number static methods."""

    EPSILON = 2**-52
    MAX_SAFE_INTEGER = 2**53 - 1
    MIN_SAFE_INTEGER = -(2**53 - 1)
    MAX_VALUE = sys.float_info.max
    MIN_VALUE = float.fromhex("0x0.0000000000001p-1022")
    NaN = math.nan
    POSITIVE_INFINITY = math.inf
    NEGATIVE_INFINITY = -math.inf

    def __new__(cls, value=0):
        return super().__new__(cls, to_number(value))

    @staticmethod
    def isNaN(value=undefined):
        return is_number(value) and math.isnan(to_number(value))

    @staticmethod
    def isFinite(value=undefined):
        return is_number(value) and math.isfinite(to_number(value))

    @staticmethod
    def isInteger(value=undefined):
        return Number.isFinite(value) and to_number(value).is_integer()

    @staticmethod
    def isSafeInteger(value=undefined):
        return Number.isInteger(value) and abs(to_number(value)) <= Number.MAX_SAFE_INTEGER

    def toString(self):
        from ._string import String
        return String(number_string(self))

    def valueOf(self):
        return float(self)


def Boolean(value=undefined) -> bool:
    return truthy(value)


def parseFloat(value=undefined):
    text = to_string(value).lstrip(WHITESPACE)
    match = re.match(r"[+-]?(?:Infinity|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", text)
    return float(match[0]) if match else math.nan


def parseInt(value=undefined, radix=undefined):
    from ._string import uint32
    text = to_string(value).lstrip(WHITESPACE)
    sign = -1 if text.startswith("-") else 1
    if text.startswith(("-", "+")):
        text = text[1:]
    base = uint32(radix)
    if base >= 2**31:
        base -= 2**32
    if base != 0 and not 2 <= base <= 36:
        return math.nan
    if base in (0, 16) and text.startswith(("0x", "0X")):
        text, base = text[2:], 16
    if base == 0:
        base = 10
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"[:base]
    result = 0
    count = 0
    for char in text.lower():
        if char not in digits:
            break
        result = result * base + digits.index(char)
        count += 1
    if not count:
        return math.nan
    return to_number(result) * sign


Number.parseFloat = staticmethod(parseFloat)
Number.parseInt = staticmethod(parseInt)
