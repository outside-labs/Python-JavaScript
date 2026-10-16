"""Own enumerable data properties for the initial Object subset."""

from __future__ import annotations

from collections.abc import Mapping
from reprlib import recursive_repr

from ._values import same_value, to_string, undefined


def array_index(key: str) -> int | None:
    if key.isascii() and key.isdecimal() and (key == "0" or not key.startswith("0")):
        # Avoid Python's integer-string digit limit on arbitrary property names.
        if len(key) <= 10:
            number = int(key)
            if number < 2**32 - 1:
                return number
    return None


def ordered_keys(properties) -> list[str]:
    indices = [key for key in properties if array_index(key) is not None]
    names = [key for key in properties if array_index(key) is None]
    return sorted(indices, key=int) + names


def own_entries(value):
    if value is None or value is undefined:
        raise TypeError("Cannot convert undefined or null to object")
    method = getattr(type(value), "_js_entries", None)
    if method is not None:
        return method(value)
    if isinstance(value, Mapping):
        properties = {to_string(key): value[key] for key in value}
        return [(key, properties[key]) for key in ordered_keys(properties)]
    if isinstance(value, str):
        data = value.encode("utf-16-le", "surrogatepass")
        return [(str(i // 2), data[i:i + 2].decode("utf-16-le", "surrogatepass")) for i in range(0, len(data), 2)]
    if isinstance(value, (int, float, bool)):
        return []
    raise TypeError("Expected Object, Array, mapping or primitive")


class Object:
    """An identity-based object containing enumerable, writable data properties.

    Missing properties return undefined. Own keys shadow ordinary attributes;
    use Object.keys(obj) rather than obj.keys() when calling static methods.
    Special Python attributes retain their Python meaning.
    """

    __slots__ = ("_properties",)

    def __new__(cls, value=undefined):
        if isinstance(value, cls):
            return value
        return super().__new__(cls)

    def __init__(self, value=undefined):
        if value is self:
            return
        if value is not None and value is not undefined and not isinstance(value, Mapping):
            raise TypeError("Object() supports mappings, Object, null or undefined")
        object.__setattr__(self, "_properties", {})
        if value is not None and value is not undefined:
            for key, child in own_entries(value):
                self[key] = child

    def __getattribute__(self, name):
        if not (name.startswith("__") and name.endswith("__")):
            properties = object.__getattribute__(self, "_properties")
            if name in properties:
                return properties[name]
        return object.__getattribute__(self, name)

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return undefined

    def __setattr__(self, name, value):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError("Use brackets for special Python names")
        self[name] = value

    def __delattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError("Use brackets for special Python names")
        del self[name]

    def __getitem__(self, key):
        return object.__getattribute__(self, "_properties").get(to_string(key), undefined)

    def __setitem__(self, key, value):
        object.__getattribute__(self, "_properties")[to_string(key)] = value

    def __delitem__(self, key):
        object.__getattribute__(self, "_properties").pop(to_string(key), None)

    def __contains__(self, key):
        return to_string(key) in object.__getattribute__(self, "_properties")

    def __iter__(self):
        return iter(ordered_keys(object.__getattribute__(self, "_properties")))

    def __len__(self):
        return len(object.__getattribute__(self, "_properties"))

    def __bool__(self):
        return True

    def __repr__(self):
        return _object_repr(self)

    def _js_entries(self):
        properties = object.__getattribute__(self, "_properties")
        return [(key, properties[key]) for key in ordered_keys(properties)]

    def _js_primitive(self):
        return "[object Object]"

    def toString(self):
        return "[object Object]"

    @staticmethod
    def keys(value):
        from ._array import Array
        return Array.of(*(key for key, _ in own_entries(value)))

    @staticmethod
    def values(value):
        from ._array import Array
        return Array.of(*(child for _, child in own_entries(value)))

    @staticmethod
    def entries(value):
        from ._array import Array
        return Array.of(*(Array.of(key, child) for key, child in own_entries(value)))

    @staticmethod
    def assign(target, *sources):
        if not isinstance(target, Object):
            raise TypeError("assign target must be an Object")
        for source in sources:
            if source is not None and source is not undefined:
                for key, value in own_entries(source):
                    target[key] = value
        return target

    @staticmethod
    def fromEntries(entries):
        from ._array import Array
        result = Object()
        for entry in entries:
            if isinstance(entry, (Object, Array)):
                key, value = entry[0], entry[1]
            elif isinstance(entry, Mapping):
                properties = dict(own_entries(entry))
                key, value = properties.get("0", undefined), properties.get("1", undefined)
            elif isinstance(entry, (list, tuple)):
                key = entry[0] if entry else undefined
                value = entry[1] if len(entry) > 1 else undefined
            else:
                raise TypeError("Iterator entry must be an object") from None
            result[key] = value
        return result

    @staticmethod
    def hasOwn(value, key):
        if value is None or value is undefined:
            raise TypeError("Cannot convert undefined or null to object")
        method = getattr(type(value), "_js_has_own", None)
        if method is not None:
            return method(value, to_string(key))
        return to_string(key) in {name for name, _ in own_entries(value)}

    is_ = staticmethod(same_value)


@recursive_repr("Object({...})")
def _object_repr(value):
    return f"Object({object.__getattribute__(value, '_properties')!r})"
