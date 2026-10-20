# Compiled browser target

The development checkout provides `JavaScript.browser.compile_browser`. It
compiles verified [local source modules](compiler-modules.md), enables the
[async profile](compiler-async.md), and records the complete local worker/host
asset closure. It is not included in the published 0.1.0 distribution.

The target is `python-browser-modules-host-async/1`, compiler ABI
`python-browser-host-esm/1`, using host protocol `pocket-python-host` version 1.
Python computation executes as our emitted JavaScript and compatibility helpers
inside a module worker. No interpreter, server execution or alternate engine is
loaded. New-source parsing remains the independent interpreter's later milestone.

## Run the example

From this checkout:

```sh
uv sync --locked
uv run --no-sync python examples/browser_text_metrics.py --output build/browser-text-metrics
python -m http.server 8000 --bind 127.0.0.1 --directory build/browser-text-metrics
```

Open `http://127.0.0.1:8000/`. Run counts Unicode characters, ASCII-separated
words and LF-based lines. Stop terminates the worker; Restart creates a fresh
session. The example enables Run after its callback is registered. Computation
works offline after loading. Offline reload, service-worker caching and PWA
assembly are WEB-03, not part of this example builder.

The builder reads the approved text_metrics corpus, emits selected local modules,
source maps/notices, the host/worker/protocol modules, a manifest and a small HTML
entry. It requires a new output directory and preserves existing outputs.
The same computation can be imported under CPython in a separate server entry;
client entrypoints and host adapters are explicit. E2E-01 owns the complete
server/client packaging demonstration.

## Python namespace and entry

Only named imports from the compiler's `JavaScript.browser` namespace are
adopted. They belong in the client entry; they are not CPython DOM functions.

```python
from JavaScript.browser import on_click, read_text, write_text, fetch_text
from text_metrics import metrics

async def display(text):
    print(metrics(text))

async def main():
    await on_click("run", display)
```

| Function | Adopted behavior |
| --- | --- |
| `read_text(control)` | Await the current text/value of a named granted control; return Python str. |
| `write_text(control, text)` | Await replacement with plain text; return None. |
| `on_click(control, callback)` | Register a known compiled synchronous/async function taking one snapshot argument; return an opaque subscription handle. |
| `unsubscribe(subscription)` | Remove the listener and release its callback; return None. Reuse raises STALE_HANDLE. |
| `fetch_text(url)` | Await an allowed native GET and return `(status, final_url, text)` as a Python tuple. HTTP non-2xx statuses remain successful responses. |

Every call returns an adopted Promise that source code awaits. Aliases retain
binding identity. Str arguments stay explicit, and status integers remain BigInt.
There is no implicit JSON/dict/Number conversion. Imports must be unconditional;
module initialization contains imports, definitions, immutable constants, pass or
docstrings. Browser entry requires a directly defined async `main()` without
required arguments. This prevents host calls before the ready handshake.

The original JavaScript Array/Promise registry keeps its own contract.
`from JavaScript import fetch`, arbitrary globals/attributes, selectors, innerHTML,
DOM nodes, POST/options/headers, streaming and response JSON APIs remain outside
this language profile. CPython uses the published `fetch_api` companion through
its server adapter; that implementation is not embedded in browser output.

## Main-thread configuration

Import `mountCompiledApplication` from the generated `browser-host.mjs`. Supply
the verified application's manifest SHA-256, profile `compiled-javascript`/1,
entrypoint `app.mjs`, and engine null. Bind grant names to trusted DOM Elements,
provide a text output Element, and optionally map button names to input snapshot
controls (otherwise the callback receives an empty str). The example supplies a complete configuration. Each required capability
must be granted; source code cannot widen controls or URLs.

The adapter supports output/1, dom-text/1, dom-events/1, handles/1 and the adopted
GET text subset of fetch/1. Files/persistence and unlisted capabilities fail
initialization. No arbitrary host filesystem or native object is exposed.
Fetch grants use exact normalized HTTP(S) URLs without embedded credentials or
fragments. Native Fetch preserves origin/CORS checks, omits credentials, rejects
redirects and enforces a bounded strict-UTF-8 response and deadline. Relative
requests are normalized against the page URL before the exact grant check.

`ready` confirms protocol initialization, before asynchronous application setup
finishes. `main()` then registers handlers. `stop()` aborts pending host work,
removes listeners and terminates the worker. `restart()` stops the current
session and returns a fresh controller. `stats()` exposes lifecycle and resource
counts for integration tests. Optional `onError` receives bounded plain error
metadata; the default output uses a text node. Application code never supplies
HTML or arbitrary host properties to these operations.

## Ordering, lifetime and limits

The adapter implements the [HOST-01 envelope and lifecycle](https://github.com/outside-labs/pocket-python/blob/main/docs/browser-host-protocol.md)
for this adopted surface: fresh 128-bit sessions, independent monotonic sequence
counters, unique request IDs, bounded pending work and terminal replies. Stale
sessions do not advance counters. Malformed active messages/replays close the
session. Valid operation failures reject the source await with an original source
location; an unhandled main/callback exception closes the application.

Events are serialized in a bounded queue. Output is ordered and bounded. A
subscription owns its main-thread listener and worker callback until unsubscribe
or teardown; already queued events for released subscriptions are discarded.
Canceled/timed-out request slots remain bounded until terminal reply or teardown.
Cancellation cannot undo a committed DOM/output effect. Busy synchronous code
requires worker termination; the main thread remains responsive. Worker placement
provides responsiveness isolation, not a general hostile-code security sandbox.

Defaults match HOST-01: 1 MiB messages/responses, value depth 64, 32 pending
requests/subscriptions/events, 65,536 output code points and ten seconds per
operation. Trusted configuration may lower limits. Oversized results return
QUOTA. Stored Python surrogate points survive engine transport; projecting to
DOM UTF-16 and reading back may combine an explicit surrogate pair. Error
metadata retains its source span; full call-frame traceback construction is
separately staged.

The manifest records source/output hashes, maps, notices, required capabilities
and every static module/worker edge. Initialization echoes identity; it does not
independently authenticate files. Deployment/assembly must verify the recorded
assets against a trusted manifest before use. WEB-03 implements that application
profile and cache/publication boundary.

## Verification

```sh
uv sync --locked --group browser-tests
uv run --no-sync python -m playwright install chromium
uv run --no-sync python scripts/compiler_browser_smoke.py --report build/compiler-browser-report.json
```

Use `--channel chrome` for an installed Chrome. Playwright 1.64.0 is a declared
test-only group; existing runtime dependency versions are retained. CI tests
installed wheel/source compiler APIs on Linux/macOS/Windows and runs the local
browser fixture on Linux. The fixture covers CPython/client parity, loaded-worker
offline computation, Fetch status/CORS/credentials/grants/redirect/size/deadline,
source errors, forty callback allocation/release cycles, repeated restart,
pending Fetch cancellation and busy-worker stop. The user example is also run
under a URL subdirectory. Reports record the actual browser and target identity.
