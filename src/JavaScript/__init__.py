"""JavaScript-style objects, methods and functions for Python."""

from ._array import Array
from ._object import Object
from ._values import (
    Infinity,
    NaN,
    isFinite,
    isNaN,
    null,
    strictEqual,
    truthy,
    typeof,
    undefined,
)

__all__ = [
    "Array", "Object",
    "Infinity", "NaN", "isFinite", "isNaN", "null", "strictEqual",
    "truthy", "typeof", "undefined",
]
