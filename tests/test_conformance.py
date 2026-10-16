"""Compare independent native-JavaScript fixtures with Python observations."""

import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest

from JavaScript import Array, Boolean, JSON, Math, Number, Object, String, parseFloat, parseInt, strictEqual, typeof, undefined


def encode(value):
    if value is undefined:
        return {"type": "undefined"}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, (int, float)):
        if math.isnan(value):
            value = "NaN"
        elif math.isinf(value):
            value = "Infinity" if value > 0 else "-Infinity"
        elif value == 0 and math.copysign(1, value) < 0:
            value = "-0"
        return {"type": "number", "value": value}
    if isinstance(value, str):
        # Canonicalize equivalent Python astral and explicit surrogate sequences.
        value = value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")
        return {"type": "string", "value": value}
    if isinstance(value, (Array, list, tuple)):
        entries = Object.entries(value) if isinstance(value, Array) else enumerate(value)
        return {"type": "array", "length": len(value), "items": [[str(key), encode(child)] for key, child in entries]}
    entries = Object.entries(value) if isinstance(value, Object) else value.items()
    return {"type": "object", "entries": [[key, encode(child)] for key, child in entries]}


def observations():
    cases = {}
    values = [undefined, None, False, True, 0, -0.0, math.nan, math.inf, -math.inf,
              "", "0", "false", "  \ufeff42\n", "0xff", "-0x1", "0b11", "0o10", ".5e2", "1_000",
              "inf", "\x851", "１２", Array(), Array.of(1), Array.of(1, 2), Object()]
    cases["conversion"] = [[Boolean(value), Number(value), String(value), typeof(value)] for value in values]
    cases["equality"] = [strictEqual(1, True), strictEqual(math.nan, math.nan), strictEqual(0, -0.0), Object.is_(0, -0.0), Object.is_(math.nan, math.nan), strictEqual(Object(), Object()), strictEqual("😀", "\ud83d\ude00")]
    cases["namespace"] = [typeof(Math), typeof(JSON), typeof(Number), Object.hasOwn("😀", "length")]
    unicode_object = Object({"😀": 1})
    unicode_object["\ud83d\ude00"] = 2
    cases["unicodeKeys"] = [Object.keys(unicode_object), unicode_object["😀"], Array.from_("\ud83d\ude00")]
    obj = Object({"b": 1, "10": 2, "2": 3, "01": 4, "0": 5, "4294967295": 6})
    cases["objectOrder"] = Object.entries(obj)
    del obj.b
    obj.b = 7
    cases["objectReinsert"] = Object.keys(obj)
    cases["objectCopy"] = Object.assign(Object(), {"a": 1}, None, undefined, {"a": 2, "b": 3})
    cases["fromEntries"] = Object.fromEntries([["a", 1], ["a", 2], ["b"]])
    sparse = Array(4)
    sparse[1], sparse[3] = undefined, 4
    cases["sparse"] = sparse
    cases["sparseMap"] = sparse.map(lambda value, index: Array.of(value, index))
    cases["sparseFilter"] = sparse.filter(lambda: True)
    cases["sparseFind"] = [sparse.findIndex(lambda value: value is undefined), sparse.findLastIndex(lambda value: value is undefined)]
    cases["sparseSearch"] = [sparse.includes(undefined), sparse.indexOf(undefined), sparse.lastIndexOf(undefined), sparse.lastIndexOf(undefined, undefined)]
    cases["sparseSlice"] = sparse.slice(0, -1)
    spliced = sparse.slice()
    cases["sparseSpliceRemoved"] = spliced.splice(1, 2, "x", "y", "z")
    cases["sparseSpliceResult"] = spliced
    cases["sparseReverse"] = sparse.slice().reverse()
    cases["sparseSort"] = Array(1).concat(Array.of(10, 2, undefined, 1)).sort()
    cases["numericSort"] = Array.of(10, 2, 1).sort(lambda a, b: a - b)
    cases["arraySearch"] = [Array.of(1, True, math.nan, 0, undefined).indexOf(value) for value in [math.nan, True, 1, -0.0, undefined]]
    cases["arrayIncludes"] = [Array.of(1, True, math.nan, 0).includes(value) for value in [math.nan, True, 1, -0.0, undefined]]
    mutated, seen = Array.of(1, 2, 3), []
    def visit(value, index, array):
        seen.append(value)
        if index == 0:
            array[1] = 9
            del array[2]
            array.push(4)
        return value
    cases["callbackMutation"] = mutated.map(visit)
    cases["callbackSeen"] = seen
    cases["reduce"] = [sparse.reduce(lambda total, value: total + (value if Boolean(value) else 0), 0), Array.of(2, 3).reduceRight(lambda a, b: a - b)]
    cases["fromSparse"] = Array.from_(Array(2))
    cases["join"] = Array.of(1, None, undefined, Array.of(2, 3)).join("|")
    cases["arrayPredicates"] = [Array().every(lambda: False), Array().some(lambda: True), Array.of(1).some(lambda: Array()), Array.isArray(Array()), Array.isArray(Object())]
    text = String("a😀b😀")
    cases["stringIndex"] = [text.length, text[1], text[-1], text.at(-1), text.charAt(20), text.charCodeAt(20), text.charCodeAt(1), text.codePointAt(1), text.codePointAt(2)]
    cases["stringSearch"] = [text.indexOf("😀"), text.lastIndexOf("😀"), text.lastIndexOf("😀", 3), text.indexOf("", math.inf), text.startsWith("😀", 1), text.endsWith("b", 4), text.includes("\ude00")]
    cases["stringSlice"] = [text.slice(1, 3), text.slice(-2), text.substring(3, 1), text.substring(-5, 1)]
    cases["stringSplit"] = [String("😀").split(""), String("a,b,c").split(",", 2), String("a,").split(","), String("").split(""), String("ab").split(), String("ab").split("", 2**32)]
    cases["stringConstructors"] = [String.fromCharCode(0xD83D, 0xDE00), String.fromCharCode(65537), String.fromCodePoint(0x1F600), Array.from_(text)]
    cases["stringOther"] = [String("\ufeff  hi \n").trim(), String("\x85hi\x85").trim(), String("Straße").toUpperCase(), String("AbC").toLowerCase(), String("ab").repeat(2.8)]
    cases["stringBoundary"] = [String("abc").lastIndexOf("", 0), String("abc").lastIndexOf("", -1), String("abc").lastIndexOf("", math.nan), String("abc").substring(math.inf, -math.inf)]
    nums = [undefined, None, True, "1", math.nan, math.inf, -0.0, 3.5, 3, 2**53 - 1, 2**53]
    cases["numberPredicates"] = [[Number.isNaN(value), Number.isFinite(value), Number.isInteger(value), Number.isSafeInteger(value)] for value in nums]
    cases["parseInt"] = [parseInt(value) for value in ["12px", "0xff", "010", "1e3", "-0", "bad", "0x"]]
    cases["parseRadix"] = [parseInt(text, radix) for text, radix in [("ffz", 16), ("11", 2), ("12", 1), ("z", 36), ("0b11", 0), ("K", 36), ("K", 36)]]
    cases["parseFloat"] = [parseFloat(value) for value in ["-1.2e2px", "1e+", "0xff", "Infinity!", "bad"]]
    rounding = [-math.inf, -2.5, -1.5, -0.5, -0.2, -0.0, 0, 0.49999999999999994, 0.5, 1.5, math.inf, math.nan]
    cases["mathRounding"] = [[Math.floor(value), Math.ceil(value), Math.trunc(value), Math.round(value), Math.sign(value)] for value in rounding]
    cases["mathExtrema"] = [Math.min(), Math.max(), Math.min(0, -0.0), Math.max(-0.0, 0), Math.min(math.nan, 1), Math.sqrt(-1), Math.sqrt(-0.0)]
    powers = [(math.nan, 0), (1, math.nan), (1, math.inf), (-1, math.inf), (-0.0, -3), (-2, 1025), (-1, .5), (-math.inf, 3), (-math.inf, -3), (0, -math.inf)]
    cases["mathPow"] = [Math.pow(base, exponent) for base, exponent in powers]
    cases["numberString"] = [String(value) for value in [1e-7, 1e-6, 1e20, 1e21, 5e-324, -0.0, 9007199254740993]]
    cases["jsonParse"] = JSON.parse('{"items":[{"name":"Ada"}],"big":9007199254740993,"zero":-0}')
    cases["jsonOmit"] = JSON.stringify(Object({"missing": undefined, "fn": lambda: None, "null": None, "array": Array(1).concat(Array.of(undefined, math.nan, math.inf, -0.0))}))
    cases["jsonUnicode"] = JSON.stringify(Object({"b": "雪😀", "2": 1, "1": "\ud800", "number": 1e-7}))
    cases["jsonSpace"] = JSON.stringify(Object({"x": Array.of(1, Object({"y": True}))}), None, 2)
    cases["jsonTop"] = [JSON.stringify(undefined), JSON.stringify(math.nan), JSON.stringify(-0.0), JSON.stringify("\ud83d\ude00")]
    return cases


@unittest.skipUnless(shutil.which("node"), "Node.js is required for differential conformance")
class ConformanceTests(unittest.TestCase):
    def test_native_javascript_observations(self):
        fixture = Path(__file__).parent / "fixtures" / "conformance.mjs"
        result = subprocess.run(["node", str(fixture)], capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
        expected = dict(json.loads(result.stdout)["entries"])
        actual = observations()
        self.assertEqual(set(actual), set(expected))
        for name, value in actual.items():
            with self.subTest(case=name):
                self.assertEqual(encode(value), expected[name])
