"""Adapt the standalone JSON parser to runtime values and serialization rules."""

from __future__ import annotations

import json as _json
import math
from collections.abc import Mapping

import JSON as _standalone

from ._array import Array
from ._object import Object, own_entries
from ._string import String
from ._values import is_number, number_string, to_number, to_string, undefined


def _runtime(value):
    if isinstance(value, dict):
        return Object({key: _runtime(child) for key, child in dict.items(value)})
    if isinstance(value, list):
        return Array.of(*(_runtime(child) for child in value))
    if isinstance(value, str):
        return String(value)
    return to_number(value) if is_number(value) else value


def _quote(value):
    # Delegate escaping to the companion, preserving normal Unicode while
    # escaping lone surrogates as required by well-formed JSON.stringify.
    value = value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")
    quoted = _standalone.stringify(value, ensure_ascii=False)
    return "".join(f"\\u{ord(char):04x}" if 0xD800 <= ord(char) <= 0xDFFF else char for char in quoted)


class _JSON:
    JSONDecodeError = _standalone.JSONDecodeError

    @staticmethod
    def parse(text):
        """Parse JSON after JavaScript string conversion; no reviver overload."""
        if isinstance(text, (bytes, bytearray)):
            raise TypeError("JavaScript.JSON.parse expects text, not bytes")
        def reject_constant(value):
            raise ValueError(f"{value} is not a valid JSON numeric constant")

        # The standalone parser preserves Python integers. Select binary64
        # decoder hooks here so nested -0 and large integers retain JS semantics.
        value = _json.loads(
            to_string(text), parse_int=float, parse_float=float,
            parse_constant=reject_constant,
        )
        return _runtime(value)

    @staticmethod
    def stringify(value=undefined, replacer=undefined, space=undefined):
        """Serialize supported values; replacers and toJSON hooks are not supported."""
        if replacer is not undefined and replacer is not None:
            raise NotImplementedError("JSON replacers are not supported")
        if is_number(space):
            number = to_number(space)
            gap = " " * (0 if math.isnan(number) else int(max(0, min(number, 10))))
        elif isinstance(space, str):
            gap = String(space).slice(0, 10).valueOf()
        else:
            gap = ""
        active = set()

        def encode(child, depth=0):
            if child is undefined or callable(child):
                return undefined
            if child is None:
                return "null"
            if isinstance(child, bool):
                return "true" if child else "false"
            if isinstance(child, str):
                return _quote(child)
            if is_number(child):
                return number_string(child) if math.isfinite(to_number(child)) else "null"
            if not isinstance(child, (Object, Array, Mapping, list, tuple)):
                raise TypeError(f"Unsupported JSON value: {type(child).__name__}")
            if isinstance(child, (Object, Mapping)):
                if any(key == "toJSON" and callable(item) for key, item in own_entries(child)):
                    raise NotImplementedError("JSON toJSON hooks are not supported")
            identity = id(child)
            if identity in active:
                raise TypeError("Converting circular structure to JSON")
            active.add(identity)
            try:
                array = isinstance(child, (Array, list, tuple))
                parts = []
                if array:
                    for item in child:
                        text = encode(item, depth + 1)
                        parts.append("null" if text is undefined else text)
                else:
                    for key, item in own_entries(child):
                        text = encode(item, depth + 1)
                        if text is not undefined:
                            parts.append(_quote(key) + (": " if gap else ":") + text)
                left, right = ("[", "]") if array else ("{", "}")
                if not parts:
                    return left + right
                if not gap:
                    return left + ",".join(parts) + right
                prefix = gap * (depth + 1)
                return left + "\n" + prefix + (",\n" + prefix).join(parts) + "\n" + gap * depth + right
            finally:
                active.remove(identity)

        result = encode(value)
        return result if result is undefined else String(result)


JSON = _JSON()
