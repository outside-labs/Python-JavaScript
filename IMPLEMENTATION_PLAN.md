# Python-JavaScript implementation plan

Date: 2026-10-16

## First milestone delivered: 2026-10-16

[Python-JavaScript 0.1.0](https://pypi.org/project/Python-JavaScript/0.1.0/)
is published. At release the repository and organization Project were private. The repository
became public on 2026-10-20; the organization Project remains private. Final main
and tag `v0.1.0` point to `c0389e4645c39f3db23ad2e911475fdd3188dad5`.

| Task | Completed PR |
| --- | --- |
| FET-01 | [Fetch #2](https://github.com/outside-labs/JavaScript-Fetch-API/pull/2), published as 0.2.0 |
| JS-01 | [#16](https://github.com/outside-labs/Python-JavaScript/pull/16) |
| JS-02 | [#17](https://github.com/outside-labs/Python-JavaScript/pull/17) |
| JS-03 | [#18](https://github.com/outside-labs/Python-JavaScript/pull/18) |
| QA-01 | [#19](https://github.com/outside-labs/Python-JavaScript/pull/19) |
| CORE-01 | [#21](https://github.com/outside-labs/Python-JavaScript/pull/21), review-discovered edge-case fix |

Verification: 46 tests, including independent native Node observations;
Linux/macOS/Windows Python 3.14 final-main CI; installed wheel and source tests;
strict metadata checks; reviewed distribution contents; README examples; fresh
PyPI-only installation; and SHA256 agreement for both published artifacts with
[the Release build](https://github.com/outside-labs/Python-JavaScript/actions/runs/38959744536).
[Final-main CI](https://github.com/outside-labs/Python-JavaScript/actions/runs/38959517890)
passes. The installed dependencies are JavaScript-Fetch-API 0.2.0 and
JavaScript-JSON 0.1.0. The locked local development environment is ready.

Published SHA256:

- `python_javascript-0.1.0-py3-none-any.whl`: `3909129535faa257b58a99b39e40e86c0e88c547c32cb8c111ff9e1b8ebeb564`
- `python_javascript-0.1.0.tar.gz`: `1d3e72381e8dde4b010430acb8d8a19b16caa01f223686c80bd95725fd70b8bb`

The [compatibility matrix](https://github.com/outside-labs/Python-JavaScript/blob/v0.1.0/docs/compatibility.md)
records the supported subset and deviations; it is also included in the source
distribution. The translator remains a later milestone. Future tasks remain in
Triage until their precise contracts are adopted.

## Purpose

Implement useful JavaScript objects, methods, and functions in Python, preserving
JavaScript names, call shapes, and observable behavior wherever Python permits.
Python programs should remain pleasant to inspect and should eventually form a
well-defined source language that can be translated into JavaScript.

The first release is an explicitly bounded standard-library compatibility layer,
not a JavaScript interpreter. A future translator must reject unsupported Python
constructs rather than silently emit JavaScript with different behavior.

## Names and package ownership

| Repository / PyPI distribution | Python import | Responsibility |
| --- | --- | --- |
| `outside-labs/Python-JavaScript` / `Python-JavaScript` | `JavaScript` | Core values, objects, arrays, primitive helpers, compatibility adapters, future translation tools |
| `outside-labs/JavaScript-Fetch-API` / `JavaScript-Fetch-API` | `fetch_api` | Standalone HTTP Fetch API, headers, request/response, promises |
| `outside-labs/JavaScript-JSON` / `JavaScript-JSON` | `JSON` | Standalone JSON parser, serializer, Python-friendly dot traversal |

The main import is case-sensitive `JavaScript`. Do not provide a lowercase
`javascript` alias: it would conflict with an existing distribution. Fetch moves
from `from javascript import fetch` to `from fetch_api import fetch` in its next
minor release, `0.2.0`; the already-published `0.1.0` cannot be replaced.
`JavaScript` may re-export Fetch's public objects without copying their code.

`Python-JavaScript` declares both companion distributions as ordinary PyPI
dependencies with bounded compatible versions. Wheels must install without local
paths, Git checkouts, private repository access, or an editable source tree.
Local sibling checkouts are development inputs only.

Keep the independently useful Fetch and JSON repositories. Extract additional
packages only when their standalone contract is stable and demonstrated by a
second consumer. In particular, do not split every primitive into its own package.
Promise can later move out of Fetch once an independent async consumer warrants it.
Dependency direction remains acyclic: main -> companions, never companions -> main.

## Starting evidence

- Main is a new local scaffold with no implementation or remote history.
- Both companions are private repositories on `master`, with successful CI and
  published PyPI/GitHub `v0.1.0` releases.
- Fetch uses standard-library HTTP transport and background promises; its JSON
  objects differ from the standalone JSON package's key-shadowing policy.
- Standalone JSON deliberately preserves Python integers, lists, errors, and
  serializer conventions. Those are useful standalone choices, but cannot be
  described as full ECMAScript semantics.
- The JSON checkout contains an unrelated staged/deleted empty file. Preserve it.

GitHub Issues and the new private organization Project are the canonical queue:
[Project #11](https://github.com/orgs/outside-labs/projects/11) and the
[roadmap issue](https://github.com/outside-labs/Python-JavaScript/issues/1).
This document records architecture and acceptance criteria; completed PRs record
implementation choices, verification, and deviations.

## Compatibility principles

1. Preserve ECMAScript spelling and camelCase: `Object.keys`, `Array.isArray`,
   `array.map`, `string.includes`, `Number.isNaN`, and `Math.round`.
2. Explicit constructors establish runtime semantics: `Array.of(1, 2)` and
   `Object({"name": "Ada"})`. Python list/dict literals retain Python behavior.
   Do not monkey-patch builtins or claim that Python operators automatically gain
   JavaScript coercion, equality, overflow, or short-circuit semantics.
3. Represent `undefined` with one falsey singleton, distinct from `None` (`null`).
   Support missing properties, empty array results, JavaScript truthiness,
   number/string conversions, strict equality, SameValue and SameValueZero.
4. Implement JavaScript property-key conversion and numeric-key enumeration order.
   Preserve object identity. Object/array equality must not become structural
   equality merely because Python containers compare structurally.
5. Model sparse arrays explicitly: a hole is absent, while an explicit
   `undefined` element exists. Methods must distinguish them when the standard
   does. Do not use Python negative indexing for JavaScript bracket indexing;
   use `at()` for relative indexing.
6. JavaScript strings index UTF-16 code units. Test astral characters, lone
   surrogates, empty strings, and slicing boundaries.
7. JavaScript numbers use IEEE-754 binary64. Document the boundary between Python
   integer arithmetic and explicit `Number` conversion. Test NaN, infinities,
   signed zero, safe-integer boundaries, and coercion.
8. Python keywords require documented spellings such as `Array.from_` and
   `Promise.finally_`. Future translation maps these by binding identity.
9. Python callbacks can declare fewer positional arguments than JavaScript sends.
   Adapt signatures before invocation; never retry a callback after catching a
   TypeError from its body, which could duplicate side effects.
10. Do not imply support for prototypes, descriptors, getters/setters, Symbol,
    Proxy, browser globals, or arbitrary JavaScript execution before implemented.

## v0.1.0 scope and release contract

The first release delivers a small, coherent collection with executable examples
and a precise supported-method matrix. It must include:

- The `JavaScript` namespace and the two installable companion dependencies.
- `undefined`, JavaScript truthiness/conversion/equality helpers and `typeof`.
- Data-property `Object` construction, dot/bracket access, missing values,
  assignment/deletion, key ordering, and selected static enumeration/copy methods.
- `Array` length, indexed access, holes, iteration, mutation, slicing/search,
  callback operations, reductions, and construction helpers.
- A focused `String` API with UTF-16 indexing; `Number` predicates/conversion;
  Boolean conversion; selected `Math` functions with JavaScript edge cases.
- A JSON facade adapting the standalone JSON model to runtime Object/Array values and
  implementing the documented serialization subset, including undefined handling.
- Re-exported Fetch and Promise identities; standalone `fetch_api` stays usable.
- Typed package marker, meaningful unit tests, selected Node.js differential
  fixtures, CI on Python 3.14 for Linux/macOS/Windows, and clean artifact tests.
- A release workflow that verifies version/tag agreement, builds an sdist then a
  wheel from it, checks metadata, tests the installed wheel, and publishes using
  GitHub OIDC to the `pypi` environment.

Not in v0.1.0: a parser/transpiler, complete ECMAScript compatibility, arbitrary
prototype manipulation, descriptors, RegExp, Date, Map/Set, typed arrays, BigInt,
Symbol, WeakRef, Intl, DOM, streaming Fetch, or browser security policies.
Unsupported Python objects and unimplemented overloads raise clear errors.
The method matrix must state narrower domains and remaining deviations.

## Internal layout

```text
src/JavaScript/
    __init__.py      # intentional, documented public exports
    _values.py      # undefined, coercion, equality, callback conventions
    _object.py      # own data properties and enumeration
    _array.py       # sparse indexed collection and algorithms
    _string.py      # UTF-16-aware string methods
    _number.py      # number conversion and predicates
    _math.py        # selected mathematical functions
    _json.py        # JSON model/escaping adapter with binary64 decoder hooks
    py.typed
tests/
    test_values.py
    test_object.py
    test_array.py
    test_primitives.py
    test_json.py
    test_integration.py
    test_conformance.py
    fixtures/       # explicit Python/JavaScript behavioral pairs
docs/
    compatibility.md
```

Use the standard library for the core. Build tools and the Node.js conformance
runner are development tools, not runtime dependencies. Keep imports lightweight;
do not create event loops or make network requests during import.

## First rolling batch: five focused PRs

| Task | Repository | Depends on | Deliverable and acceptance criteria |
| --- | --- | --- | --- |
| FET-01 | JavaScript-Fetch-API | None | Rename the import package to `fetch_api`; remove the placeholder entry point; update all examples/tests/build metadata; bump to `0.2.0`; prove the wheel has `fetch_api` and no `javascript`; run existing loopback/Promise tests and release the passing change. |
| JS-01 | Python-JavaScript | FET-01 for distribution install | Establish `JavaScript` packaging, shared values/coercion helpers, CI, declared dependencies, import and value tests. Publish no placeholder command. |
| JS-02 | Python-JavaScript | JS-01 | Implement data-property Object and sparse Array together with identity, ordering, hole, callback, mutation, search, and reduction tests. |
| JS-03 | Python-JavaScript | JS-02 | Implement focused String/Number/Boolean/Math and JSON adapters; select standard-library binary64 decoder hooks to preserve negative zero without changing standalone JSON's Python integer contract; preserve companion class identity for Fetch/Promise; test boundaries and JSON failures. |
| QA-01 | Python-JavaScript | JS-03 | Add Node differential cases, an accurate compatibility matrix, installable examples, source/wheel verification and trusted release workflow; prepare and publish main `v0.1.0`, then verify installation from PyPI. |

Create each issue before implementation and add it to the organization Project.
Use Task, Order, Dependencies, Target, Readiness, and Status fields. Begin with a
minimal default-branch bootstrap, then use `type/TASK-ID-short-name` branches.
Each implementation includes tests. Push ready work and open its PR immediately,
then continue the next task while CI runs. Dependent main tasks use stacked PRs.
Fix failing checks, squash-merge in dependency order, retarget descendants, and
verify the final default branch. Do not rewrite shared history.

Release review added [CORE-01](https://github.com/outside-labs/Python-JavaScript/issues/20)
as a separate focused fix after the first five PRs. It corrects the non-callable
Math namespace, UTF-16-equivalent property keys, code-point iteration for explicit
surrogate pairs, string length ownership, and ASCII-only radix digit parsing.
These are regressions within the adopted API; no additional methods or dependencies
were added. Unit and native Node fixtures cover each correction.

## Earlier subsequent-roadmap proposals

The forward program below prioritizes compilation. Unselected standard-library
expansion remains Triage and is not automatically widened.

| Task | Target | Scope and completion evidence |
| --- | --- | --- |
| STD-01 | 0.2 | Broaden Object/Array/String coverage and property semantics; define descriptors/prototypes before adding them; port selected upstream conformance tests. |
| COL-01 | 0.2 | Map/Set with insertion order, identity and SameValueZero; iteration protocol and constructors; standalone extraction only with demonstrated consumers. |
| STD-02 | Later | Date with explicit timezone/clock rules, RegExp with an approved engine strategy, Error classes, Reflect, Symbol and BigInt. Avoid pretending Python regex/date semantics are equivalent. |
| BIN-01 | Later | ArrayBuffer/DataView/typed arrays with defined endianness, numeric conversion and shared-buffer ownership. |
| ASYNC-01 | Later | Promise compatibility gaps, scheduling contract, async iterables, abort and Fetch streaming; evaluate standalone Promise ownership without dependency cycles. |
| PARSE-01 | 0.2 | Specify the supported Python source subset, semantic restrictions and diagnostics before writing an emitter. |
| PARSE-02 | Later | Python AST parsing, lexical scopes, import/binding resolution, a typed intermediate representation and source spans. Reject unsupported AST nodes. |
| EMIT-01 | Later | JavaScript emission for the approved subset with source maps, deterministic output and execution parity tests. |
| QA-02 | Ongoing | Expand differential fixtures and selected Test262 coverage with provenance/license tracking, pinned engine versions and explicit expected divergences. |
| REL-02 | Later | Widen supported Python versions only after CI demonstrates compatibility; improve typing/docs and evaluate independent packages. |

## Translator architecture

Use Python's `ast` parser, not regex replacement. Resolve imported bindings,
including aliases: `from JavaScript import Array as A` and `import JavaScript as
JS` must map according to the binding, not textual spelling. Shadowed names must
remain local variables. Maintain a versioned symbol registry mapping runtime
exports and keyword-safe method names to JavaScript forms.

The initial candidate subset consists of literal values, explicit Object/Array/
String constructors, simple bindings, attribute/subscript access, calls, named
functions, supported lambdas, return, conditionals, loops over approved iterables,
and a later explicit async/await contract. Each construct needs an execution
parity fixture before adoption.

Semantic hazards need a design decision, not a syntactic rewrite: Python `and`/
`or`, chained comparisons, equality, negative indices, slicing, division/modulo,
arbitrary precision integers, default arguments, closures, exceptions, mutation,
keyword arguments, Python-only imports, and comprehensions. Provide source-located
diagnostics for unsupported cases. Never call eval/exec on source to translate it.

Separate parse -> bind -> validate -> lower -> emit. A structured intermediate
representation and source spans make emitter tests, source maps, alternate
targets, and useful error messages possible. Runtime dependencies that have native
JavaScript equivalents lower to standard objects or platform Fetch; Python-only
extensions must reject or require explicit helpers. Node is the initial execution
target; browser-specific assumptions require a separately defined target.

## Verification strategy

- Run focused standard-library unit tests during each task, then the relevant suite.
- Compare supported algorithms with executable Node fixtures: numeric key order,
  sparse map/filter/find/reduce, mutation during callbacks, NaN and signed zero,
  truthiness, UTF-16 indices, slicing and JSON omission/null behavior.
- Encode undefined, holes, NaN, infinity and signed zero explicitly in oracle
  output; plain JSON cannot distinguish them.
- Test callback arities, exceptions and single invocation; avoid flaky scheduling
  assertions and external network tests.
- Retain Fetch's loopback HTTP tests and Promise cancellation coverage.
- Test package imports outside the repository after installing the built wheel;
  inspect wheel paths and distribution metadata for namespace collisions.
- Main CI installs dependencies from PyPI. No unpublished dependency shortcuts.
- Build the sdist and build its wheel in isolation; validate with twine; test both
  distribution forms. Confirm installed metadata and versions after publication.

## Release sequence and external configuration

1. Publish Fetch `0.2.0` after namespace CI and squash merge. JSON `0.1.0` is
   already published and can remain unchanged.
2. Add a PyPI pending Trusted Publisher for project `Python-JavaScript`, GitHub
   owner `outside-labs`, repository `Python-JavaScript`, workflow `release.yaml`,
   environment `pypi`. This account-side setup is performed by the account owner.
3. Configure the repository `pypi` environment, merge the passing batch, verify
   final main CI and clean distribution installs, and create release `v0.1.0`.
4. Monitor build/publish jobs, compare artifact hashes, and verify a fresh public
   PyPI install of `Python-JavaScript==0.1.0` plus both dependency versions.

The repository is public as of 2026-10-20. PyPI distributions expose their source;
only reviewed source, tests and intended documentation belong in artifacts.
Exclude local notes, archives, credentials, references and unrelated working files.
Do not invent an open-source license: release metadata must reflect an actual
license decision. v0.1.0 is alpha and the compatibility matrix is part of its API.

## Completion criteria

The first milestone is complete when five focused PRs are merged, their issues
are Done, final default-branch CI passes, the main namespace is `JavaScript`,
standalone Fetch imports from `fetch_api`, and a clean PyPI installation runs the
documented examples with published companion dependencies. If external account
configuration blocks upload, report the exact remaining setup and preserve the
verified candidate without claiming publication.

## Coordinated program adopted 2026-10-20

Three parts have separate implementation and compatibility contracts. Open
issues and plans do not mean those features have shipped.

1. **Smaller source artifacts:** Shimify owns module reachability, bounded
   cross-module symbol extraction, resources, provenance and measurements.
2. **Our compiler and browser applications:** Python-JavaScript owns validated
   Python-to-JavaScript compilation and browser adapters. Pocket-python owns
   verified profiles, application assembly and offline delivery. Approved shared
   logic runs under CPython on the server and compiled code on the client;
   entrypoints and platform adapters remain explicit.
3. **Our independent interpreter:** pocket-python initially owns the plan and
   queue for a new engine that executes newly entered Python source locally.
   The separate interpreter plan defines language stages, architecture decisions,
   native/browser delivery, conformance and resource limits.

The compiler and independent interpreter must work without MicroPython or
Pyodide. An optional upstream CPython WebAssembly build is an existing-engine
distribution, not the independent interpreter. MicroPython, Pyodide and PyScript
remain separate optional compatibility routes. No silent fallback or arbitrary
package compatibility is implied.

Related plans:

- [Source reduction](https://github.com/outside-labs/shimify/blob/main/IMPLEMENTATION_PLAN03.md)
- [Compiler/browser target](https://github.com/outside-labs/Python-JavaScript/blob/main/IMPLEMENTATION_PLAN.md)
- [Application assembly](https://github.com/outside-labs/pocket-python/blob/main/IMPLEMENTATION_PLAN.md)
- [Independent interpreter](https://github.com/outside-labs/pocket-python/blob/main/IMPLEMENTATION_PLAN_INTERPRETER.md)

The compiler repository became public on 2026-10-20. Project visibility remains
separate; application artifacts still include only explicitly selected files.

## Common acceptance application

Use a small text_metrics application: shared Python computation counts
characters, words and lines; a local pure-Python helper and immutable constants
establish module boundaries, with an unused utility for reduction. Start the
compiler with a single-module equivalent, then add local imports. Adopt results
for empty strings, Unicode/astral characters, whitespace, invalid arguments and
numeric boundaries through the source-language contract.

Run shared logic through a CPython 3.14 CLI and local standard-library HTTP test
endpoint. The browser has a text area, a button and visible results; computation
runs offline. The interpreter later accepts this source as new input after
deployment. Keep server-only adapters/data outside client allowlists. No new
framework or external service is needed for this acceptance application.

Retain packaging==25.0 as Shimify's independent real-package module regression.
For resource work, extend the local fixture with one named UTF-8 stop-word file.
The new compiler/interpreter need not support the whole packaging library to
meet their first milestones.

## Forward compiler queue

| Task | Scope | Depends on | Readiness |
| --- | --- | --- | --- |
| [js/PARSE-01](https://github.com/outside-labs/Python-JavaScript/issues/11) | Specify the bounded translatable Python source language | Released foundation | Ready |
| [js/PARSE-02](https://github.com/outside-labs/Python-JavaScript/issues/12) | Build AST binding, validation and lowering passes | [js/PARSE-01](https://github.com/outside-labs/Python-JavaScript/issues/11) | Blocked |
| [js/EMIT-01](https://github.com/outside-labs/Python-JavaScript/issues/13) | Emit deterministic JavaScript for the approved subset | [js/PARSE-02](https://github.com/outside-labs/Python-JavaScript/issues/12) | Blocked |
| [js/MOD-01](https://github.com/outside-labs/Python-JavaScript/issues/23) | Compile bounded local Python module imports | [js/EMIT-01](https://github.com/outside-labs/Python-JavaScript/issues/13) | Blocked |
| [js/ASYNC-01](https://github.com/outside-labs/Python-JavaScript/issues/10) | Define Promise scheduling and browser async semantics | [js/PARSE-01](https://github.com/outside-labs/Python-JavaScript/issues/11) | Blocked |
| [js/BROWSER-01](https://github.com/outside-labs/Python-JavaScript/issues/24) | Implement browser DOM, events and Fetch adapters | [js/MOD-01](https://github.com/outside-labs/Python-JavaScript/issues/23), [js/ASYNC-01](https://github.com/outside-labs/Python-JavaScript/issues/10), [pocket/HOST-01](https://github.com/outside-labs/pocket-python/issues/17) | Blocked |
| [js/QA-03](https://github.com/outside-labs/Python-JavaScript/issues/25) | Verify CPython, Node and browser execution parity | [js/BROWSER-01](https://github.com/outside-labs/Python-JavaScript/issues/24) | Blocked |
| [js/PERF-01](https://github.com/outside-labs/Python-JavaScript/issues/26) | Measure compiled application and helper footprints | [js/QA-03](https://github.com/outside-labs/Python-JavaScript/issues/25) | Blocked |

PARSE-01 is the first Ready compiler task. PARSE-02/EMIT-01 follow in order;
MOD-01 adds local modules, ASYNC-01 defines the required async subset, and
BROWSER-01 uses the pocket-python host contract. QA-03 proves CPython/Node/browser
parity; PERF-01 measures output/helpers. This sequence does not require completing
Date, RegExp, Map/Set or prototype/descriptor expansion first.

[The adopted compiler language contract](docs/compiler-language.md) specifies the
first syntax/semantic decisions and reference corpus. It does not claim that
translation is implemented yet.

[The compiler front-end API](docs/compiler-front-end.md) implements parsing,
lexical binding, validation and immutable typed IR in the development checkout;
JavaScript emission remains a separate milestone.

## Compiler contracts and artifacts

Preserve ordinary supported Python truthiness, integers, Unicode, evaluation
order, exceptions and mutation through lowering/helpers, or reject unsupported
forms. Explicit JavaScript Object/Array/String/Number values retain their own
API behavior. The current Python-side compatibility library is not already a
browser execution engine.

Version language/target profiles, IR and compiled-artifact manifest. Emit
deterministic ES modules, source maps, compiler/profile versions, input/output
hashes, explicit static imports, required helpers and notices. Compile verified
bytes without running target code. Reject unknown native extensions, unsupported
Python-only imports and dynamic behavior outside the contract.

Use CPython as the Python behavior oracle and Node/browser observations for
explicit ECMAScript APIs. Prove emitted-code behavior under Node then real
browser DOM/events/Fetch, callback ownership, async/cancellation and worker/main
transport. Source maps identify original Python locations. Browser origin/CORS
constraints remain explicit; the Python Fetch companion is not automatically a
browser transport and needs deliberate lowering.

Build-time compilation produces deployable applications. Newly entered source
execution is the independent interpreter milestone. Share fixtures and host
protocols without silently coupling language/value models, IR or bytecode.

## Delivery, readiness and measurement

Issues and Projects hold current state; plans describe architecture/acceptance.
Ready means adopted scope and finished dependencies; Blocked means unfinished
dependencies; Triage means an optional or unselected extension. A contract or
architecture task may be Ready while later implementation awaits its decisions.
Do not mark a feature Done for documenting it. Update dependent readiness after
merges; Task, Order, Dependencies, Target and Readiness make the queue explicit.

Use rolling batches of 3-5 focused PRs. Start CI, continue independent work or
stack dependent changes, squash passing changes in dependency order and verify
final main. Preserve parent branches while open dependents target them;
reconcile, retarget and recheck descendants before deleting dependency bases.

Compare supported behavior before footprints. Separate source bytes, generated
code/helpers, interpreter assets, data/notices, source maps, complete uncompressed
bytes and compressed transfer. Record tool/engine/host versions, cold/warm
startup and memory method. No fixed size/performance/compatibility claim follows
from this roadmap. Incomplete import reports and unobserved dependencies never
authorize removal.

Keep releases/tags immutable. New runtime dependencies, services, engine
repository/package identity, release uploads and deployment retain their explicit
scope/decision requirements. This planning update changes no runtime dependencies
and publishes no package.

## Primary references

- [ECMAScript language specification](https://tc39.es/ecma262/)
- [Object algorithms](https://tc39.es/ecma262/multipage/fundamental-objects.html#sec-object-objects)
- [Array algorithms](https://tc39.es/ecma262/multipage/indexed-collections.html#sec-array-objects)
- [String algorithms](https://tc39.es/ecma262/multipage/text-processing.html#sec-string-objects)
- [Fetch standard](https://fetch.spec.whatwg.org/)
- [Python AST](https://docs.python.org/3/library/ast.html)
- [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/)
