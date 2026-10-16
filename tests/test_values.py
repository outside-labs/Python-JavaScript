import copy
import math
import pickle
import unittest

from JavaScript import isFinite, isNaN, strictEqual, truthy, typeof, undefined
from JavaScript._values import callback, same_value, same_value_zero, to_number, to_string


class ValueTests(unittest.TestCase):
    def test_undefined_is_distinct_and_preserves_identity(self):
        self.assertIsNot(undefined, None)
        self.assertFalse(undefined)
        self.assertEqual(repr(undefined), "undefined")
        for value in (copy.copy(undefined), copy.deepcopy(undefined), pickle.loads(pickle.dumps(undefined))):
            self.assertIs(value, undefined)

    def test_boolean_conversion_uses_javascript_rules(self):
        for value in (undefined, None, False, 0, -0.0, math.nan, ""):
            self.assertFalse(truthy(value), repr(value))
        for value in ([], {}, (), True, "0", "false", math.inf, object()):
            self.assertTrue(truthy(value), repr(value))

    def test_number_conversion_and_numeric_grammar(self):
        for value, result in [(None, 0), (True, 1), ("", 0), (" \ufeff42\n", 42), ("0xff", 255), ("0b11", 3), ("0o10", 8), (".5e2", 50), ([], 0), ([2], 2)]:
            self.assertEqual(to_number(value), result)
        for value in (undefined, "NaN", "inf", "+0xff", "1_000", "\x851", "１２", [1, 2], {}):
            self.assertTrue(math.isnan(to_number(value)), repr(value))
        self.assertEqual(math.copysign(1, to_number("-0")), -1)
        self.assertEqual(to_number(2**53 + 1), 2**53)
        self.assertEqual(to_number(10**400), math.inf)

    def test_string_conversion(self):
        for value, result in [(undefined, "undefined"), (None, "null"), (False, "false"), (-0.0, "0"), (1e-7, "1e-7"), (1e-6, "0.000001"), (1e20, "100000000000000000000"), (1e21, "1e+21"), (math.nan, "NaN"), ({}, "[object Object]"), ([1, None, undefined], "1,,")]:
            self.assertEqual(to_string(value), result)

    def test_equality_relations(self):
        self.assertFalse(strictEqual(True, 1))
        self.assertFalse(strictEqual({}, {}))
        self.assertFalse(strictEqual([], []))
        self.assertFalse(strictEqual(math.nan, math.nan))
        self.assertTrue(strictEqual(0, -0.0))
        self.assertFalse(same_value(0, -0.0))
        self.assertTrue(same_value(math.nan, math.nan))
        self.assertTrue(same_value_zero(math.nan, math.nan))
        self.assertTrue(same_value_zero(0, -0.0))

    def test_typeof_and_coercing_predicates(self):
        for value, name in [(undefined, "undefined"), (None, "object"), (True, "boolean"), (1, "number"), ("", "string"), ([], "object"), (lambda: None, "function")]:
            self.assertEqual(typeof(value), name)
        self.assertTrue(isNaN("bad"))
        self.assertFalse(isNaN(None))
        self.assertTrue(isFinite("12"))
        self.assertFalse(isFinite(math.inf))

    def test_callback_arity_and_errors_are_not_retried(self):
        self.assertEqual(callback(lambda value: value * 2)(3, 0, []), 6)
        self.assertEqual(callback(lambda *args: args)(3, 0), (3, 0))
        calls = []
        def fail(value):
            calls.append(value)
            raise TypeError("from callback body")
        with self.assertRaisesRegex(TypeError, "from callback body"):
            callback(fail)(1, 2, 3)
        self.assertEqual(calls, [1])
        with self.assertRaises(TypeError):
            callback(None)
