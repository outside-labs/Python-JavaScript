# Compiler front end

Version 0.2.0 provides JavaScript.compiler.parse_source(source,
filename=...) for the adopted python-browser/1 profile. It parses, binds and
validates source without running target code, then returns an immutable ModuleIR.
Use `JavaScript.emitter.compile_source` to emit executable JavaScript from this IR.

The API uses only the declared Python runtime and standard library. A ModuleIR
records profile/schema identity, SHA-256 of UTF-8 input, stable lexical binding
IDs and typed nodes with original source spans. to_dict returns an independent
JSON-serializable snapshot; integer constants are decimal strings tagged as
python-int so an IR consumer cannot lose precision through JSON numbers.

Bindings distinguish module constants/functions, function parameters/locals,
builtin APIs and explicit JavaScript registry aliases. Alias resolution follows
binding identity: a parameter named len or Array is not rewritten to a builtin
or imported intrinsic. Branch and loop value types merge conservatively; source
order, guards, defaults and errors remain represented for the emitter.

CompileError exposes a Diagnostic with code, phase, message and SourceSpan.
Locations use one-based character columns, converting Python AST's UTF-8 byte
offsets. PJS100 covers syntax/features, PJS110 binding/import boundaries and
PJS120 unsupported operations/calls. Unknown syntax/imports are refused before
any output publication or target execution. Syntax, binding and validation
phases remain distinct.

Use the adopted language contract for supported forms. Initial module bindings
are unconditional immutable literals; for loops are function-local with simple
targets and no else clause. Source is UTF-8 and limited to 1 MiB. This front end
does not load Python application imports, provide browser APIs or certify that
arbitrary dependencies can be translated.
