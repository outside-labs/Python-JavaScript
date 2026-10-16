"""Shared ECMAScript value operations for the supported runtime subset."""

from __future__ import annotations

import inspect
import math
import re
from collections.abc import Mapping
from decimal import Decimal


class _Undefined:
    __slots__ = ()
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "undefined"

    def __bool__(self) -> bool:
        return False

    def __reduce__(self):
        return (_Undefined, ())


undefined = _Undefined()
null = None
NaN = math.nan
Infinity = math.inf

# ECMAScript WhiteSpace and LineTerminator code points, including BOM.
WHITESPACE = "\u0009\u000b\u000c\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000\ufeff\u000a\u000d\u2028\u2029"
_DECIMAL = re.compile(r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|Infinity)\Z")


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def truthy(value=undefined) -> bool:
    """JavaScript Boolean conversion; empty containers are true."""
    if value is undefined or value is None or value is False:
        return False
    if is_number(value):
        return value != 0 and not math.isnan(to_number(value))
    if isinstance(value, str):
        return len(value) != 0
    return True


def primitive(value):
    if value is undefined or value is None or isinstance(value, (str, bool, int, float)):
        return value
    method = getattr(type(value), "_js_primitive", None)
    if method is not None:
        result = method(value)
        if result is undefined or result is None or isinstance(result, (str, bool, int, float)):
            return result
        raise TypeError("Cannot convert object to a primitive value")
    if isinstance(value, (list, tuple)):
        return ",".join("" if item is None or item is undefined else to_string(item) for item in value)
    if isinstance(value, Mapping):
        return "[object Object]"
    raise TypeError(f"Unsupported JavaScript value: {type(value).__name__}")


def to_number(value=undefined) -> float:
    value = primitive(value)
    if value is undefined:
        return NaN
    if value is None:
        return 0.0
    if isinstance(value, (bool, int, float)):
        try:
            return float(value)
        except OverflowError:
            return -Infinity if value < 0 else Infinity
    text = value.strip(WHITESPACE)
    if not text:
        return 0.0
    if re.fullmatch(r"0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+", text):
        return to_number(int(text, 0))
    if not _DECIMAL.fullmatch(text):
        return NaN
    return float(text)


def number_string(value) -> str:
    number = to_number(value)
    if math.isnan(number):
        return "NaN"
    if math.isinf(number):
        return "-Infinity" if number < 0 else "Infinity"
    if number == 0:
        return "0"
    text = repr(number)
    if 1e-6 <= abs(number) < 1e21:
        text = format(Decimal(text), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    mantissa, exponent = text.split("e")
    exponent = int(exponent)
    return f"{mantissa.removesuffix('.0')}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"


def to_string(value=undefined) -> str:
    value = primitive(value)
    if value is undefined:
        return "undefined"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")
    return number_string(value)


def integer(value=undefined):
    number = to_number(value)
    if math.isnan(number) or number == 0:
        return 0
    return number if math.isinf(number) else math.trunc(number)


def relative_index(value, length: int) -> int:
    index = integer(value)
    if index < 0:
        return max(length + index, 0)
    return min(index, length)


def strictEqual(left, right) -> bool:
    """ECMAScript strict equality for supported values (objects use identity)."""
    if is_number(left) and is_number(right):
        return to_number(left) == to_number(right)
    if isinstance(left, str) and isinstance(right, str):
        return left.encode("utf-16-le", "surrogatepass") == right.encode("utf-16-le", "surrogatepass")
    return left is right


def same_value(left, right) -> bool:
    if is_number(left) and is_number(right):
        a, b = to_number(left), to_number(right)
        if math.isnan(a) and math.isnan(b):
            return True
        if a == b == 0:
            return math.copysign(1, a) == math.copysign(1, b)
    return strictEqual(left, right)


def same_value_zero(left, right) -> bool:
    return strictEqual(left, right) or (is_number(left) and is_number(right) and math.isnan(to_number(left)) and math.isnan(to_number(right)))


def typeof(value=undefined) -> str:
    if value is undefined:
        return "undefined"
    if value is None:
        return "object"
    if isinstance(value, bool):
        return "boolean"
    if is_number(value):
        return "number"
    if isinstance(value, str):
        return "string"
    return "function" if callable(value) else "object"


def isNaN(value=undefined) -> bool:
    return math.isnan(to_number(value))


def isFinite(value=undefined) -> bool:
    return math.isfinite(to_number(value))


def callback(function):
    """Adapt declared positional arity once, without retrying callback errors."""
    if not callable(function):
        raise TypeError("Callback must be callable")
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return function
    if any(p.kind == p.VAR_POSITIONAL for p in parameters):
        return function
    count = sum(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in parameters)
    return lambda *args: function(*args[:count])
