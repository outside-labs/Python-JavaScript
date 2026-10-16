# v0.1.0 compatibility

This is a selected ECMAScript-compatible runtime API implemented in Python.
Method names and the tested behaviors below follow the
[ECMAScript specification](https://tc39.es/ecma262/). It is not a complete language
implementation. The native Node.js fixture checks the adopted subset, rather
than asserting general Test262 conformance.

## Supported API

| Surface | Implemented members |
| --- | --- |
| Values | `undefined`, `null`, `NaN`, `Infinity`, `typeof`, `truthy`, `strictEqual`, global `isNaN`, global `isFinite` |
| `Object` | Mapping/empty construction, dot/bracket data properties, deletion, missing `undefined`, `keys`, `values`, `entries`, `assign`, `fromEntries`, `hasOwn`, `is_`, `toString` |
| `Array` | Numeric-length/element construction, `of`, iterable `from_`, `isArray`, `length`, bracket access/deletion, `at`, `push`, `pop`, `shift`, `unshift`, `slice`, `splice`, `concat`, `join`, `toString`, `includes`, `indexOf`, `lastIndexOf` |
| Array callbacks | `map`, `filter`, `forEach`, `some`, `every`, `find`, `findIndex`, `findLast`, `findLastIndex`, `reduce`, `reduceRight` |
| Array mutation/iteration | `reverse`, `fill`, `sort`, `keys`, `values`, `entries`, Python iteration |
| `String` | Conversion, `length`, bracket code units, `at`, `charAt`, `charCodeAt`, `codePointAt`, `slice`, `substring`, `indexOf`, `lastIndexOf`, `includes`, `startsWith`, `endsWith`, `split`, `concat`, `repeat`, `trim`, `trimStart`, `trimEnd`, `toLowerCase`, `toUpperCase`, `toString`, `valueOf`, `fromCharCode`, `fromCodePoint` |
| `Number` | Conversion, `isNaN`, `isFinite`, `isInteger`, `isSafeInteger`, `parseInt`, `parseFloat`, decimal `toString`, `valueOf`, `EPSILON`, `MAX_SAFE_INTEGER`, `MIN_SAFE_INTEGER`, `MAX_VALUE`, `MIN_VALUE`, `NaN`, `POSITIVE_INFINITY`, `NEGATIVE_INFINITY` |
| `Boolean` | Primitive conversion returning a Python bool |
| `Math` | `abs`, `floor`, `ceil`, `trunc`, `round`, `sign`, `min`, `max`, `sqrt`, `pow`, `random`; `PI`, `E`, `LN2`, `LN10`, `LOG2E`, `LOG10E`, `SQRT1_2`, `SQRT2` |
| `JSON` | `parse(text)`, `stringify(value, replacer=undefined, space=undefined)`, `JSONDecodeError` |
| Global parsing | `parseInt`, `parseFloat` |
| Companions | `fetch`, `FetchError`, `Headers`, `Request`, `Response`, `Promise`, re-exported unchanged from `fetch_api` |

## Data model and Python boundaries

- `Object` stores own enumerable writable data properties. Keys convert to
  strings. Array-index keys enumerate numerically before other keys in insertion
  order. Deleting and re-adding a non-index key moves it to the end.
- `Object()`/`Object(None)` create empty objects; `Object(existing)` returns the
  existing Object. Other construction accepts a Python mapping. Primitive
  boxing and prototype/descriptor operations are unsupported.
- Object-to-primitive conversion uses the built-in data-object representation.
  Custom `valueOf`/`toString` conversion hooks and Symbol.toPrimitive are not
  implemented.
- Objects preserve supplied child values; passing a nested Python dict/list
  does not recursively convert it. JSON parsing creates runtime containers.
- Own Object keys shadow ordinary Python attributes. Use `Object.keys(obj)`
  for static methods and brackets for special names such as `__class__`.
  Missing ordinary attributes return `undefined`; Python `hasattr` therefore
  cannot test property presence. Use `Object.hasOwn` or `key in obj`.
- Arrays store holes separately from explicit undefined values. Length changes
  truncate or expand sparsely. Callback methods skip holes where ECMAScript does;
  find methods and includes observe holes as undefined. `Object.hasOwn(array, i)`
  distinguishes them. `length` is an own, non-enumerable property.
- Use bracket notation for named Array properties; arbitrary dot property
  assignment and overriding Array methods are outside this subset. Python `in`
  tests property presence, matching JavaScript `in`; use `includes` for values.
- `Array.from_` accepts Python iterables, including runtime arrays and strings.
  JavaScript array-like objects, custom iterators/Symbol protocols, `thisArg`,
  subclass species and `Symbol.isConcatSpreadable` are not implemented. `concat`
  spreads runtime Array values; ordinary Python lists remain single elements.
- Callbacks receive JavaScript's arguments, truncated to their inspectable Python
  positional arity. Zero-argument and variadic callbacks work. Uninspectable
  callables receive all arguments; wrap them in a lambda if needed. Keyword-only
  callback parameters and JavaScript `this` binding are unsupported. Exceptions
  propagate once without retrying the callback.
- `sort` is stable and uses UTF-16 lexicographic order by default. Undefined
  elements follow defined elements; holes follow undefined. Comparators may
  return a number; mutating the sorted array from its comparator is unsupported.
- String methods and brackets index UTF-16 code units. String iteration visits
  code points. Python `len(string)` and inherited str methods/operators retain
  Python semantics; use `.length` for JavaScript length. Case conversion uses
  Python's Unicode tables, which can differ from a JavaScript engine's version.
- `Number` is a float subclass with binary64 conversion. Plain Python integers,
  arithmetic, division, modulo, comparisons, `and`/`or`, `==`, container literals
  and inherited methods retain Python behavior. Use explicit helpers for
  JavaScript semantics. No operator rewriting or automatic primitive boxing is
  provided. `Boolean` does not create boxed Boolean objects.
- Methods can return native Python primitives, including Array `join` and Math
  results. Wrap such results with `String` or `Number` to call their JavaScript
  methods; Python does not automatically box primitive values.
- Decimal number strings use Python's shortest float representation adjusted to
  JavaScript exponent/fixed-format thresholds. Tested ordinary values agree;
  rare shortest-decimal tie choices may differ between Python and ECMAScript.
  Other number radices and `toFixed`/`toPrecision` are not implemented.
- Errors use Python `TypeError`, `ValueError` and `JSONDecodeError`; no full
  ECMAScript Error hierarchy or matching message text is promised. Invalid array
  lengths, repeat counts and code points raise ValueError. Invalid JSON numeric
  constants raise ValueError. Unsupported overloads raise TypeError or
  NotImplementedError.

## JSON boundaries

`JavaScript.JSON.parse` creates Object, Array and String values, and binary64
Python floats for numbers. Negative zero and integer rounding follow the number
model. It uses the standard-library decoder's numeric hooks because standalone
`JSON.parse` intentionally preserves Python integers. The companion's serializer
provides string escaping; its public decoder exception type is shared.

`stringify` emits compact JSON by default, orders object keys, writes non-finite
numbers as null, omits undefined/callable object properties, and writes them as
null in arrays. Top-level undefined/callables return undefined. Shared references
are allowed; cycles raise TypeError. A numeric/string `space` is capped at ten
characters. Lone surrogates are escaped. Plain Python mappings/lists/tuples are
accepted as a convenience.

Revivers, replacer functions/property lists, `toJSON` hooks, symbols and BigInt
are unsupported. A non-null replacer or callable own toJSON hook raises
NotImplementedError. Byte input is a standalone JSON extension and is rejected
by the runtime facade. The facade does not change standalone `import JSON` or
Fetch's `response.json()` result types.

## Fetch and Promise boundaries

The [standalone Fetch documentation](https://github.com/outside-labs/JavaScript-Fetch-API)
is the complete contract. Core HTTP(S) requests, buffered bodies, headers,
redirects, promises and await work. Browser policies, streaming, abort, cookies
and browser globals are not provided. Promise callbacks use a background Python
thread, not JavaScript microtask scheduling. Rejections use Python exceptions;
handlers return values or Promise objects, rather than raw Python coroutines.

## Future translation

The runtime deliberately keeps recognizable call shapes, but a Python program
using it is not automatically safe to translate. The future translator must
resolve bindings and validate an approved Python AST subset. It must diagnose
unsupported operators and Python-only constructs before emitting JavaScript.
