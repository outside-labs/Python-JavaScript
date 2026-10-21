# Reproducing compiler measurements

PERF-01 measures the existing helper selection in the 0.2.0 compiler. It
compares required helpers with every helper available to the same language
profile; it does not add an optimization or enable otherwise unsupported syntax.
The complete positive compiler corpus must match CPython in both variants, in
Node and in a real browser worker. Rejected/deferred features remain covered by
the separate compiler conformance gate. Published 0.1.0 predates these APIs.

```sh
uv sync --locked --group browser-tests
uv run --no-sync python -m playwright install chromium
uv run --no-sync python scripts/measure_compiler.py --browser --repeats 5 \
  --output build/compiler-measurements
```

Choose a new output directory. Omit --browser for the Node/reference and build/
size gates. --channel chrome selects an installed Chrome and records its actual
version. The reference and Node versions in CI are 3.14.7 and 24.19.0; the locked
Playwright 1.64.0 installs its Chromium build. Hardware, OS caches, CPU frequency
and background load are not controlled. Compare reports with matching recorded
inputs and versions; the command accepts other development environments and
reports them rather than silently treating them as identical.

The output contains schema-1 compiler-footprint/1 report.json and twelve
reproducible .tar.gz browser-fixture archives. Reports record the repository
revision/modified state, actual installed compiler source hashes with canonical
LF line endings, measurement/corpus hashes, Python/Node/browser/host versions,
every output file/hash, raw build/startup/heap samples and reference outcomes.
No host-specific absolute source paths are included. The initial observations
were collected before their commit; the recorded script and compiler hashes
identify the actual measurement inputs.

## Payload accounting and behavior

Three fixtures exercise numeric/Unicode values, the shared text-metrics callable,
and its invalid-input error. Each has required/all-profile helpers and included/
omitted maps. The application source and generated executable module statements
are the same within a helper comparison. The baseline includes all synchronous
helpers for a synchronous profile, or all non-browser helpers for an async corpus
case. Injecting browser/async adapters into a synchronous application would change
its requirements and is not a comparable baseline.

The report separates original input source, generated executable modules,
compatibility helpers, source maps, notices, compiler metadata and the small
measurement HTML/worker harness. The physical buckets sum to complete payload
bytes. Original source is a separate input metric; source maps can embed those
same bytes. Interpreter assets are zero in this compiled profile. The browser-host
SDK and pocket-python PWA shell are outside these synchronous fixtures and need
separate complete-application measurements.

Per-file gzip transfer bytes sum gzip level-9, mtime-zero streams for every file;
HTTP headers, TLS framing and server content-encoding policy are excluded. This
is a reproducible transfer estimate, not captured network traffic. A separate
canonical USTAR archive uses sorted paths, fixed modes/ownership/timestamps and
includes archive padding before gzip. Compressed archive bytes and independently
compressed files answer different questions. Record the zlib version when
comparing exact compressed bytes.

The shared computation retains Shimify's exact MIT notice in every corresponding
artifact. Other fixtures are original regression cases. Compiler provenance
notices do not choose a license for the compiler itself. Only these approved
fixtures are executed; the script is not a general application benchmark runner.

## Timing and memory methods

Build samples measure compilation and manifest generation in an already imported
Python process after warming the compiler's Unicode repr table. They exclude
Python startup, dependency installation and filesystem publication. The required
and all-profile variants must emit identical bytes on every repeated build.

Cold browser samples create a fresh storage/HTTP-cache context and a fresh module
worker for each observation. The running browser process and OS caches are
shared. Warm samples use one context, perform an explicit untimed warm-up, then
create a new worker for each observation. HTTP cache is shared; V8 decides whether
its code cache is reusable. Every served file is immutable during the run and
uses max-age=3600. No service worker or server computation enters this measurement.

The page timer starts before worker creation and ends after its result message.
It includes worker bootstrap, application import, module initialization and one
complete call; document navigation is outside that timer. Worker observations
also separate dynamic import from initialization/call time. Every observed result
and original error span must match CPython. Both helper modes additionally run
all 24 positive corpus cases in Node and the browser (48 observations per target).
These include precision/Unicode, side effects, imports, original errors and async
cases; the measured synchronous fixtures do not imply broader browser-host support.

Memory uses separate fresh-context workers, outside startup samples. The command
selects the dedicated worker by URL and browser-context identity, forces a V8 GC,
and reads CDP Runtime.getHeapUsage before importing the application and after
retaining one module/result. It records used/total V8 heap, embedder heap and
backing storage in bytes, plus the used-heap difference. These figures exclude
process RSS, other processes and native/code allocations outside that API. A
post-GC retained heap difference is not peak application memory or a hard memory
limit. Memory samples must also produce the same reference outcome.

The script refuses a measurement if helper variants disagree with the reference,
any timed/memory call changes its result, browser scripts raise unhandled errors,
or requests leave the local static GET fixture. Tests also deliberately corrupt
an arithmetic helper to demonstrate that agreement between two wrong variants
cannot satisfy the CPython gate. Neither smaller source nor a single run's timing
establishes a general speed or memory improvement.

## Recorded observations

[The 2026-10-20 report](measurements/2026-10-20-compiler.json) records five samples
per condition on one Darwin arm64 host, CPython 3.14.7, Node 24.19.0 and Chromium
156.0.8078.4. The tables below describe that run only; raw samples and exact file
identities remain in the report.

| Fixture / variant | Input source B | Helper B | Complete payload B | Per-file gzip B |
| --- | ---: | ---: | ---: | ---: |
| numeric-and-unicode / required-maps | 138 | 9,796 | 17,855 | 6,522 |
| numeric-and-unicode / all-profile-maps | 138 | 23,547 | 31,665 | 11,668 |
| numeric-and-unicode / required-no-maps | 138 | 9,796 | 17,379 | 6,219 |
| numeric-and-unicode / all-profile-no-maps | 138 | 23,547 | 31,189 | 11,367 |
| text-metrics / required-maps | 702 | 10,357 | 25,152 | 8,947 |
| text-metrics / all-profile-maps | 702 | 23,547 | 38,378 | 13,996 |
| text-metrics / required-no-maps | 702 | 10,357 | 23,612 | 8,146 |
| text-metrics / all-profile-no-maps | 702 | 23,547 | 36,838 | 13,194 |
| text-metrics-error / required-maps | 651 | 10,357 | 24,614 | 8,815 |
| text-metrics-error / all-profile-maps | 651 | 23,547 | 37,840 | 13,868 |
| text-metrics-error / required-no-maps | 651 | 10,357 | 23,146 | 8,053 |
| text-metrics-error / all-profile-no-maps | 651 | 23,547 | 36,372 | 13,103 |

| Text-metrics variant | Warm build ms | Cold context ms | Warm context ms | Retained used-heap delta B |
| --- | ---: | ---: | ---: | ---: |
| required-maps | 1.290 | 10.400 | 4.200 | 67,152 |
| all-profile-maps | 1.359 | 10.600 | 4.600 | 107,824 |
| required-no-maps | 1.165 | 10.100 | 4.300 | 67,088 |
| all-profile-no-maps | 1.256 | 10.100 | 4.500 | 107,760 |

Helper selection reduces these fixture payloads relative to their full-profile
baselines. The text-metrics required runtime is 10,357 bytes versus 23,547 bytes
for all synchronous helpers. These observations do not compare full browser
applications, MicroPython, Pyodide or the independent interpreter, and they do not
establish a general startup or memory improvement.
