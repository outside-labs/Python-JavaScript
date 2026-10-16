"""Sparse arrays and selected ECMAScript Array algorithms."""

from __future__ import annotations

from functools import cmp_to_key
from reprlib import recursive_repr

from ._object import array_index, ordered_keys
from ._values import (
    callback, integer, is_number, relative_index, same_value_zero, strictEqual,
    to_number, to_string, truthy, undefined,
)


class Array:
    """Identity-based sparse indexed values; use Array.of for one numeric item."""

    __slots__ = ("_items", "_length", "_properties")

    def __init__(self, *values):
        self._items = {}
        self._properties = {}
        self._length = 0
        if len(values) == 1 and is_number(values[0]):
            self.length = values[0]
        else:
            self.push(*values)

    @property
    def length(self):
        return self._length

    @length.setter
    def length(self, value):
        number = to_number(value)
        if not 0 <= number <= 2**32 - 1 or number != int(number):
            raise ValueError("Invalid array length")
        length = int(number)
        for index in list(self._items):
            if index >= length:
                del self._items[index]
        self._length = length

    def __getitem__(self, key):
        key = to_string(key)
        if key == "length":
            return self.length
        index = array_index(key)
        return self._items.get(index, undefined) if index is not None else self._properties.get(key, undefined)

    def __setitem__(self, key, value):
        key = to_string(key)
        if key == "length":
            self.length = value
            return
        index = array_index(key)
        if index is None:
            self._properties[key] = value
        else:
            self._items[index] = value
            self._length = max(self._length, index + 1)

    def __delitem__(self, key):
        key = to_string(key)
        if key == "length":
            raise TypeError("Cannot delete array length")
        index = array_index(key)
        (self._items if index is not None else self._properties).pop(index if index is not None else key, None)

    def __contains__(self, key):
        return self._js_has_own(to_string(key))

    def _js_has_own(self, key):
        index = array_index(key)
        return key == "length" or (index in self._items if index is not None else key in self._properties)

    def _js_entries(self):
        return [(str(i), self._items[i]) for i in sorted(self._items)] + [(key, self._properties[key]) for key in ordered_keys(self._properties)]

    def __iter__(self):
        index = 0
        while index < self.length:
            yield self[index]
            index += 1

    def __len__(self):
        return self.length

    def __bool__(self):
        return True

    @recursive_repr("Array(...)")
    def __repr__(self):
        return f"Array(length={self.length}, items={self._items!r})"

    @recursive_repr("")
    def _js_primitive(self):
        return self.join()

    @classmethod
    def of(cls, *values):
        result = cls()
        result.push(*values)
        return result

    @classmethod
    def from_(cls, source, mapFn=undefined):
        transform = callback(mapFn) if mapFn is not undefined else None
        result = cls()
        for index, value in enumerate(source):
            result.push(transform(value, index) if transform else value)
        return result

    @staticmethod
    def isArray(value):
        return isinstance(value, Array)

    def at(self, index=undefined):
        index = integer(index)
        if index < 0:
            index += self.length
        return self[index] if 0 <= index < self.length else undefined

    def push(self, *values):
        if self.length + len(values) > 2**32 - 1:
            raise ValueError("Invalid array length")
        for value in values:
            self[self.length] = value
        return self.length

    def pop(self):
        if not self.length:
            return undefined
        index = self.length - 1
        value = self[index]
        self._items.pop(index, None)
        self._length -= 1
        return value

    def shift(self):
        if not self.length:
            return undefined
        value = self[0]
        self._items = {i - 1: item for i, item in self._items.items() if i > 0}
        self._length -= 1
        return value

    def unshift(self, *values):
        if self.length + len(values) > 2**32 - 1:
            raise ValueError("Invalid array length")
        self._items = {i + len(values): item for i, item in self._items.items()}
        self._items.update(enumerate(values))
        self._length += len(values)
        return self.length

    def slice(self, start=0, end=undefined):
        length = self.length
        start = relative_index(start, length)
        end = length if end is undefined else relative_index(end, length)
        result = Array(max(end - start, 0))
        for i in range(start, end):
            if i in self._items:
                result[i - start] = self[i]
        return result

    def splice(self, *args):
        if not args:
            return Array()
        start = relative_index(args[0], self.length)
        count = self.length - start if len(args) == 1 else max(0, min(integer(args[1]), self.length - start))
        values = args[2:]
        new_length = self.length - count + len(values)
        if new_length > 2**32 - 1:
            raise ValueError("Invalid array length")
        removed = self.slice(start, start + count)
        items = {i: value for i, value in self._items.items() if i < start}
        items.update({i - count + len(values): value for i, value in self._items.items() if i >= start + count})
        items.update({start + i: value for i, value in enumerate(values)})
        self._items, self._length = items, new_length
        return removed

    def concat(self, *values):
        result = self.slice()
        for value in values:
            if isinstance(value, Array):
                start = result.length
                result.length += value.length
                for i, child in value._items.items():
                    result[start + i] = child
            else:
                result.push(value)
        return result

    def join(self, separator=undefined):
        separator = "," if separator is undefined else to_string(separator)
        return separator.join("" if value is undefined or value is None else to_string(value) for value in self)

    def toString(self):
        return self.join()

    def includes(self, value=undefined, fromIndex=0):
        start = relative_index(fromIndex, self.length)
        return any(same_value_zero(self[i], value) for i in range(start, self.length))

    def indexOf(self, value=undefined, fromIndex=0):
        for i in range(relative_index(fromIndex, self.length), self.length):
            if i in self._items and strictEqual(self[i], value):
                return i
        return -1

    def lastIndexOf(self, value=undefined, *args):
        start = self.length - 1 if not args else integer(args[0])
        if start < 0:
            start += self.length
        start = min(start, self.length - 1)
        if start < 0:
            return -1
        for i in range(start, -1, -1):
            if i in self._items and strictEqual(self[i], value):
                return i
        return -1

    def map(self, function):
        transform = callback(function)
        result = Array(self.length)
        for i in range(self.length):
            if i in self._items:
                result[i] = transform(self[i], i, self)
        return result

    def filter(self, function):
        predicate = callback(function)
        result = Array()
        for i in range(self.length):
            if i in self._items:
                value = self[i]
                if truthy(predicate(value, i, self)):
                    result.push(value)
        return result

    def forEach(self, function):
        visit = callback(function)
        for i in range(self.length):
            if i in self._items:
                visit(self[i], i, self)
        return undefined

    def some(self, function):
        predicate = callback(function)
        return any(i in self._items and truthy(predicate(self[i], i, self)) for i in range(self.length))

    def every(self, function):
        predicate = callback(function)
        return all(i not in self._items or truthy(predicate(self[i], i, self)) for i in range(self.length))

    def _find(self, function, reverse=False):
        predicate = callback(function)
        indices = range(self.length - 1, -1, -1) if reverse else range(self.length)
        for i in indices:
            value = self[i]
            if truthy(predicate(value, i, self)):
                return i, value
        return -1, undefined

    def find(self, function):
        return self._find(function)[1]

    def findIndex(self, function):
        return self._find(function)[0]

    def findLast(self, function):
        return self._find(function, True)[1]

    def findLastIndex(self, function):
        return self._find(function, True)[0]

    def _reduce(self, function, args, reverse=False):
        reducer = callback(function)
        indices = iter(range(self.length - 1, -1, -1) if reverse else range(self.length))
        if args:
            accumulator = args[0]
        else:
            for i in indices:
                if i in self._items:
                    accumulator = self[i]
                    break
            else:
                raise TypeError("Reduce of empty array with no initial value")
        for i in indices:
            if i in self._items:
                accumulator = reducer(accumulator, self[i], i, self)
        return accumulator

    def reduce(self, function, *args):
        return self._reduce(function, args)

    def reduceRight(self, function, *args):
        return self._reduce(function, args, True)

    def reverse(self):
        self._items = {self.length - i - 1: value for i, value in self._items.items()}
        return self

    def fill(self, value=undefined, start=0, end=undefined):
        end = self.length if end is undefined else relative_index(end, self.length)
        for i in range(relative_index(start, self.length), end):
            self[i] = value
        return self

    def sort(self, compareFn=undefined):
        compare = callback(compareFn) if compareFn is not undefined else None
        values = [self._items[i] for i in sorted(self._items) if self._items[i] is not undefined]
        undefined_count = sum(value is undefined for value in self._items.values())
        if compare:
            def order(a, b):
                number = to_number(compare(a, b))
                return -1 if number < 0 else 1 if number > 0 else 0
            values.sort(key=cmp_to_key(order))
        else:
            values.sort(key=lambda value: to_string(value).encode("utf-16-be", "surrogatepass"))
        self._items = dict(enumerate(values + [undefined] * undefined_count))
        return self

    def keys(self):
        index = 0
        while index < self.length:
            yield index
            index += 1

    def values(self):
        return iter(self)

    def entries(self):
        for index in self.keys():
            yield Array.of(index, self[index])
