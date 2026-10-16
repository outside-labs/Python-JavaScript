import math
import unittest

import JSON as standalone

from JavaScript import Array, JSON, Number, Object, String, undefined


class JSONTests(unittest.TestCase):
    def test_parse_wraps_runtime_values_and_rounds_binary64(self):
        value = JSON.parse('{"items": [{"name": "Ada"}], "big": 9007199254740993, "null": null}')
        self.assertIsInstance(value, Object)
        self.assertIsInstance(value.items, Array)
        self.assertIsInstance(value.items[0].name, String)
        self.assertEqual(value.items[0].name.toUpperCase(), "ADA")
        self.assertEqual(value.big, 2**53)
        self.assertIsNone(value["null"])
        self.assertIs(value.absent, undefined)
        self.assertIs(JSON.parse(True), True)
        self.assertEqual(JSON.parse(12), 12)
        self.assertEqual(standalone.parse("9007199254740993"), 2**53 + 1)
        self.assertIs(type(standalone.parse("[]")), list)
        self.assertEqual(math.copysign(1, JSON.parse('{"x": [-0]}').x[0]), -1)

    def test_parse_failure_and_no_byte_extension(self):
        with self.assertRaises(JSON.JSONDecodeError):
            JSON.parse("{")
        with self.assertRaises(TypeError):
            JSON.parse(b"{}")

    def test_undefined_functions_holes_and_non_finite_numbers(self):
        value = Object({"missing": undefined, "fn": lambda: None, "null": None, "array": Array(1).concat(Array.of(undefined, math.nan, math.inf, -0.0))})
        self.assertEqual(JSON.stringify(value), '{"null":null,"array":[null,null,null,null,0]}')
        self.assertIs(JSON.stringify(), undefined)
        self.assertIs(JSON.stringify(lambda: None), undefined)

    def test_key_order_unicode_and_numeric_rendering(self):
        value = Object({"b": "雪😀", "2": 1.0, "1": "\ud800", "number": 1e-7})
        self.assertEqual(JSON.stringify(value), '{"1":"\\ud800","2":1,"b":"雪😀","number":1e-7}')
        self.assertEqual(JSON.stringify(1e20), "100000000000000000000")
        self.assertEqual(JSON.stringify("\ud83d\ude00"), '"😀"')

    def test_space_and_roundtrip(self):
        value = Object({"x": Array.of(1, Object({"y": True}))})
        text = JSON.stringify(value, None, 2)
        self.assertEqual(text, '{\n  "x": [\n    1,\n    {\n      "y": true\n    }\n  ]\n}')
        self.assertEqual(JSON.stringify(JSON.parse(text)), '{"x":[1,{"y":true}]}')
        self.assertEqual(JSON.stringify(Object(), None, 100), "{}")

    def test_cycles_shared_values_and_unsupported_overloads(self):
        value = Object()
        value.self = value
        with self.assertRaisesRegex(TypeError, "circular"):
            JSON.stringify(value)
        shared = Object({"x": 1})
        self.assertEqual(JSON.stringify(Array.of(shared, shared)), '[{"x":1},{"x":1}]')
        with self.assertRaises(NotImplementedError):
            JSON.stringify({}, lambda key, value: value)
        with self.assertRaises(NotImplementedError):
            JSON.stringify(Object({"toJSON": lambda: 1}))
        with self.assertRaises(TypeError):
            JSON.stringify(object())
