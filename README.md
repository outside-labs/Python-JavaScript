# Python-JavaScript

JavaScript-style objects, methods and functions for Python 3.14+, using the
case-sensitive `JavaScript` namespace. An alpha compatibility layer with a
documented subset of ECMAScript behavior.

```sh
python -m pip install Python-JavaScript==0.1.0
```

```python
from JavaScript import Array, JSON, Math, Object, String, undefined

people = JSON.parse('[{"name":"Ada","score":8},{"name":"Lin","score":6}]')
names = people.filter(lambda person: person.score >= 7).map(
    lambda person: person.name.toUpperCase()
)
assert names.join(", ") == "ADA"

profile = Object({"name": String("Ada"), "scores": Array.of(8, 6)})
assert profile.missing is undefined
assert profile.scores.reduce(lambda total, score: total + score, 0) == 14
assert Math.round(2.5) == 3
assert JSON.stringify(profile) == '{"name":"Ada","scores":[8,6]}'
```

Explicit `Object`, `Array`, `String` and `Number` values expose JavaScript names
and behavior. Ordinary Python literals and operators retain Python semantics.
Objects and arrays compare by identity and remain truthy when empty. Use
`Boolean(value)` or `truthy(value)` when testing JavaScript truthiness of values
that might include Python containers.

## Standalone packages

Installation includes two independently useful dependencies:

| Distribution | Import | Purpose |
| --- | --- | --- |
| `JavaScript-Fetch-API>=0.2.0,<0.3.0` | `fetch_api` | Standard-library HTTP Fetch and Promise APIs |
| `JavaScript-JSON>=0.1.0,<0.2.0` | `JSON` | Python-friendly JSON parsing, serialization and dot traversal |

```python
import asyncio
from fetch_api import fetch
from JavaScript import JSON

async def main():
    response = await fetch("https://example.com/api/people")
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status}")
    people = JSON.parse(await response.text())
    return people

# Run against your own JSON endpoint:
# people = asyncio.run(main())
```

`JavaScript.fetch`, `Promise`, `Headers`, `Request`, `Response` and `FetchError`
are the same objects exported by `fetch_api`. Fetch 0.2.0 changes the old
`from javascript import fetch` spelling to `from fetch_api import fetch`.

`response.json()` retains Fetch's standalone `JSONObject`/list result. Use
`JavaScript.JSON.parse(await response.text())` for runtime Object/Array/String
values. Standalone `import JSON` preserves Python integers and containers;
`from JavaScript import JSON` uses binary64 numbers and JavaScript serialization
rules for its supported subset.

## Supported surface

Core data objects and sparse arrays; UTF-16 String methods; Number predicates and
prefix parsers; Boolean conversion; selected Math functions; JSON; and the
standalone Fetch/Promise APIs. See the complete
[compatibility matrix](docs/compatibility.md) for method lists and limits.

Python keywords require `Array.from_`, `Object.is_`, and `Promise.finally_`.
`None` represents `null`; `undefined` is a separate singleton. Array bracket
indices follow JavaScript rules: `values[-1]` is a named property, and
`values.at(-1)` accesses the last element. `Array(3)` creates three holes;
`Array.of(3)` creates one element containing 3.

The next program adds our Python-to-JavaScript compiler, a browser target and
CPython/client parity, coordinated with Shimify source reduction and pocket-python
assembly. See [the implementation plan](IMPLEMENTATION_PLAN.md). A separately
staged independent interpreter is tracked by pocket-python. v0.1.0
provides the runtime foundation; it does not translate source or execute
JavaScript. Prototypes, descriptors, Date, RegExp, Map/Set, typed arrays, browser
globals and other unlisted APIs remain future work. Development is tracked in
the [issues](https://github.com/outside-labs/Python-JavaScript/issues) and
[Project](https://github.com/orgs/outside-labs/projects/11).

The development checkout now includes a [binding-aware compiler front end](docs/compiler-front-end.md)
that validates source and produces typed IR. JavaScript emission and browser
execution remain subsequent milestones.

## Development

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv build
```

Node.js 24 runs the native ECMAScript differential fixture. That test is skipped
when Node is absent locally; CI and release builds require it. Runtime code
needs only Python and the two declared companions. Tests make no external
network requests.
