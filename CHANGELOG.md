# Changelog

## 0.2.0

- Add the binding-aware source compiler, deterministic ES module emitter and original-source diagnostics/maps.
- Compile explicitly supplied local modules and re-exports with selected helper and notice closure.
- Add lazy coroutine/Promise awaits and named browser worker/host capabilities with stop/restart.
- Verify the approved corpus across CPython, Node and Chromium and record scoped payload/startup/memory measurements.
- Preserve the JavaScript runtime namespace and existing Fetch/JSON dependency ranges.

## 0.1.0

- Introduce the case-sensitive `JavaScript` namespace with Object, sparse Array,
  UTF-16 String methods, Number, Boolean, selected Math functions and JSON.
- Add undefined, truthiness, conversion, equality and parsing helpers.
- Depend on standalone JavaScript-Fetch-API 0.2 and JavaScript-JSON 0.1; expose
  Fetch and Promise without duplicating their implementations.
- Document the supported compatibility subset and future translation direction.
