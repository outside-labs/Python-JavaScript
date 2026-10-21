# Experimental ES module emitter

Version 0.2.0 exposes `JavaScript.emitter.compile_source`. It
validates source through the python-browser/1 front end, lowers the immutable IR
and returns a CompiledArtifact without executing input or writing files. The
published 0.1.0 package predates this compiler implementation.

```python
from JavaScript.emitter import compile_source

artifact = compile_source(
    "def count(text):\n    return len(text)",
    filename="counter.py",
)
print(artifact.manifest["application_exports"])  # ['count']
```

`files` is a tuple of immutable OutputFile(path, data, role) values. The caller
can inspect or pass those bytes to the pocket-python 0.2 application builder.
The manifest bytes are separate from their own file/hash closure and can be
saved as PYTHON-JAVASCRIPT.json. Every recorded file has exact size, SHA-256 and
role; imports, notices and selected helper dependencies are explicit. Current
single-module output has no static imports. The compiler ABI is
python-browser-esm/1, independently of package and application-profile versions.

The emitted entrypoint is app.mjs by default, with a named `createModule` export:

```javascript
import {createModule} from './app.mjs';
const app = createModule({write: text => console.log(text)});
console.log(app.count('A😀')); // 2n
```

Each factory call initializes a fresh module in Python source order. Top-level
print/call statements execute at that time. Functions are assigned when their
definition executes; immutable literal defaults are created once per definition,
including tuple identity across calls. Function-local unbound values and global
use before definition raise source-located Python errors. Imports/aliases resolve
through the validated JavaScript registry; only Array.of/length are adopted.
The default output sink uses console.log with the print newline removed.

External function arguments accept BigInt, bool, null and native JavaScript
strings. Number is rejected to avoid ambiguous rounded integers. An explicit
`{type:'str', codepoints:[...]}` preserves Python surrogate/code-point distinctions;
`{type:'tuple', items:[...]}` constructs a Python tuple. Cycles, arbitrary host
objects and input depth over 64 fail explicitly. Native string input iterates
Unicode code points at the boundary. Exported strings/tuples retain their frozen
str/codepoints or tuple/items wrappers; they are not JavaScript arrays. The host
protocol adapter will serialize these values separately.

Python integers use BigInt, including signed floor division/modulo and numeric
bool behavior. Strings retain code points, negative indexing, membership and
lexicographic ordering. Tuples retain truthiness, iteration, equality/order and
alias identity. Chained comparisons and boolean operators evaluate each operand
once, in order, with short-circuiting and original operand results.

Print formats supported values using Python spelling and tuple/string repr.
The compiler generates a compact nonprintable-range table from its CPython
Unicode database and records that database version, so a newer JavaScript
Unicode database cannot silently change repr. This is build-time data, not
runtime Python delegation. Raw surrogate text output requires a separately
adopted sink and fails explicitly; escaped surrogate tuple repr is supported.
Integer/string interning identity remains outside the profile. Dynamic values
outside an adopted operation fail with a source-located TypeError rather than
coercing to native JavaScript behavior.

Compiled calls use an explicit depth limit of 128 and report RecursionError
before depending on host stack exhaustion. This is a profile resource limit,
not CPython's configurable recursion limit. Arbitrary compiled applications are
not instruction/memory sandboxed; the independent VM has its own budget model.
Unsupported syntax/imports fail compilation before an artifact is returned.
Ordinary error classes are preserved; argument-count wording is profile-specific.

Source maps use version 3 and original logical filename, lines/columns and
sourcesContent. Runtime errors also carry original location records. Pass
source_map=False to omit map bytes and their sourceMappingURL together. Use a
logical filename when artifacts are intended for distribution; maps intentionally
include the selected source. module_name must be a portable .mjs basename.

Only selected helpers and their declared dependency closure enter the output.
NOTICES.txt records original helper provenance; no third-party interpreter or
runtime is embedded. The repository has no declared code license; this notice
does not choose or grant one. Redistribution licensing remains a release decision.

Run `python -m unittest discover -s tests -p 'test_compiler*.py' -v` with the
installed package and Node 24.19.0. Tests compare CPython and emitted
Node output/errors/evaluation order, the single-module text_metrics application,
precision/Unicode/tuple/default behavior and an independent Node source-map
consumer. Local modules and async browser capabilities have separate adopted
profiles. The shared [compiler-parity/1 suite](compiler-conformance.md) compares
emitted Node and browser-worker execution with CPython. This compiler executes only
ahead-of-time approved source; it does not parse new source in the browser.

Exception construction does not start a traceback. An explicit raise records
its statement span; rejecting a Promise with an unraised exception records the
first source await. Errors already raised in a function/callback keep that
origin when propagated through awaits. Exception values retain identity. Native
stack capture, where available, maps explicit raises to their statement; full
Python call-frame construction remains separately staged.
