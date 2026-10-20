# Compiling local source modules

The development checkout provides `JavaScript.modules.compile_modules`. The
published 0.1.0 package predates this API. `python-browser-modules/1` extends the
[single-module language](compiler-language.md) with explicit named source imports.

```python
from pathlib import Path
from JavaScript.modules import SourceModule, compile_modules

sources = (
    SourceModule.from_text("app", "from helpers import size\nprint(size('A😀'))"),
    SourceModule.from_text("helpers", "def size(text):\n    return len(text)"),
)
artifact = compile_modules(sources, entrypoint="app")
destination = Path("compiled")
for output in artifact.files:
    path = destination / output.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output.data)
(destination / "manifest.json").write_bytes(artifact.manifest_bytes)
```

Load `createModule` from the generated `app.mjs` and call it to initialize a new
application context. Its `write` option receives Python print output, including
newlines. The entrypoint is imported under its declared identity; it is not
executed a second time as `__main__`.

## Inputs and imports

Supply an immutable tuple of `SourceModule` records. Each record contains its
qualified module name, exact immutable UTF-8 bytes, SHA-256, package flag and
logical relative `.py` filename. Direct construction validates the supplied
hash; `from_text` computes it. Compilation rechecks records. Logical filenames
are source-map identities, not paths the compiler opens. No target module is
imported or executed during compilation.

The allowlist contains at most 32 modules, 1 MiB per module and 8 MiB total.
Module identities use ordinary ASCII Python names and cannot shadow the stdlib
or the JavaScript registry. Module names and portable logical filenames must be
unique, including when case folded. Every parent package needs an explicitly
declared `is_package=True` initializer. Only reachable modules and their parent
initializers are parsed and emitted; supplied unused modules are omitted.

Supported source imports are unconditional top-level named imports, including
aliases, relative imports and package re-exports:

```python
from text_metrics import metrics as selected
from .helpers import character_count as count_characters
```

Exports can be supported plain functions, immutable module constants or
re-exported source bindings. JavaScript registry imports retain their separate
binding rules and cannot be re-exported through the Python source namespace.
Plain local `import module`, wildcard, conditional/function-local, dynamic,
stdlib/native-extension and undeclared imports fail with source-located
diagnostics. Explicit source-import cycles are deterministically rejected.
Required parent initializer ordering supports a package re-exporting a child;
it does not authorize general partially initialized module cycles.

Import statements execute in source order, each module initializes once per
application context, and parents initialize before children. Reading a binding
before its defining statement still raises the adopted Python error. One shared
runtime preserves imported callable, tuple and string identities, immutable
function defaults, recursion limits and the output sink. Entry exports wrap
callables once per context for JavaScript invocation; internal imports use the
original Python values. Each `createModule` call creates independent state.

## Artifacts and limits

The manifest has kind `python-javascript-compiled`, schema 1, compiler ABI
`python-browser-modules-esm/1` and language profile `python-browser-modules/1`.
It records selected modules/exports, Python source import edges, per-module
source hashes and filenames, the static emitted import closure, required helper
closure, file sizes/hashes and notices. Deterministically named module factories
share `runtime.mjs`; `app.mjs` statically imports every emitted dependency.
Source maps retain each original module's text. `source_map=False` omits maps.

Original nonempty notices may be passed as immutable `OutputFile` records with
role `notice`, under portable `LICENSES/` paths. They are copied unchanged and
hashed. The compiler's provenance notice grants no additional license rights.
No runtime dependency on Shimify is introduced. Shimify may produce the verified
source bytes used here, but unchanged supported modules also compile directly.

The text_metrics parity fixture uses its supported metrics module and the
reduced helper containing `character_count`. The original helper's unused slice
utility remains unsupported and causes rejection if supplied unchanged. This
compiler does not perform symbol extraction or silently skip unsupported code
inside a selected module. The [browser profile](compiler-browser.md) adds DOM/Fetch integration. Runtime
parsing of new source remains an independent-interpreter task.
