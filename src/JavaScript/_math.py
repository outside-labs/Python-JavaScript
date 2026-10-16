"""Selected Math functions with ECMAScript numeric edge behavior."""

from __future__ import annotations

import math
import random

from ._values import to_number, undefined


class Math:
    PI = math.pi
    E = math.e
    LN2 = math.log(2)
    LN10 = math.log(10)
    LOG2E = math.log2(math.e)
    LOG10E = math.log10(math.e)
    SQRT1_2 = math.sqrt(0.5)
    SQRT2 = math.sqrt(2)

    @staticmethod
    def abs(value=undefined):
        return abs(to_number(value))

    @staticmethod
    def floor(value=undefined):
        number = to_number(value)
        return float(math.floor(number)) if math.isfinite(number) and number != 0 else number

    @staticmethod
    def ceil(value=undefined):
        number = to_number(value)
        if not math.isfinite(number) or number == 0:
            return number
        return -0.0 if -1 < number < 0 else float(math.ceil(number))

    @staticmethod
    def trunc(value=undefined):
        number = to_number(value)
        if not math.isfinite(number) or number == 0:
            return number
        return math.copysign(float(math.trunc(number)), number)

    @staticmethod
    def round(value=undefined):
        number = to_number(value)
        if not math.isfinite(number) or number == 0:
            return number
        if -0.5 <= number < 0:
            return -0.0
        lower = math.floor(number)
        return float(lower if number - lower < 0.5 else lower + 1)

    @staticmethod
    def sign(value=undefined):
        number = to_number(value)
        return number if math.isnan(number) or number == 0 else math.copysign(1.0, number)

    @staticmethod
    def min(*values):
        result = math.inf
        for value in values:
            number = to_number(value)
            if math.isnan(number):
                return math.nan
            if number < result or (number == result == 0 and math.copysign(1, number) < 0):
                result = number
        return result

    @staticmethod
    def max(*values):
        result = -math.inf
        for value in values:
            number = to_number(value)
            if math.isnan(number):
                return math.nan
            if number > result or (number == result == 0 and math.copysign(1, number) > 0):
                result = number
        return result

    @staticmethod
    def sqrt(value=undefined):
        number = to_number(value)
        return math.nan if number < 0 else math.sqrt(number)

    @staticmethod
    def pow(base=undefined, exponent=undefined):
        base, exponent = to_number(base), to_number(exponent)
        if exponent == 0:
            return 1.0
        if math.isnan(exponent):
            return math.nan
        if abs(base) == 1 and math.isinf(exponent):
            return math.nan
        try:
            return math.pow(base, exponent)
        except OverflowError:
            return -math.inf if base < 0 and exponent.is_integer() and exponent % 2 else math.inf
        except ValueError:
            if base == 0 and exponent < 0:
                return -math.inf if math.copysign(1, base) < 0 and exponent.is_integer() and exponent % 2 else math.inf
            return math.nan

    @staticmethod
    def random():
        return random.random()
