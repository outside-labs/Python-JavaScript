# Compiler compatibility matrix: compiler-parity/1

The development compiler runs the same approved source corpus under CPython
3.14.7 and as identical emitted ES modules in Node 24.19.0 and a Chromium module
worker. This is a bounded ahead-of-time Python profile. The independent source
interpreter is a separate pocket-python implementation. Published 0.1.0 predates
this compiler.

| Area | Adopted behavior and evidence | Boundary |
| --- | --- | --- |
| Values | Typed None, bool, arbitrary-size int, code-point str and immutable tuple returns | Mutable containers, floats and arbitrary host values are deferred |
| Evaluation | Output order, short-circuiting, default tuple identity, imported function aliases and source initialization order match CPython | Integer/string interning identity is not adopted; indirect local callable invocation is rejected |
| Unicode/numbers | Integers beyond 2^53, signed floor/modulo, combining marks, supplementary characters and explicit surrogate pairs | Native JS strings count UTF-16 units; Python strings count code points |
| Exceptions | Error class, adopted message, original filename/line/code-point column and output before failure match the reference | Argument-count wording and recursion resource limits are profile-specific |
| Source maps | Actual Node and browser error stacks map back to original explicit raise, division, indexing and module callback source lines | These are mapped JS frames, not complete Python traceback objects; source-map columns identify emitted statements |
| Async | Lazy/single-use coroutines, Promise callback side effects, rejected values and previously raised error origins | Microtask scheduling can differ from CPython; async generators/iteration and Promise.all are not adopted |
| Browser host | Real-worker shared computation, DOM callbacks/release, Fetch grants/limits, cancellation and stop/restart are checked separately by compiler_browser_smoke.py | Host errors carry original spans; workers provide responsiveness isolation, not a general security boundary |
| Imports | Explicit source allowlist and shared module/runtime identity; module callback origins preserved | Dynamic imports, undeclared sources and arbitrary installed-package execution are rejected |
| Diagnostics | Every rejected/deferred corpus entry must fail with its declared compiler diagnostic | A failed supported case fails the suite; no Python execution fallback in either target |

The schema-1 corpus consists of compiler_contract.json plus compiler_parity.json.
The initial matrix has 24 supported cases and 10 explicit boundary cases. Its
report also records three native observations in both JavaScript targets:
Array.of length, Promise callback ordering and UTF-16 string length. These are
native API observations, not CPython-language assertions. Compiler Promise cases
compare the adopted Python wrapper with emitted modules separately.

The reference runs only trusted test fixtures in fresh isolated Python processes.
The browser fixture server serves static assets; the browser worker performs the
computation. Both targets import the same artifact bytes. Tagged comparison
preserves integer precision, Unicode surrogate distinctions and tuple structure.
Output and original error spans are compared independently. Source-map checks
feed actual target stack frames to Node's SourceMap consumer. An unraised
exception rejected through a Promise reports its first source await; its native
JS stack can retain the construction site. Only explicitly raised errors in the
traceback subset require the first mapped frame to identify the error origin.

Run the complete suite from a development checkout with the declared browser
test group and its Chromium installation:

```sh
uv sync --locked --group browser-tests
uv run --no-sync python -m playwright install chromium
uv run --no-sync python scripts/compiler_conformance.py --browser --report build/compiler-parity-report.json
uv run --no-sync python scripts/compiler_browser_smoke.py --report build/compiler-browser-report.json
```

Omit --browser for the Node/reference gate; --channel chrome selects an installed
Chrome for local verification. CI pins the reference and Node versions, uses the
locked Playwright package and retains both reports with the actual browser
version. The ordinary installed-wheel/sdist suite runs the Node/reference gate
on Linux, macOS and Windows. Reports contain every compared result, original and
mapped error locations, profile classifications, corpus SHA-256 and artifact
manifest identities. A corpus change updates its digest; incompatible report
schema/comparison semantics require a new suite version. A report describes its
tested versions and selected cases, not universal CPython compatibility.

The shared reduced text-metrics computation originates in Shimify's fixture
package. The attribution entry in compiler_parity.json pins the source revision;
tests/fixtures/licenses/SHIMIFY-LICENSE.txt retains its exact MIT notice. Emitted
shared-computation artifacts, the host smoke fixture and the runnable browser
example include that notice in LICENSES/shimify.txt with manifest hashes. Other
cases are original regression examples; no upstream Python test suite is copied.
This attribution does not choose a license for the compiler itself.
