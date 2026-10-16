import math
import unittest

from JavaScript import Array, Object, undefined


class ArrayTests(unittest.TestCase):
    def test_constructors_length_holes_and_presence(self):
        value = Array(3)
        self.assertEqual(value.length, 3)
        self.assertEqual(list(value), [undefined] * 3)
        self.assertEqual(list(Object.keys(value)), [])
        value[1] = undefined
        self.assertTrue(Object.hasOwn(value, 1))
        self.assertFalse(Object.hasOwn(value, 0))
        self.assertEqual(list(Array.of(3)), [3])
        self.assertEqual(list(Array(True)), [True])
        self.assertTrue(Array())
        self.assertNotEqual(Array(), Array())
        self.assertTrue(Array.isArray(value))
        self.assertFalse(Array.isArray([]))

    def test_length_validation_truncation_and_sparse_expansion(self):
        value = Array.of(1, 2, 3)
        value.length = 1
        value.length = "4"
        self.assertEqual(list(value), [1, undefined, undefined, undefined])
        self.assertFalse(Object.hasOwn(value, 2))
        value[10] = 8
        self.assertEqual(value.length, 11)
        del value[10]
        self.assertEqual(value.length, 11)
        for length in (-1, 1.5, math.nan, math.inf, 2**32):
            with self.assertRaises(ValueError):
                value.length = length
        self.assertEqual(Array(2**32 - 1).length, 2**32 - 1)

    def test_negative_bracket_is_a_property_and_at_is_relative(self):
        value = Array.of("a", "b")
        self.assertIs(value[-1], undefined)
        value[-1] = "named"
        self.assertEqual(value[-1], "named")
        self.assertEqual(value.at(-1), "b")
        self.assertIs(value.at(-3), undefined)
        self.assertIs(value.at(math.inf), undefined)
        self.assertEqual(value.length, 2)

    def test_mutators_preserve_holes_and_return_javascript_results(self):
        value = Array(2)
        value[1] = 2
        self.assertEqual(value.push(3, 4), 4)
        self.assertEqual(value.pop(), 4)
        self.assertIs(value.shift(), undefined)
        self.assertEqual(value.unshift(0, 1), 4)
        self.assertEqual(list(value), [0, 1, 2, 3])
        self.assertIs(Array().pop(), undefined)
        self.assertIs(Array().shift(), undefined)

    def test_slice_splice_concat_and_fill(self):
        value = Array(4)
        value[1], value[3] = "a", "b"
        sliced = value.slice(0, -1)
        self.assertEqual(sliced.length, 3)
        self.assertEqual(list(Object.keys(sliced)), ["1"])
        removed = value.splice(1, 2, "x", "y", "z")
        self.assertEqual(list(removed), ["a", undefined])
        self.assertFalse(Object.hasOwn(removed, 1))
        self.assertEqual(list(value), [undefined, "x", "y", "z", "b"])
        combined = Array(1).concat(Array.of(1), [2, 3])
        self.assertEqual(combined.length, 3)
        self.assertFalse(Object.hasOwn(combined, 0))
        self.assertEqual(combined[2], [2, 3])
        self.assertIs(value.fill(7, -2), value)
        self.assertEqual(list(value)[-2:], [7, 7])
        self.assertEqual(value.splice().length, 0)

    def test_search_uses_correct_equality_and_hole_rules(self):
        value = Array(1).concat(Array.of(math.nan, True, 1, -0.0, undefined))
        self.assertTrue(value.includes(math.nan))
        self.assertEqual(value.indexOf(math.nan), -1)
        self.assertEqual(value.indexOf(undefined), 5)
        self.assertTrue(Array(1).includes(undefined))
        self.assertEqual(value.indexOf(1), 3)
        self.assertEqual(value.lastIndexOf(undefined), 5)
        self.assertEqual(value.lastIndexOf(undefined, undefined), -1)
        self.assertEqual(value.indexOf(0, -2), 4)
        target = Object()
        self.assertEqual(Array.of(Object(), target).indexOf(target), 1)

    def test_callback_methods_skip_holes_except_find_and_find_last(self):
        value = Array(3)
        value[1] = 2
        mapped = value.map(lambda child: child * 3)
        self.assertEqual(list(Object.keys(mapped)), ["1"])
        self.assertEqual(mapped[1], 6)
        self.assertEqual(list(value.filter(lambda child: True)), [2])
        visited = []
        self.assertIs(value.forEach(lambda child, index: visited.append((child, index))), undefined)
        self.assertEqual(visited, [(2, 1)])
        self.assertTrue(value.every(lambda child: child == 2))
        self.assertTrue(value.some(lambda child: child == 2))
        self.assertEqual(value.findIndex(lambda child: child is undefined), 0)
        self.assertEqual(value.findLastIndex(lambda child: child is undefined), 2)
        self.assertIs(value.findLast(lambda child: child is undefined), undefined)
        self.assertTrue(Array.of(1).some(lambda child: []))
        with self.assertRaises(TypeError):
            Array().map(None)

    def test_callbacks_snapshot_length_and_observe_mutation(self):
        value = Array.of(1, 2, 3)
        seen = []
        def visit(child, index, array):
            seen.append(child)
            if index == 0:
                array[1] = 9
                del array[2]
                array.push(4)
            return child
        mapped = value.map(visit)
        self.assertEqual(seen, [1, 9])
        self.assertEqual(mapped.length, 3)
        self.assertFalse(Object.hasOwn(mapped, 2))

    def test_reductions_distinguish_missing_and_explicit_undefined(self):
        value = Array(1).concat(Array.of(2, 3))
        self.assertEqual(value.reduce(lambda total, child: total + child), 5)
        self.assertEqual(value.reduceRight(lambda total, child: total - child), 1)
        self.assertEqual(value.reduce(lambda total, child: total + child, 10), 15)
        self.assertIs(Array().reduce(lambda total, child: child, undefined), undefined)
        with self.assertRaises(TypeError):
            Array(3).reduce(lambda total, child: child)

    def test_sort_reverse_and_join(self):
        value = Array(1).concat(Array.of(10, 2, undefined, 1))
        self.assertIs(value.sort(), value)
        self.assertEqual(list(value), [1, 10, 2, undefined, undefined])
        self.assertTrue(Object.hasOwn(value, 3))
        self.assertFalse(Object.hasOwn(value, 4))
        self.assertEqual(list(Array.of(10, 2, 1).sort(lambda a, b: a - b)), [1, 2, 10])
        self.assertIs(value.reverse(), value)
        self.assertFalse(Object.hasOwn(value, 0))
        self.assertEqual(Array.of(1, None, undefined, Array.of(2, 3)).join("|"), "1|||2,3")

    def test_from_and_iterators(self):
        self.assertEqual(list(Array.from_(Array(2))), [undefined, undefined])
        self.assertEqual(list(Array.from_([2, 3], lambda value, index: value + index)), [2, 4])
        value = Array.of("a")
        iterator = value.values()
        self.assertEqual(next(iterator), "a")
        value.push("b")
        self.assertEqual(next(iterator), "b")
        self.assertEqual(list(value.keys()), [0, 1])
        self.assertEqual([list(entry) for entry in value.entries()], [[0, "a"], [1, "b"]])

    def test_cycle_repr_and_string_conversion(self):
        value = Array()
        value.push(value)
        self.assertIn("...", repr(value))
        self.assertEqual(value.toString(), "")
