# Compiled async profile

The 0.2.0 APIs `parse_source`, `compile_source` and `compile_modules`
accept `async_enabled=True`. Without it, async syntax remains rejected. Published
0.1.0 artifacts predate these compiler APIs. Single-module artifacts identify
`python-browser-async/1` and ABI `python-browser-async-esm/1`; local-module artifacts
identify `python-browser-modules-async/1` and ABI
`python-browser-modules-async-esm/1`. These are explicit extensions of the
[source language](compiler-language.md) and [module contract](compiler-modules.md).

```python
from JavaScript import Promise

async def main():
    value = await Promise.resolve(9007199254740993)
    print(value + 1)
    return value
```

Compile this source with the async flag, import its generated `createModule`,
then use `await createModule().main()` in JavaScript. An exported async function
returns a native Promise, including for invalid arguments and cancellation.
Python integers, strings and tuples keep their adopted runtime representation;
no implicit Number conversion is added. Synchronous exports returning an adopted
Promise also expose a native Promise. Other synchronous exports remain synchronous.

## Coroutine and Promise behavior

Top-level plain `async def` functions support the existing positional parameters,
immutable defaults, ordinary control flow and return values. Calling one inside
compiled Python creates a lazy, single-use coroutine. Its body begins when
awaited. Arguments/defaults are bound when called. Awaiting the same coroutine
twice raises RuntimeError; a Promise can be awaited repeatedly. Await in defaults,
module initialization or a synchronous function is rejected. Async generators,
async iteration/context managers, asyncio task APIs, gather and top-level await
are deferred. Unawaited coroutines have no execution side effect; no finalizer
warning is promised.

The approved async JavaScript registry adds `Promise.resolve(value)`,
`Promise.reject(TypeError(message))` and `promise.then(on_fulfilled, on_rejected)`.
Registry imports/aliases resolve by binding identity. A handler is a supported
plain synchronous Python function or None; omitted/None handlers forward outcomes.
Each handler receives one argument and is called once. A returned adopted Promise
is chained; a raised adopted exception rejects the chain without retrying the
handler. Async callbacks and arbitrary thenables are rejected. Promise constructors,
catch/finally, all/race and general native Promise inputs remain deferred.
Coroutines must be awaited before passing them as arguments; async functions
cannot return an unawaited coroutine or Promise as their final value.

Source locations survive async rejection, imported calls and callbacks. Explicit
builtin TypeError and existing runtime errors retain their Python names and
messages. Unexpected host rejections become a bounded RuntimeError rather than
exposing host internals. Synchronous compiled calls retain depth 128; at most 128
async coroutine bodies may be active in one context. This bound also limits
concurrent active bodies and is not CPython's recursion limit.

## Scheduling and cancellation

An exported async invocation starts on a JavaScript microtask. Internal coroutine
creation remains lazy; native async lowering and Promise continuations preserve
source evaluation order, short circuiting, and callback single invocation.
Awaited boolean/chained-comparison expressions may add a continuation even on a
short-circuited path. Awaiting an already fulfilled Promise also crosses a
microtask checkpoint. CPython's companion Promise uses thread-backed callbacks
and its asyncio bridge may resume an already completed awaitable without the
same checkpoint. Timing relative to unrelated tasks or callbacks is therefore
not a cross-target guarantee. No implicit event loop or Python scheduler is
embedded in the generated artifact.

`createModule({write, signal})` accepts an optional AbortSignal for that context.
Generated statements, public calls, callbacks and await boundaries check it.
Cancellation rejects pending exported operations with name AbortError and code
CANCELLED at a recorded source location. Await listeners are removed on success,
failure and cancellation. Completed output/other side effects remain committed.
The signal applies to the whole application context; create a fresh context to
restart. Signal reasons are not copied into application errors.

AbortSignal delivery cannot interrupt busy synchronous execution on its own.
In a worker, the trusted main thread must retain worker termination as the stop
path. The [host protocol](https://github.com/outside-labs/pocket-python/blob/main/docs/browser-host-protocol.md)
uses session/request IDs, serialized tagged values, exactly one terminal result
and CANCELLED/TIMEOUT replies. The [browser profile](compiler-browser.md) wraps a pending
host result as an adopted Promise, forwards cancellation to its request, discards
stale replies and releases handles. Raw Promise/Event/DOM objects do not cross
that transport. HOST-01 defines the shared contract; the async-only profile does not itself provide that adapter.

## Fetch boundary

CPython code continues to use the published `fetch_api.fetch` implementation
re-exported by `JavaScript`, including its thread-backed Promise and HTTP types.
Those implementations are not copied into compiled artifacts. `fetch`, Request,
Response, streaming bodies and response JSON methods remain rejected by this
compiler profile. The [browser profile](compiler-browser.md) adds the separately granted `fetch/1` text operation,
lowering to browser-native Fetch through the trusted host with AbortSignal,
origin/CORS, URL, credential, redirect, size and deadline rules. Its first text
metrics UI requires no network access. Streaming, async iterables and standalone
Promise package extraction remain separate extensions.

Local fixtures compare awaited values, laziness, defaults, order and callback
errors with CPython and execute the generated modules in Node. Abort and listener
cleanup tests use a local AbortController; no external network is needed.
