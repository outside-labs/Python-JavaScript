"""Deterministic ES modules for the validated python-browser/1 source profile."""

from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import json
import re
import unicodedata

from .compiler import parse_source
from ._compiler_runtime import HELPER_BINDINGS, helper_closure, helper_source


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


@dataclass(frozen=True)
class OutputFile:
    path: str
    data: bytes
    role: str


@dataclass(frozen=True)
class CompiledArtifact:
    files: tuple[OutputFile, ...]
    manifest_bytes: bytes

    @property
    def manifest(self):
        """Return a fresh snapshot; callers cannot mutate artifact metadata."""
        return json.loads(self.manifest_bytes)


def _vlq(value):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    value = (-value << 1 | 1) if value < 0 else value << 1
    encoded = ''
    while True:
        digit = value & 31
        value >>= 5
        encoded += alphabet[digit | (32 if value else 0)]
        if not value:
            return encoded


def _contains_await(node):
    if not hasattr(node, 'fields'):
        return any(_contains_await(item) for item in node) if isinstance(node, tuple) else False
    return node.kind == 'await' or any(_contains_await(value) for _, value in node.fields)


class _Emitter:
    def __init__(self, module):
        self.module = module
        self.bindings = {binding.id: binding for binding in module.bindings}
        self.names = {binding.id: '$v' + str(index) for index, binding in enumerate(module.bindings)}
        self.required = set()
        self.lines = []
        self.counter = 0

    def use(self, helper):
        self.required.add(helper)

    def temporary(self):
        self.counter += 1
        return '$t' + str(self.counter)

    def location(self, node):
        return _json(vars(node.span))

    def add(self, text, indent=1, node=None):
        self.lines.append(('  ' * indent + text, node.span if node else None))

    def expression(self, node):
        fields, location = dict(node.fields), self.location(node)
        kind = node.kind
        if kind == 'constant':
            if node.value_type == 'python-int':
                return fields['value'] + 'n'
            if node.value_type == 'python-str':
                self.use('str')
                return '$str(' + _json([ord(character) for character in fields['value']]) + ')'
            return _json(fields['value'])
        if kind == 'tuple':
            self.use('tuple')
            return '$tuple([' + ','.join(map(self.expression, fields['values'])) + '])'
        if kind == 'name':
            binding = self.bindings[fields['binding']]
            if binding.kind == 'builtin':
                name = binding.name
                if name in {'str', 'int', 'bool', 'tuple'}:
                    self.use('types')
                    return '$types.' + name
                helper, value = {'len': ('len', '$len'), 'print': ('print', '$print'),
                                 'isinstance': ('types', '$isinstance'), 'TypeError': ('exception', '$TypeError')}[name]
                self.use(helper)
                return value
            self.use('binding')
            return f'$get({self.names[binding.id]},{_json(binding.name)},{str(binding.kind in {"local", "parameter"}).lower()},{location})'
        if kind == 'await':
            self.use('async')
            return f'(await $await({self.expression(fields["value"])},{location}))'
        if kind == 'async-attribute':
            self.use('async')
            return f'$asyncAttribute({self.expression(fields["value"])},{_json(fields["name"])},{location})'
        if kind == 'attribute':
            self.use('javascript')
            return f'$attribute({self.expression(fields["value"])},{_json(fields["name"])},{location})'
        if kind == 'call':
            self.use('call')
            return f'$call({self.expression(fields["function"])},[{",".join(map(self.expression, fields["arguments"]))}],{location})'
        if kind in {'binary', 'unary', 'index'}:
            self.use(kind)
            if kind == 'binary':
                values = [_json(fields['operator']), self.expression(fields['left']), self.expression(fields['right'])]
            elif kind == 'unary':
                values = [_json(fields['operator']), self.expression(fields['value'])]
            else:
                values = [self.expression(fields['value']), self.expression(fields['index'])]
            return '$' + kind + '(' + ','.join([*values, location]) + ')'
        if kind == 'boolean':
            self.use('truth')
            name = self.temporary()
            values = fields['values']
            pieces = [f'let {name}={self.expression(values[0])};']
            for value in values[1:]:
                condition = f'$truth({name},{location})'
                if fields['operator'] == 'and':
                    condition = '!' + condition
                pieces.extend([f'if({condition})return {name};', f'{name}={self.expression(value)};'])
            code = '(()=>{' + ''.join(pieces) + f'return {name};' + '})()'
            return '(await ' + code.replace('(()=>', '(async()=>', 1) + ')' if _contains_await(node) else code
        if kind == 'compare':
            self.use('compare')
            left, right = self.temporary(), self.temporary()
            pieces = [f'let {left}={self.expression(fields["values"][0])};let {right};']
            for operator, value in zip(fields['operators'], fields['values'][1:]):
                pieces.extend([f'{right}={self.expression(value)};',
                    f'if(!$compare({_json(operator)},{left},{right},{location}))return false;', f'{left}={right};'])
            code = '(()=>{' + ''.join(pieces) + 'return true;})()'
            return '(await ' + code.replace('(()=>', '(async()=>', 1) + ')' if _contains_await(node) else code
        raise AssertionError('Unrecognized validated expression: ' + kind)

    def statements(self, nodes, indent=1):
        for node in nodes:
            if 'async/' in self.module.profile:
                self.use('async')
                self.add(f'$checkpoint({self.location(node)});', indent, node)
            self.statement(node, indent)

    def statement(self, node, indent):
        fields, kind = dict(node.fields), node.kind
        if kind == 'source-import':
            temporary = self.temporary()
            self.add(f'const {temporary}=importModule({_json(fields["module"])});', indent, node)
            for identifier, exported in fields['bindings']:
                self.add(f'{self.names[identifier]}={temporary}[{_json(exported)}];', indent, node)
        elif kind == 'import':
            self.use('javascript')
            for identifier in fields['bindings']:
                target = self.bindings[identifier].target
                if target == 'JavaScript.Promise':
                    self.use('async')
                value = {'JavaScript': '$JS', 'JavaScript.Array': '$JArray', 'JavaScript.Promise': '$PromiseRegistry'}[target]
                self.add(f'{self.names[identifier]}={value};', indent, node)
        elif kind == 'function':
            self.use('call')
            binding = self.bindings[fields['binding']]
            defaults = '[' + ','.join(map(self.expression, fields['defaults'])) + ']'
            asynchronous = fields.get('asynchronous', False)
            if asynchronous:
                self.use('async')
            factory, modifier = ('$cfn', 'async ') if asynchronous else ('$fn', '')
            self.add(f'{self.names[binding.id]}={factory}({_json(binding.name)},{len(fields["parameters"])},{defaults},{modifier}($args)=>{{', indent, node)
            locals_ = [item for item in self.module.bindings if item.scope == 'function:' + binding.name]
            if locals_:
                self.use('binding')
                self.add('let ' + ','.join(self.names[item.id] + '=$UNBOUND' for item in locals_) + ';', indent + 1)
            for index, parameter in enumerate(fields['parameters']):
                self.add(f'{self.names[parameter]}=$args[{index}];', indent + 1)
            self.statements(fields['body'], indent + 1)
            self.add('return null;', indent + 1)
            self.add('});', indent)
        elif kind == 'assign':
            temporary = self.temporary()
            self.add(f'const {temporary}={self.expression(fields["value"])};', indent, node)
            for target in fields['targets']:
                self.add(f'{self.names[target]}={temporary};', indent, node)
        elif kind in {'expression', 'return', 'raise'}:
            value = self.expression(fields['value']) if fields['value'] else 'null'
            prefix = {'expression': '', 'return': 'return ', 'raise': 'throw '}[kind]
            self.add(prefix + value + ';', indent, node)
        elif kind == 'if':
            self.use('truth')
            self.add(f'if($truth({self.expression(fields["test"])},{self.location(node)})){{', indent, node)
            self.statements(fields['body'], indent + 1)
            if fields['otherwise']:
                self.add('}else{', indent)
                self.statements(fields['otherwise'], indent + 1)
            self.add('}', indent)
        elif kind == 'for':
            self.use('iterate')
            temporary = self.temporary()
            self.add(f'for(const {temporary} of $iterate({self.expression(fields["value"])},{self.location(node)})){{', indent, node)
            self.add(f'{self.names[fields["target"]]}={temporary};', indent + 1)
            self.statements(fields['body'], indent + 1)
            self.add('}', indent)
        elif kind in {'break', 'continue'}:
            self.add(kind + ';', indent, node)
        elif kind == 'pass':
            self.add(';', indent, node)
        else:
            raise AssertionError('Unrecognized validated statement: ' + kind)

    def render(self, source, module_name, source_map, *, shared_runtime=False):
        roots = [binding for binding in self.module.bindings if binding.scope == 'module']
        if roots:
            self.use('binding')
            self.add('let ' + ','.join(self.names[binding.id] + '=$UNBOUND' for binding in roots) + ';')
        self.statements(self.module.body)
        exports = [binding for binding in roots if binding.kind != 'javascript']
        items = []
        for binding in exports:
            value = self.names[binding.id]
            if binding.kind == 'function' and not shared_runtime:
                self.use('async-expose' if 'async/' in self.module.profile else 'input')
                definition = next(node for node in self.module.body if node.kind == 'function' and node.field('binding') == binding.id)
                expose = '$asyncExpose' if 'async/' in self.module.profile else '$expose'
                value = f'{expose}({value},{self.location(definition)})'
            items.append(f'[{_json(binding.name)}]:{value}')
        self.add('return Object.freeze({' + ','.join(items) + '});')
        helpers = helper_closure(self.required)
        if shared_runtime:
            names = [name for helper in helpers for name in HELPER_BINDINGS[helper]]
            lines = [('export function initialize(runtime, importModule) {', None)]
            if names:
                lines.append(('  const {' + ','.join(names) + '}=runtime;', None))
        else:
            option = ', signal = null' if 'async/' in self.module.profile else ''
            lines = [('export function createModule({write = text => console.log(text.slice(0,-1))' + option + '} = {}) {', None),
                     ("  if(typeof write !== 'function')throw new TypeError('write must be a function');", None)]
            for helper in helpers:
                lines.extend(('  ' + line, None) for line in helper_source(helper).splitlines())
        lines.extend(self.lines)
        lines.append(('}', None))
        mappings, previous_line, previous_column = [], 0, 0
        for text, span in lines:
            if span:
                column = len(text) - len(text.lstrip())
                mappings.append(''.join(_vlq(value) for value in [column, 0, span.line - 1 - previous_line, span.column - 1 - previous_column]))
                previous_line, previous_column = span.line - 1, span.column - 1
            else:
                mappings.append('')
        code = '\n'.join(text for text, _ in lines) + '\n'
        output = [OutputFile(module_name, code.encode('utf-8'), 'executable-module')]
        if source_map:
            code += '//# sourceMappingURL=' + module_name + '.map\n'
            output[0] = OutputFile(module_name, code.encode('utf-8'), 'executable-module')
            data = {'version': 3, 'file': module_name, 'sources': [self.module.filename],
                    'sourcesContent': [source], 'names': [], 'mappings': ';'.join(mappings)}
            output.append(OutputFile(module_name + '.map', (_json(data) + '\n').encode('utf-8'), 'source-map'))
        return output, helpers, [binding.name for binding in exports]


def compile_source(source: str, *, filename: str = 'app.py', module_name: str = 'app.mjs',
                   source_map: bool = True, async_enabled: bool = False) -> CompiledArtifact:
    """Compile one approved module to immutable artifacts; do not execute or publish it."""
    if not isinstance(module_name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*\.mjs', module_name):
        raise ValueError('module_name must be a portable .mjs basename')
    if type(source_map) is not bool:
        raise TypeError('source_map must be bool')
    module = parse_source(source, filename=filename, async_enabled=async_enabled)
    output, helpers, exports = _Emitter(module).render(source, module_name, source_map)
    compiler_version = version('Python-JavaScript')
    notice = ('Generated by Python-JavaScript ' + compiler_version + '\n'
              'https://github.com/outside-labs/Python-JavaScript\n'
              'Original compiler helper implementation; no third-party runtime is embedded.\n'
              'This provenance notice grants no additional license rights.\n')
    output.append(OutputFile('NOTICES.txt', notice.encode('utf-8'), 'notice'))
    files = tuple(sorted(output, key=lambda item: item.path))
    manifest = {'kind': 'python-javascript-compiled', 'schema_version': 1,
                'compiler': {'name': 'Python-JavaScript', 'version': compiler_version, 'abi': 'python-browser-async-esm/1' if async_enabled else 'python-browser-esm/1'},
                'language_profile': module.profile, 'target': 'ecmascript-2022-module',
                'unicode_version': unicodedata.unidata_version, 'entrypoint': module_name,
                'entrypoint_export': 'createModule', 'application_exports': exports,
                'sources': [{'path': filename, 'sha256': module.source_sha256, 'size': len(source.encode('utf-8'))}],
                'files': [{'path': item.path, 'size': len(item.data), 'sha256': hashlib.sha256(item.data).hexdigest(), 'role': item.role} for item in files],
                'imports': [], 'helpers': list(helpers), 'notices': ['NOTICES.txt']}
    return CompiledArtifact(files, (_json(manifest) + '\n').encode('utf-8'))
