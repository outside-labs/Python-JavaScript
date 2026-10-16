import math
import unittest

from JavaScript import Array, Boolean, Math, Number, String, isFinite, parseFloat, parseInt, strictEqual, typeof, undefined


class StringTests(unittest.TestCase):
    def test_conversion_and_utf16_indexing(self):
        value = String("a😀b")
        self.assertEqual(value.length, 4)
        self.assertEqual(value[1], "\ud83d")
        self.assertEqual(value.at(-2), "\ude00")
        self.assertIs(value[-1], undefined)
        self.assertIs(value["01"], undefined)
        self.assertEqual(value.charAt(20), "")
        self.assertTrue(math.isnan(value.charCodeAt(20)))
        self.assertEqual(value.charCodeAt(1), 0xD83D)
        self.assertEqual(value.codePointAt(1), 0x1F600)
        self.assertEqual(value.codePointAt(2), 0xDE00)
        self.assertIs(value.codePointAt(4), undefined)
        self.assertEqual(list(value), ["a", "😀", "b"])
        self.assertEqual(list(Array.from_(value)), ["a", "😀", "b"])
        self.assertEqual(list(Array.from_("\ud83d\ude00")), ["😀"])
        self.assertTrue(strictEqual("😀", "\ud83d\ude00"))
        self.assertEqual(String(), "")
        self.assertEqual(String(undefined), "undefined")
        self.assertEqual(String(None), "null")

    def test_search_and_substrings_use_code_units(self):
        value = String("a😀b😀")
        self.assertEqual(value.indexOf("😀"), 1)
        self.assertEqual(value.lastIndexOf("😀"), 4)
        self.assertEqual(value.lastIndexOf("😀", 3), 1)
        self.assertEqual(value.indexOf("", math.inf), 6)
        self.assertTrue(value.startsWith("😀", 1))
        self.assertTrue(value.endsWith("b", 4))
        self.assertTrue(value.includes("\ude00"))
        self.assertEqual(value.slice(1, 3), "😀")
        self.assertEqual(value.slice(-2), "😀")
        self.assertEqual(value.substring(3, 1), "😀")
        self.assertEqual(value.substring(-5, 1), "a")

    def test_split_and_constructor_helpers(self):
        self.assertEqual(list(String("😀").split("")), ["\ud83d", "\ude00"])
        self.assertEqual(list(String("a,b,c").split(",", 2)), ["a", "b"])
        self.assertEqual(list(String("a,").split(",")), ["a", ""])
        self.assertEqual(list(String("").split("")), [])
        self.assertEqual(list(String("ab").split()), ["ab"])
        self.assertEqual(list(String("ab").split("", 2**32)), [])
        self.assertEqual(String.fromCharCode(0xD83D, 0xDE00), "😀")
        self.assertEqual(String.fromCodePoint(0x1F600), "😀")
        self.assertEqual(String.fromCharCode(65537), "\x01")
        with self.assertRaises(ValueError):
            String.fromCodePoint(1.5)

    def test_trim_case_concat_and_repeat(self):
        self.assertEqual(String("\ufeff  hi \n").trim(), "hi")
        self.assertEqual(String("\x85hi\x85").trim(), "\x85hi\x85")
        self.assertEqual(String("AbC").toLowerCase().toUpperCase(), "ABC")
        self.assertEqual(String("x").concat(1, None, True), "x1nulltrue")
        self.assertEqual(String("ab").repeat(2.8), "abab")
        with self.assertRaises(ValueError):
            String("a").repeat(-1)


class NumberTests(unittest.TestCase):
    def test_conversion_and_noncoercing_predicates(self):
        self.assertEqual(Number(), 0)
        self.assertEqual(Number("0xff"), 255)
        self.assertTrue(math.isnan(Number(undefined)))
        self.assertEqual(Number(2**53 + 1), 2**53)
        self.assertFalse(Number.isNaN("bad"))
        self.assertTrue(Number.isNaN(math.nan))
        self.assertTrue(isFinite("1"))
        self.assertFalse(Number.isFinite("1"))
        self.assertFalse(Number.isInteger(True))
        self.assertTrue(Number.isInteger(3.0))
        self.assertFalse(Number.isSafeInteger(2**53))
        self.assertEqual(Number(1e-6).toString(), "0.000001")
        self.assertEqual(Number.MIN_VALUE, 5e-324)
        self.assertTrue(Boolean([]))
        self.assertFalse(Boolean(math.nan))

    def test_prefix_parsers(self):
        for value, expected in [("12px", 12), ("0xff", 255), ("010", 10), ("1e3", 1), ("-0", -0.0)]:
            self.assertEqual(parseInt(value), expected)
        self.assertEqual(parseInt("ffz", 16), 255)
        self.assertEqual(Number.parseInt("11", 2), 3)
        self.assertTrue(math.isnan(parseInt("12", 1)))
        self.assertTrue(math.isnan(parseInt("0x")))
        self.assertTrue(math.isnan(parseInt("K", 36)))
        self.assertEqual(parseInt("K", 36), 20)
        self.assertEqual(math.copysign(1, parseInt("-0")), -1)
        self.assertEqual(parseFloat("-1.2e2px"), -120)
        self.assertEqual(parseFloat("1e+"), 1)
        self.assertEqual(parseFloat("0xff"), 0)
        self.assertEqual(Number.parseFloat("Infinity!"), math.inf)
        self.assertTrue(math.isnan(parseFloat("bad")))


class MathTests(unittest.TestCase):
    def test_math_is_a_noncallable_namespace(self):
        self.assertEqual(typeof(Math), "object")
        with self.assertRaises(TypeError):
            Math()

    def test_rounding_and_negative_zero(self):
        self.assertEqual(Math.round(2.5), 3)
        self.assertEqual(Math.round(-1.5), -1)
        self.assertEqual(Math.round(0.49999999999999994), 0)
        for value in (Math.round(-0.5), Math.ceil(-0.2), Math.trunc(-0.2), Math.sign(-0.0), Math.sqrt(-0.0)):
            self.assertEqual(math.copysign(1, value), -1)
        self.assertEqual(Math.floor(-1.1), -2)
        self.assertEqual(Math.ceil(math.inf), math.inf)
        self.assertTrue(math.isnan(Math.round()))

    def test_extrema_domains_and_powers(self):
        self.assertEqual(Math.min(), math.inf)
        self.assertEqual(Math.max(), -math.inf)
        self.assertEqual(math.copysign(1, Math.min(0, -0.0)), -1)
        self.assertEqual(math.copysign(1, Math.max(-0.0, 0)), 1)
        self.assertTrue(math.isnan(Math.max(1, math.nan)))
        self.assertTrue(math.isnan(Math.sqrt(-1)))
        self.assertEqual(Math.pow(math.nan, 0), 1)
        self.assertTrue(math.isnan(Math.pow(1, math.nan)))
        self.assertTrue(math.isnan(Math.pow(1, math.inf)))
        self.assertEqual(Math.pow(-0.0, -3), -math.inf)
        self.assertEqual(Math.pow(-2, 1025), -math.inf)
        self.assertTrue(math.isnan(Math.pow(-1, 0.5)))
        self.assertEqual(Math.abs("-2"), 2)
        self.assertGreaterEqual(Math.random(), 0)
        self.assertLess(Math.random(), 1)
