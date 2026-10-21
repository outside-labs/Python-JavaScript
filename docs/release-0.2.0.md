# Python-JavaScript 0.2.0

An experimental minor release for Python 3.14+. The case-sensitive `JavaScript`
compatibility namespace and the existing Fetch/JSON companion dependency ranges
are retained. No new runtime dependency is introduced.

## Compiler and browser target

The distribution now includes `JavaScript.compiler.parse_source`,
`JavaScript.emitter.compile_source`, `JavaScript.modules.compile_modules` and
`JavaScript.browser.compile_browser`, plus the matching `.mjs` worker/host assets.
They parse/bind a documented Python subset at build time and produce deterministic
ES modules, selected compatibility helpers, original-source maps, hashes and
provenance notices. They never import or execute the target source to compile it.

Adopted profiles cover Python large integers, code-point strings and tuples,
short-circuit/evaluation order, plain functions with immutable defaults, verified
named local modules/re-exports, and explicit async/browser host capabilities.
Named controls, text output, callbacks and exact URL-granted Fetch execute through
the versioned browser worker protocol. Stop/restart releases the worker/session.

The [compiler language](compiler-language.md), [modules](compiler-modules.md),
[async](compiler-async.md) and [browser target](compiler-browser.md) documents
specify the exact boundaries. CPython/Node/Chromium differential reports and
component measurements cover the approved corpus; measurements are fixture and
engine specific and do not establish a general size/speed advantage.

## Limits

This is ahead-of-time compilation. It does not parse newly entered Python in a
browser or delegate to a Python interpreter. Arbitrary packages/stdlib, classes,
descriptors, dynamic imports, unrestricted host attributes and unlisted Python or
ECMAScript APIs remain unsupported. Unsupported syntax is rejected with original
source diagnostics. Compiled applications require the documented external argument
representations and are not instruction/memory sandboxed.

The repository has no declared code license; this release retains that metadata.
Original helper provenance and the borrowed fixture's MIT notice are preserved;
provenance does not grant additional redistribution rights.

## Publication gates

Require installed-wheel and installed-sdist tests on Linux/macOS/Windows, full
approved browser conformance, strict distribution allowlists/metadata, and final
main CI. Publish immutable `v0.2.0` through the existing `pypi` Trusted Publisher,
compare PyPI hashes with workflow artifacts, then test a fresh installation and
compile/run a representative module before closing
[REL-03](https://github.com/outside-labs/Python-JavaScript/issues/38).
