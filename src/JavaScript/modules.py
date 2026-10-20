"""Compile a closed, verified set of ordinary source modules to local ES modules."""

import ast
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import keyword
from pathlib import PurePosixPath
import re
import sys
import unicodedata

from .compiler import (CompileError, Diagnostic, ModuleIR, SourceImport, SourceSpan,
                       _FrontEnd, _immutable, _literal_type)
from .emitter import CompiledArtifact, OutputFile, _Emitter, _json
from ._compiler_runtime import HELPER_BINDINGS, helper_closure, helper_source


def _portable(path):
    relative = PurePosixPath(path)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    return (bool(relative.parts) and not relative.is_absolute() and '..' not in relative.parts and str(relative) == path
            and all(part.split('.')[0].upper() not in reserved and not part.endswith(('.', ' '))
                    and not any(ord(character) < 32 or character in '\\:*?"<>|' for character in part)
                    for part in relative.parts))


@dataclass(frozen=True)
class SourceModule:
    name: str
    data: bytes
    sha256: str
    is_package: bool = False
    filename: str | None = None

    def __post_init__(self):
        if (not isinstance(self.name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*', self.name)
                or any(keyword.iskeyword(part) for part in self.name.split('.'))
                or self.name == '__main__' or self.name.split('.')[0] in {*sys.stdlib_module_names, 'JavaScript'}):
            raise ValueError('Use an ordinary source module name without stdlib/registry shadowing.')
        if type(self.data) is not bytes or len(self.data) > 1_048_576:
            raise ValueError('Source requires immutable UTF-8 bytes, at most 1 MiB per module.')
        self.data.decode('utf-8')
        if hashlib.sha256(self.data).hexdigest() != self.sha256:
            raise ValueError('Source SHA-256 does not match its supplied bytes.')
        if type(self.is_package) is not bool:
            raise TypeError('is_package must be bool')
        filename = self.filename
        if filename is None:
            filename = self.name.replace('.', '/') + ('/__init__.py' if self.is_package else '.py')
        if not isinstance(filename, str) or not _portable(filename) or not filename.endswith('.py'):
            raise ValueError('filename must be a portable relative logical .py path')
        filename.encode('utf-8')
        object.__setattr__(self, 'filename', filename)

    @classmethod
    def from_text(cls, name, text, *, is_package=False, filename=None):
        data = text.encode('utf-8')
        return cls(name, data, hashlib.sha256(data).hexdigest(), is_package, filename)


class _Modules:
    def __init__(self, sources, entrypoint, async_enabled):
        self.async_enabled = async_enabled
        if not isinstance(sources, tuple) or any(not isinstance(source, SourceModule) for source in sources):
            raise TypeError('sources must be a tuple of verified SourceModule records')
        if not 1 <= len(sources) <= 32 or sum(len(source.data) for source in sources) > 8_388_608:
            raise ValueError('Declare 1–32 source modules, at most 8 MiB total.')
        if len({source.name.casefold() for source in sources}) != len(sources):
            raise ValueError('Source module identities must be unique and portable.')
        if len({source.filename.casefold() for source in sources}) != len(sources):
            raise ValueError('Logical source filenames must be unique and portable.')
        # Recheck snapshots at the compiler boundary, including constructed records.
        for source in sources:
            source.__post_init__()
        self.sources = {source.name: source for source in sources}
        if entrypoint not in self.sources:
            raise ValueError('entrypoint must name a declared source module')
        self.entrypoint = entrypoint
        self.trees, self.imports, self.dependencies, self.declarations = {}, {}, {}, {}
        pending = [entrypoint]
        while pending:
            name = pending.pop()
            if name in self.trees:
                continue
            source = self.sources[name]
            try:
                tree = ast.parse(source.data.decode('utf-8'), filename=source.filename)
            except SyntaxError as error:
                span = SourceSpan(source.filename, error.lineno or 1, error.offset or 1,
                                  error.end_lineno or error.lineno or 1, error.end_offset or error.offset or 1)
                raise CompileError(Diagnostic('PJS100', error.msg, span, 'parse')) from None
            self.trees[name] = tree
            self.imports[name], self.dependencies[name], self.declarations[name] = [], set(), {}
            for index in range(1, len(name.split('.'))):
                parent = '.'.join(name.split('.')[:index])
                if parent not in self.sources or not self.sources[parent].is_package:
                    self.fail(name, 'Every parent requires an explicitly supplied package initializer.')
                pending.append(parent)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                if node not in tree.body:
                    self.fail(name, 'Source imports require unconditional module bindings.', node, 'PJS100')
                registry = isinstance(node, ast.Import) and all(alias.name == 'JavaScript' for alias in node.names)
                registry = registry or isinstance(node, ast.ImportFrom) and not node.level and node.module == 'JavaScript'
                if registry:
                    continue
                if isinstance(node, ast.Import):
                    self.fail(name, 'Local modules require explicit named from-imports.', node)
                base = self.absolute(name, node)
                if base not in self.sources or any(alias.name == '*' for alias in node.names):
                    self.fail(name, 'Import requires a declared source module and explicit exported names.', node)
                self.imports[name].append((node, base))
                self.dependencies[name].add(base)
                pending.append(base)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.declarations[name][node.name] = ('function', node)
                elif isinstance(node, ast.Assign):
                    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                        self.declarations[name][node.targets[0].id] = ('constant', node)
            for node, base in self.imports[name]:
                for alias in node.names:
                    self.declarations[name][alias.asname or alias.name] = ('import', (node, base, alias.name))
        visiting, visited = set(), set()
        def visit(name):
            if name in visiting:
                self.fail(name, 'Explicit source-import cycles are outside this module profile.')
            if name in visited:
                return
            visiting.add(name)
            for dependency in sorted(self.dependencies[name]):
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
        for name in sorted(self.trees):
            visit(name)

    def fail(self, name, message, node=None, code='PJS110'):
        source = self.sources[name]
        span = SourceSpan(source.filename, 1, 1, 1, 1)
        if node is not None:
            lines = source.data.decode('utf-8').splitlines()
            def column(line, offset):
                return len(lines[line - 1].encode('utf-8')[:offset].decode('utf-8')) + 1
            span = SourceSpan(source.filename, node.lineno, column(node.lineno, node.col_offset),
                              node.end_lineno, column(node.end_lineno, node.end_col_offset))
        raise CompileError(Diagnostic(code, message, span, 'bind' if code == 'PJS110' else 'validate'))

    def absolute(self, name, node):
        if not node.level:
            return node.module
        package = name if self.sources[name].is_package else name.rpartition('.')[0]
        parts = package.split('.') if package else []
        if node.level > len(parts):
            self.fail(name, 'Relative import escapes its declared package.', node)
        return '.'.join([*parts[:len(parts) - node.level + 1], *([node.module] if node.module else [])])

    def export_type(self, name, exported, requester, node):
        declaration = self.declarations[name].get(exported)
        if declaration is None:
            self.fail(requester, 'Export is outside the declared Python namespace: ' + name + ':' + exported, node)
        kind, value = declaration
        if kind == 'function':
            return 'async-callable' if isinstance(value, ast.AsyncFunctionDef) else 'callable'
        if kind == 'constant':
            if not _immutable(value.value):
                self.fail(name, 'Module bindings require immutable literals.', value, 'PJS100')
            result = _literal_type(ast.literal_eval(value.value))
            if result is None:
                self.fail(name, 'Literal type is outside this profile.', value, 'PJS100')
            return result
        original, base, target = value
        return self.export_type(base, target, name, original)

    def lower(self, name):
        source = self.sources[name]
        imports = {(node.lineno, node.col_offset): tuple(
                    SourceImport(alias.asname or alias.name, base, alias.name,
                                 self.export_type(base, alias.name, name, node)) for alias in node.names)
                   for node, base in self.imports[name]}
        frontend = _FrontEnd(source.data.decode('utf-8'), source.filename, imports, async_enabled=self.async_enabled)
        body = frontend.statements(frontend.tree.body)
        return ModuleIR(source.filename, source.sha256,
                        tuple(frontend.bindings[key] for key in sorted(frontend.bindings)), body,
                        profile='python-browser-modules-async/1' if self.async_enabled else 'python-browser-modules/1')


def compile_modules(sources: tuple[SourceModule, ...], *, entrypoint: str,
                    source_map: bool = True, async_enabled: bool = False, notices: tuple[OutputFile, ...] = ()) -> CompiledArtifact:
    """Compile a verified source allowlist, never reading or executing target files."""
    if type(source_map) is not bool:
        raise TypeError('source_map must be bool')
    if type(async_enabled) is not bool:
        raise TypeError('async_enabled must be bool')
    graph = _Modules(sources, entrypoint, async_enabled)
    output, required, module_records = [], {'async-expose' if async_enabled else 'input'}, []
    modules = sorted(graph.trees)
    for index, name in enumerate(modules):
        source = graph.sources[name]
        filename = f'module-{index:03}.mjs'
        files, helpers, exports = _Emitter(graph.lower(name)).render(
            source.data.decode('utf-8'), filename, source_map, shared_runtime=True)
        output.extend(files)
        required.update(helpers)
        module_records.append({'module': name, 'file': filename, 'is_package': source.is_package,
                               'exports': exports, 'source': source.filename, 'sha256': source.sha256})
    helpers = helper_closure(required)
    bindings = [binding for helper in helpers for binding in HELPER_BINDINGS[helper]]
    runtime = ["export function createRuntime(write" + (", signal = null" if async_enabled else "") + ") {", "  if(typeof write!=='function')throw new TypeError('write must be a function');"]
    for helper in helpers:
        runtime.extend('  ' + line for line in helper_source(helper).splitlines())
    runtime.extend(['  return Object.freeze({' + ','.join(bindings) + '});', '}'])
    output.append(OutputFile('runtime.mjs', ('\n'.join(runtime) + '\n').encode(), 'compatibility-helper'))
    imports = ["import {createRuntime} from './runtime.mjs';"]
    imports.extend(f"import {{initialize as module{index}}} from './{record['file']}';" for index, record in enumerate(module_records))
    registry = '[' + ','.join('[' + _json(record['module']) + ',module' + str(index) + ']' for index, record in enumerate(module_records)) + ']'
    packages = _json([record['module'] for record in module_records if record['is_package']])
    location = _json({'filename': graph.sources[entrypoint].filename, 'line': 1, 'column': 1, 'end_line': 1, 'end_column': 1})
    expose = '$asyncExpose' if async_enabled else '$expose'
    signal_option = ', signal = null' if async_enabled else ''
    signal_argument = ',signal' if async_enabled else ''
    entry = '\n'.join(imports) + '\n' + f'''
export function createModule({{write = text => console.log(text.slice(0,-1)){signal_option}}} = {{}}) {{
  const runtime=createRuntime(write{signal_argument}), factories=new Map({registry}), packages=new Set({packages}), cache=new Map(), loading=new Set();
  function importModule(name) {{
    if(cache.has(name))return cache.get(name);
    const parent=name.includes('.')?name.slice(0,name.lastIndexOf('.')):null;
    if(parent && packages.has(parent) && !loading.has(parent))importModule(parent);
    if(cache.has(name))return cache.get(name);
    if(loading.has(name))throw new Error('Source-import cycle is outside this profile.');
    if(!factories.has(name))throw new Error('Undeclared compiled source module.');
    loading.add(name);
    const value=factories.get(name)(runtime,importModule);
    loading.delete(name);cache.set(name,value);return value;
  }}
  const module=importModule({_json(entrypoint)});
  return Object.freeze(Object.fromEntries(Object.entries(module).map(([name,value])=>[name,runtime.{expose}(value,{location})])));
}}
'''
    output.append(OutputFile('app.mjs', entry.encode('utf-8'), 'executable-module'))
    compiler_version = version('Python-JavaScript')
    output.append(OutputFile('NOTICES.txt', ('Generated by Python-JavaScript ' + compiler_version +
        '\nhttps://github.com/outside-labs/Python-JavaScript\nOriginal compiler helpers; no third-party runtime is embedded.\nThis provenance notice grants no additional license rights.\n').encode(), 'notice'))
    if not isinstance(notices, tuple) or any(not isinstance(item, OutputFile) or item.role != 'notice'
            or not item.path.startswith('LICENSES/') or not _portable(item.path)
            or type(item.data) is not bytes or not item.data.strip() for item in notices):
        raise ValueError('notices must contain nonempty immutable notice files under LICENSES/.')
    output.extend(notices)
    if len({item.path.casefold() for item in output}) != len(output):
        raise ValueError('Artifact paths must be unique and portable.')
    if any(left.path.casefold().startswith(right.path.casefold() + '/') for left in output for right in output):
        raise ValueError('Artifact file/directory paths collide.')
    files = tuple(sorted(output, key=lambda item: item.path))
    manifest = {'kind': 'python-javascript-compiled', 'schema_version': 1,
                'compiler': {'name': 'Python-JavaScript', 'version': compiler_version, 'abi': 'python-browser-modules-async-esm/1' if async_enabled else 'python-browser-modules-esm/1'},
                'language_profile': 'python-browser-modules-async/1' if async_enabled else 'python-browser-modules/1', 'target': 'ecmascript-2022-module',
                'unicode_version': unicodedata.unidata_version, 'entrypoint': 'app.mjs', 'entrypoint_export': 'createModule',
                'application_exports': next(record['exports'] for record in module_records if record['module'] == entrypoint),
                'modules': module_records, 'helpers': list(helpers),
                'sources': [{'path': graph.sources[name].filename, 'sha256': graph.sources[name].sha256, 'size': len(graph.sources[name].data)} for name in modules],
                'imports': [{'from': 'app.mjs', 'to': name} for name in ['runtime.mjs', *[record['file'] for record in module_records]]],
                'source_imports': [{'from': name, 'to': dependency} for name in modules for dependency in sorted(graph.dependencies[name])],
                'notices': sorted(item.path for item in files if item.role == 'notice'),
                'files': [{'path': item.path, 'size': len(item.data), 'sha256': hashlib.sha256(item.data).hexdigest(), 'role': item.role} for item in files]}
    return CompiledArtifact(files, (_json(manifest) + '\n').encode('utf-8'))
