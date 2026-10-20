# Compiler source language contract

PARSE-01 adopts `python-browser/1` as the initial language profile, using Python
3.14 grammar and semantics for ordinary Python constructs. This contract is
future compiler work; the released package still provides Python-side
JavaScript compatibility objects. The reference corpus checks Python behavior,
not successful translation.

## First application and accepted source

Start with a single-module equivalent of Shimify's text_metrics application:
Unicode character count, explicitly selected ASCII word separators, LF-based
line count and a tuple of Python integer results. MOD-01 later adds its local
helper import and package re-export. The selected input domain is builtin str;
non-string input raises TypeError("text must be str"). String subclass overrides
and arbitrary user objects are outside the first profile.

| Syntax/API | First adopted contract |
| --- | --- |
| Scalars | None, bool, arbitrary-precision int and Unicode str literals; tuples of supported values. Floats/bytes/complex wait for separate numeric/binary contracts. |
| Bindings | Simple names, immutable module constants, ordinary local assignments and top-level plain functions. Preserve lexical binding identity and evaluation order. |
| Functions | Positional arguments and immutable literal defaults; return, direct calls and recursion. Keyword/variadic calls, nested closures, decorators, annotations and async functions are deferred. |
| Control flow | if/elif/else, for over approved strings/tuples, break/continue, ordinary return and expression statements. while/comprehensions/generators are deferred initially. |
| Operations | Supported scalar arithmetic/comparisons, Python and/or/not, identity on supported values, string membership and supported indexing. Mixed or unknown operand forms need helpers or a source-located rejection. |
| Builtins/errors | len on adopted strings/tuples, print of adopted values, approved isinstance checks and explicit builtin TypeError raising needed by the fixture. No eval/exec, reflection or undeclared I/O. |
| JavaScript API | Resolve explicit imports/aliases through a versioned symbol/method registry. Start with Array.of and length as a binding fixture; other exports/methods need adopted signatures and parity cases before lowering. |
| Imports | Only approved JavaScript registry imports in the single-module profile. Local modules follow MOD-01; Python stdlib/third-party/native imports require explicit future adapters. |

Every AST form and operation is supported, rejected or deferred explicitly. A
Python-side JavaScript API existing today does not automatically make it
translatable. No Date/RegExp/Map/Set expansion is a prerequisite for this compiler.

The first operators are integer +, -, *, // and %, unary +/-, boolean and/or/not,
adopted scalar comparisons and string membership. True division, exponentiation
and bitwise operations are deferred. Indexing supports builtin strings/tuples
with integer indices and Python negative-index/error behavior; slicing is
deferred. Identity tests initially cover None/bool singletons and retained
object aliases, not implementation-dependent integer/string interning.

## Python and JavaScript semantics

Preserve Python truthiness and short-circuit operand results, rather than native
JavaScript truthiness for containers. Strings count and iterate Unicode code
points, preserving astral characters and combining marks without normalization.
Python integers retain precision beyond 2**53; use deliberate representations
and conversions, not silent Number rounding. Floor division/modulo must match
negative operands and Python errors. Compare values and side effects in the
original order with each operand evaluated once.

Tuple results remain distinguishable from JavaScript arrays in internal and
transport contracts; implement required Python operations or reject them. Do not
claim general tuple hashing, mixed comparisons or arbitrary object equality.
Explicit JavaScript Array/String/Number/Object values retain their own approved
API semantics. Crossing the two models needs an explicit conversion/signature.

Defaults are definition-time values, with immutable literal restrictions in the
first profile. A direct call resolves to the actual lexical binding; aliases,
local shadowing and recursion must not be rewritten by spelling alone. Preserve
source-visible guards and errors even when static types guide lowering.

Runtime boundary values must satisfy the export/input contract. Incompatible
operations raise the adopted Python error or fail validation clearly; the
compiler must not emit superficially equivalent JavaScript. Unsupported async,
classes, reflection, mutable module initialization and dynamic execution remain
source-located diagnostics, not an interpreter/server fallback.

## Front end and diagnostics

Use ast -> bind -> validate -> typed IR -> lower -> emit. Never import or execute
application/dependency modules to compile them. Carry original file/line/column
spans and stable binding identities through every pass. Validate imports,
exports, operation signatures and unsupported forms before publishing output.

Diagnostic families: PJS100 unsupported syntax/feature, PJS110 unresolved or
unsupported binding/import, PJS120 incompatible operation/value contract.
Include code, phase, original path, one-based line and column, and a concrete
message. Reject an entire unsupported compilation without partially publishing
an executable artifact. Do not catch an application exception and retry a
callback or silently alter evaluation order.

## Output and conformance

EMIT-01 produces deterministic ES modules, source maps and an explicit helper
closure. Its manifest identifies compiler/language/target versions, source and
output hashes, entrypoint/exports, static module imports, required helpers and
notices. Application profile schema 2 is defined by pocket-python; it must not
be confused with its current MicroPython runtime asset lock.

Use CPython as the ordinary Python semantics oracle and native Node/browser
observations for explicit JavaScript APIs. tests/fixtures/compiler_contract.json
provides initial positive and rejected/deferred cases; parsing known sources
for the contract does not prove a compiler already exists. PARSE-02 implements
the front end and EMIT-01 must execute emitted output against that corpus.

MOD-01 adds explicit local-module identity and initialization; ASYNC-01 adds
supported await/Promise/cancellation behavior. BROWSER-01 integrates main-thread
DOM/events and native Fetch through the versioned host protocol; QA-03 verifies
CPython/Node/browser parity and source-map errors. Origin/CORS and worker message
constraints remain explicit.

This build-time application compiler does not execute newly entered source in
the browser. That is a separate independent-interpreter milestone. Shared
fixtures/host protocols do not make the two engines' IR, bytecode or value models
interchangeable.
