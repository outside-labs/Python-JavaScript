// Native ECMAScript oracle for the explicitly supported runtime subset.
function encode(value) {
  if (value === undefined) return {type: "undefined"};
  if (value === null) return {type: "null"};
  if (typeof value === "number") {
    return {type: "number", value: Number.isNaN(value) ? "NaN" :
      value === Infinity ? "Infinity" : value === -Infinity ? "-Infinity" :
      Object.is(value, -0) ? "-0" : value};
  }
  if (typeof value === "string" || typeof value === "boolean") {
    return {type: typeof value, value};
  }
  if (Array.isArray(value)) {
    return {type: "array", length: value.length,
      items: Object.keys(value).map(key => [key, encode(value[key])])};
  }
  return {type: "object", entries: Object.entries(value).map(([key, child]) => [key, encode(child)])};
}

const cases = {};
const values = [undefined, null, false, true, 0, -0, NaN, Infinity, -Infinity,
  "", "0", "false", "  \ufeff42\n", "0xff", "-0x1", "0b11", "0o10", ".5e2", "1_000",
  "inf", "\x851", "１２", [], [1], [1, 2], {}];
cases.conversion = values.map(value => [Boolean(value), Number(value), String(value), typeof value]);
cases.equality = [1 === true, NaN === NaN, 0 === -0, Object.is(0, -0),
  Object.is(NaN, NaN), {} === {}, "😀" === "\ud83d\ude00"];
const obj = {b: 1, 10: 2, 2: 3, "01": 4, 0: 5, "4294967295": 6};
cases.objectOrder = Object.entries(obj);
delete obj.b; obj.b = 7;
cases.objectReinsert = Object.keys(obj);
cases.objectCopy = Object.assign({}, {a: 1}, null, undefined, {a: 2, b: 3});
cases.fromEntries = Object.fromEntries([["a", 1], ["a", 2], ["b"]]);

const sparse = Array(4); sparse[1] = undefined; sparse[3] = 4;
cases.sparse = sparse;
cases.sparseMap = sparse.map((value, index) => [value, index]);
cases.sparseFilter = sparse.filter(() => true);
cases.sparseFind = [sparse.findIndex(value => value === undefined),
  sparse.findLastIndex(value => value === undefined)];
cases.sparseSearch = [sparse.includes(undefined), sparse.indexOf(undefined),
  sparse.lastIndexOf(undefined), sparse.lastIndexOf(undefined, undefined)];
cases.sparseSlice = sparse.slice(0, -1);
const spliced = sparse.slice();
cases.sparseSpliceRemoved = spliced.splice(1, 2, "x", "y", "z");
cases.sparseSpliceResult = spliced;
cases.sparseReverse = sparse.slice().reverse();
cases.sparseSort = Array(1).concat([10, 2, undefined, 1]).sort();
cases.numericSort = [10, 2, 1].sort((a, b) => a - b);
cases.arraySearch = [NaN, true, 1, -0, undefined].map(value =>
  [1, true, NaN, 0, undefined].indexOf(value));
cases.arrayIncludes = [NaN, true, 1, -0, undefined].map(value =>
  [1, true, NaN, 0].includes(value));
const mutated = [1, 2, 3], seen = [];
cases.callbackMutation = mutated.map((value, index, array) => {
  seen.push(value);
  if (index === 0) { array[1] = 9; delete array[2]; array.push(4); }
  return value;
});
cases.callbackSeen = seen;
cases.reduce = [sparse.reduce((total, value) => total + (value || 0), 0),
  [2, 3].reduceRight((a, b) => a - b)];
cases.fromSparse = Array.from(Array(2));
cases.join = [1, null, undefined, [2, 3]].join("|");
cases.arrayPredicates = [[].every(() => false), [].some(() => true),
  [1].some(() => []), Array.isArray([]), Array.isArray({})];

const text = "a😀b😀";
cases.stringIndex = [text.length, text[1], text[-1], text.at(-1),
  text.charAt(20), text.charCodeAt(20), text.charCodeAt(1), text.codePointAt(1), text.codePointAt(2)];
cases.stringSearch = [text.indexOf("😀"), text.lastIndexOf("😀"), text.lastIndexOf("😀", 3),
  text.indexOf("", Infinity), text.startsWith("😀", 1), text.endsWith("b", 4), text.includes("\ude00")];
cases.stringSlice = [text.slice(1, 3), text.slice(-2), text.substring(3, 1), text.substring(-5, 1)];
cases.stringSplit = ["😀".split(""), "a,b,c".split(",", 2), "a,".split(","), "".split(""), "ab".split(), "ab".split("", 2**32)];
cases.stringConstructors = [String.fromCharCode(0xD83D, 0xDE00), String.fromCharCode(65537), String.fromCodePoint(0x1F600), Array.from(text)];
cases.stringOther = ["\ufeff  hi \n".trim(), "\x85hi\x85".trim(), "Straße".toUpperCase(), "AbC".toLowerCase(), "ab".repeat(2.8)];
cases.stringBoundary = ["abc".lastIndexOf("", 0), "abc".lastIndexOf("", -1), "abc".lastIndexOf("", NaN), "abc".substring(Infinity, -Infinity)];

const nums = [undefined, null, true, "1", NaN, Infinity, -0, 3.5, 3, 2**53 - 1, 2**53];
cases.numberPredicates = nums.map(value => [Number.isNaN(value), Number.isFinite(value), Number.isInteger(value), Number.isSafeInteger(value)]);
cases.parseInt = ["12px", "0xff", "010", "1e3", "-0", "bad", "0x"].map(value => parseInt(value));
cases.parseRadix = [["ffz", 16], ["11", 2], ["12", 1], ["z", 36], ["0b11", 0]].map(([text, radix]) => parseInt(text, radix));
cases.parseFloat = ["-1.2e2px", "1e+", "0xff", "Infinity!", "bad"].map(value => parseFloat(value));
const rounding = [-Infinity, -2.5, -1.5, -0.5, -0.2, -0, 0, 0.49999999999999994, 0.5, 1.5, Infinity, NaN];
cases.mathRounding = rounding.map(value => [Math.floor(value), Math.ceil(value), Math.trunc(value), Math.round(value), Math.sign(value)]);
cases.mathExtrema = [Math.min(), Math.max(), Math.min(0, -0), Math.max(-0, 0), Math.min(NaN, 1), Math.sqrt(-1), Math.sqrt(-0)];
const powers = [[NaN, 0], [1, NaN], [1, Infinity], [-1, Infinity], [-0, -3], [-2, 1025], [-1, .5], [-Infinity, 3], [-Infinity, -3], [0, -Infinity]];
cases.mathPow = powers.map(([base, exponent]) => Math.pow(base, exponent));
cases.numberString = [1e-7, 1e-6, 1e20, 1e21, 5e-324, -0, 9007199254740993].map(value => String(value));

cases.jsonParse = JSON.parse('{"items":[{"name":"Ada"}],"big":9007199254740993,"zero":-0}');
cases.jsonOmit = JSON.stringify({missing: undefined, fn: () => null, null: null,
  array: Array(1).concat([undefined, NaN, Infinity, -0])});
cases.jsonUnicode = JSON.stringify({b: "雪😀", 2: 1, 1: "\ud800", number: 1e-7});
cases.jsonSpace = JSON.stringify({x: [1, {y: true}]}, null, 2);
cases.jsonTop = [JSON.stringify(undefined), JSON.stringify(NaN), JSON.stringify(-0), JSON.stringify("\ud83d\ude00")];

process.stdout.write(JSON.stringify(encode(cases)));
