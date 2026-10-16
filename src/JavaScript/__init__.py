"""JavaScript-style objects, methods and functions for Python."""

from ._array import Array
from ._json import JSON
from ._math import Math
from ._number import Boolean, Number, parseFloat, parseInt
from ._object import Object
from ._string import String
from fetch_api import FetchError, Headers, Promise, Request, Response, fetch
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
    "Array", "Boolean", "FetchError", "Headers", "JSON", "Math", "Number",
    "Object", "Promise", "Request", "Response", "String", "fetch", "parseFloat", "parseInt",
    "Infinity", "NaN", "isFinite", "isNaN", "null", "strictEqual",
    "truthy", "typeof", "undefined",
]
