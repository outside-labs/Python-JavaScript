import math
import unittest

from JavaScript import Array, Object, undefined


class ObjectTests(unittest.TestCase):
    def test_properties_missing_values_and_identity(self):
        child = Object({"name": "Ada"})
        value = Object({"child": child, "items": 3, "__class__": "data"})
        self.assertIs(value.child, child)
        self.assertEqual(value.items, 3)
        self.assertEqual(value["__class__"], "data")
        self.assertIs(value.__class__, Object)
        self.assertIs(value.missing, undefined)
        self.assertIs(value["missing"], undefined)
        self.assertNotIn("missing", value)
        self.assertIs(Object(value), value)
        self.assertNotEqual(value, Object({"child": child, "items": 3}))
        self.assertTrue(Object())

    def test_mutation_key_conversion_and_safe_names(self):
        value = Object()
        value.name = "Grace"
        value[True] = 1
        value[None] = 2
        value[-0.0] = 3
        value["_properties"] = "user data"
        self.assertEqual(value["true"], 1)
        self.assertEqual(value["null"], 2)
        self.assertEqual(value[0], 3)
        self.assertEqual(value._properties, "user data")
        del value.name
        del value["absent"]
        self.assertIs(value.name, undefined)
        with self.assertRaises(AttributeError):
            value.__class__ = str

    def test_numeric_key_order_and_reinsertion(self):
        value = Object({"b": 1, "10": 2, "2": 3, "01": 4, "0": 5, "4294967295": 6})
        self.assertEqual(list(Object.keys(value)), ["0", "2", "10", "b", "01", "4294967295"])
        del value.b
        value.b = 7
        self.assertEqual(list(Object.keys(value))[-1], "b")
        value["9" * 5000] = "long key"
        self.assertTrue(Object.hasOwn(value, "9" * 5000))

    def test_enumeration_copy_and_from_entries(self):
        child = Object()
        value = Object.assign(Object(), None, {"a": child}, {"a": 2, "b": child})
        self.assertEqual(list(Object.values(value)), [2, child])
        self.assertIs(value.b, child)
        restored = Object.fromEntries(Object.entries(value))
        self.assertIs(restored.b, child)
        self.assertEqual(restored.a, 2)
        self.assertEqual(Object.fromEntries([["a", 1], ["a", 2]]).a, 2)
        self.assertIs(Object.fromEntries([["a"]]).a, undefined)
        self.assertEqual(Object.fromEntries([Object({"0": "x", "1": 4})]).x, 4)
        with self.assertRaises(TypeError):
            Object.fromEntries(["xy"])

    def test_array_and_string_own_properties(self):
        value = Array(3)
        value[1] = undefined
        value["-1"] = 9
        self.assertEqual(list(Object.keys(value)), ["1", "-1"])
        self.assertTrue(Object.hasOwn(value, "length"))
        self.assertFalse(Object.hasOwn(value, 0))
        self.assertTrue(Object.hasOwn(value, 1))
        self.assertEqual(list(Object.keys("😀")), ["0", "1"])
        self.assertEqual(list(Object.values("😀")), ["\ud83d", "\ude00"])
        self.assertTrue(Object.hasOwn("😀", "length"))

    def test_equivalent_utf16_strings_share_one_property_key(self):
        value = Object({"😀": 1})
        value["\ud83d\ude00"] = 2
        self.assertEqual(list(Object.keys(value)), ["😀"])
        self.assertEqual(value["😀"], 2)

    def test_null_errors_and_same_value(self):
        for value in (None, undefined):
            with self.assertRaises(TypeError):
                Object.keys(value)
        self.assertTrue(Object.is_(math.nan, math.nan))
        self.assertFalse(Object.is_(0, -0.0))
        self.assertFalse(Object.is_(Object(), Object()))

    def test_repr_handles_cycles(self):
        value = Object()
        value.self = value
        self.assertIn("...", repr(value))
