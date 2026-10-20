"""Binding-aware front end for the experimental python-browser/1 profile."""

import ast
from dataclasses import dataclass
import hashlib
import symtable
from typing import Literal


ValueType = Literal['statement', 'python-value', 'python-none', 'python-bool',
                    'python-int', 'python-str', 'python-tuple', 'python-exception',
                    'python-type', 'callable', 'javascript-type', 'javascript-array',
                    'javascript-number', 'javascript-callable', 'async-callable',
                    'python-coroutine', 'python-promise']


@dataclass(frozen=True)
class SourceSpan:
    filename: str
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    span: SourceSpan
    phase: Literal['parse', 'bind', 'validate'] = 'validate'


class CompileError(ValueError):
    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic
        span = diagnostic.span
        super().__init__(f'{span.filename}:{span.line}:{span.column}: {diagnostic.code}: {diagnostic.message}')


@dataclass(frozen=True)
class Binding:
    id: str
    name: str
    scope: str
    kind: Literal['constant', 'function', 'parameter', 'local', 'javascript', 'builtin', 'source']
    target: str | None = None


@dataclass(frozen=True)
class IRNode:
    kind: str
    value_type: ValueType
    span: SourceSpan
    fields: tuple[tuple[str, object], ...] = ()

    def field(self, name, default=None):
        return dict(self.fields).get(name, default)

    def to_dict(self):
        def encode(value):
            if isinstance(value, IRNode):
                return value.to_dict()
            if isinstance(value, tuple):
                return [encode(item) for item in value]
            return value
        return {'kind': self.kind, 'value_type': self.value_type,
                'span': dict(vars(self.span)),
                'fields': {key: encode(value) for key, value in self.fields}}


@dataclass(frozen=True)
class ModuleIR:
    filename: str
    source_sha256: str
    bindings: tuple[Binding, ...]
    body: tuple[IRNode, ...]
    profile: str = 'python-browser/1'
    schema_version: int = 1

    def to_dict(self):
        return {'profile': self.profile, 'schema_version': self.schema_version,
                'filename': self.filename, 'source_sha256': self.source_sha256,
                'bindings': [dict(vars(binding)) for binding in self.bindings],
                'body': [node.to_dict() for node in self.body]}


@dataclass(frozen=True)
class SourceImport:
    name: str
    module: str
    export: str
    value_type: ValueType


_BROWSER_APIS = {'read_text': 1, 'write_text': 2, 'on_click': 2, 'unsubscribe': 1, 'fetch_text': 1}


_BUILTINS = {'len', 'print', 'isinstance', 'str', 'int', 'bool', 'tuple', 'TypeError'}
_TYPES = {'str', 'int', 'bool', 'tuple'}
_BINARY = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.FloorDiv: '//', ast.Mod: '%'}
_COMPARE = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>',
            ast.GtE: '>=', ast.Is: 'is', ast.IsNot: 'is not', ast.In: 'in', ast.NotIn: 'not in'}


def _literal_type(value):
    if value is None:
        return 'python-none'
    return {bool: 'python-bool', int: 'python-int', str: 'python-str', tuple: 'python-tuple'}.get(type(value))


def _immutable(node):
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return False
    def accepted(value):
        return _literal_type(value) is not None and (not isinstance(value, tuple) or all(accepted(item) for item in value))
    return accepted(value)


class _FrontEnd:
    def __init__(self, source, filename, source_imports=None, *, async_enabled=False, browser_enabled=False):
        self.filename = filename
        self.lines = source.splitlines() or ['']
        self.bindings = {}
        self.root = {}
        self.locals = {}
        self.types = {}
        self.source_imports = source_imports or {}
        self.async_enabled = async_enabled
        self.browser_enabled = browser_enabled
        self.async_scopes = set()
        try:
            self.tree = ast.parse(source, filename=filename)
            self.table = symtable.symtable(source, filename, 'exec')
        except SyntaxError as error:
            span = SourceSpan(filename, error.lineno or 1, error.offset or 1,
                              error.end_lineno or error.lineno or 1,
                              error.end_offset or error.offset or 1)
            raise CompileError(Diagnostic('PJS100', error.msg, span, 'parse')) from None
        self._declare_module()

    def span(self, node):
        def column(line, offset):
            text = self.lines[line - 1] if 0 < line <= len(self.lines) else ''
            return len(text.encode('utf-8')[:offset].decode('utf-8')) + 1
        line, end_line = node.lineno, node.end_lineno or node.lineno
        return SourceSpan(self.filename, line, column(line, node.col_offset),
                          end_line, column(end_line, node.end_col_offset or node.col_offset))

    def fail(self, code, message, node):
        raise CompileError(Diagnostic(code, message, self.span(node), 'bind' if code == 'PJS110' else 'validate'))

    def node(self, original, kind, value_type='statement', **fields):
        return IRNode(kind, value_type, self.span(original), tuple(fields.items()))

    def declare(self, name, scope, kind, target=None):
        binding = Binding(scope + ':' + name, name, scope, kind, target)
        self.bindings[binding.id] = binding
        return binding

    def _declare_module(self):
        for node in self.tree.body:
            imports = self.source_imports.get((node.lineno, node.col_offset))
            if imports is not None:
                for imported in imports:
                    if imported.name in self.root:
                        self.fail('PJS100', 'Module rebinding is outside the immutable profile.', node)
                    binding = self.declare(imported.name, 'module', 'source', imported.module + ':' + imported.export)
                    self.root[imported.name] = binding
                    self.types[binding.id] = imported.value_type
                continue
            if isinstance(node, ast.ImportFrom) and node.module == 'JavaScript.browser' and self.browser_enabled:
                if node.level or any(alias.name not in _BROWSER_APIS for alias in node.names):
                    self.fail('PJS110', 'Unsupported browser host import.', node)
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name in self.root:
                        self.fail('PJS100', 'Module rebinding is outside the immutable profile.', node)
                    self.root[name] = self.declare(name, 'module', 'javascript', 'JavaScript.browser.' + alias.name)
                continue
            names = []
            kind, target = 'constant', None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names, kind = [node.name], 'function'
                if isinstance(node, ast.AsyncFunctionDef):
                    self.types['module:' + node.name] = 'async-callable'
                    self.async_scopes.add('function:' + node.name)
            elif isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name) or not _immutable(node.value):
                    self.fail('PJS100', 'Module bindings require single-name immutable literals.', node)
                names = [node.targets[0].id]
                self.types['module:' + names[0]] = _literal_type(ast.literal_eval(node.value))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                kind = 'javascript'
                if isinstance(node, ast.Import):
                    if len(node.names) != 1 or node.names[0].name != 'JavaScript':
                        self.fail('PJS110', 'Only the approved JavaScript registry may be imported.', node)
                    names, target = [node.names[0].asname or 'JavaScript'], 'JavaScript'
                else:
                    if node.level or node.module != 'JavaScript' or len(node.names) != 1 or node.names[0].name not in ({'Array', 'Promise'} if self.async_enabled else {'Array'}):
                        self.fail('PJS110', 'Only the approved JavaScript.Array binding may be imported.', node)
                    names, target = [node.names[0].asname or node.names[0].name], 'JavaScript.' + node.names[0].name
            for name in names:
                if name in self.root:
                    self.fail('PJS100', 'Module rebinding is outside the immutable profile.', node)
                self.root[name] = self.declare(name, 'module', kind, target)
        for child in self.table.get_children():
            if child.get_name() in self.root and self.root[child.get_name()].kind == 'function':
                scope = 'function:' + child.get_name()
                self.locals[scope] = {
                    symbol.get_name(): self.declare(symbol.get_name(), scope,
                        'parameter' if symbol.is_parameter() else 'local')
                    for symbol in sorted(child.get_symbols(), key=lambda symbol: symbol.get_name())
                    if symbol.is_local()
                }

    def resolve(self, name, scope, node):
        if scope and name in self.locals[scope]:
            return self.locals[scope][name]
        if name in self.root:
            return self.root[name]
        if name in _BUILTINS:
            identifier = 'builtin:' + name
            if identifier not in self.bindings:
                self.declare(name, 'builtin', 'builtin', identifier)
            return self.bindings[identifier]
        self.fail('PJS110', 'Unresolved or unsupported binding: ' + name, node)

    def expression(self, node, scope):
        if isinstance(node, ast.Constant):
            kind = _literal_type(node.value)
            if kind is None:
                self.fail('PJS100', 'Literal type is deferred in this profile.', node)
            value = str(node.value) if type(node.value) is int else node.value
            return self.node(node, 'constant', kind, value=value)
        if isinstance(node, ast.Name):
            binding = self.resolve(node.id, scope, node)
            kind = self.types.get(binding.id, 'python-value')
            target = binding.target
            if binding.kind == 'function':
                kind, target = self.types.get(binding.id, 'callable'), binding.id
            elif binding.kind == 'javascript':
                kind = 'javascript-callable' if (target or '').startswith('JavaScript.browser.') else 'javascript-type'
            elif binding.kind == 'builtin':
                kind = 'python-type' if binding.name in _TYPES else 'callable'
            elif binding.kind == 'source':
                target = binding.id if kind in {'callable', 'async-callable'} else None
            return self.node(node, 'name', kind, binding=binding.id, target=target)
        if isinstance(node, ast.Await):
            if not self.async_enabled or scope not in self.async_scopes:
                self.fail('PJS100', 'Await requires an adopted async function.', node)
            value = self.expression(node.value, scope)
            if value.value_type not in {'python-coroutine', 'python-promise', 'python-value'}:
                self.fail('PJS120', 'Await requires an adopted coroutine or Promise.', node)
            return self.node(node, 'await', 'python-value', value=value)
        if isinstance(node, ast.Tuple):
            return self.node(node, 'tuple', 'python-tuple', values=tuple(self.expression(value, scope) for value in node.elts))
        if isinstance(node, ast.Attribute):
            value = self.expression(node.value, scope)
            if self.async_enabled:
                async_target = {('JavaScript', 'Promise'): 'JavaScript.Promise',
                                ('JavaScript.Promise', 'resolve'): 'JavaScript.Promise.resolve',
                                ('JavaScript.Promise', 'reject'): 'JavaScript.Promise.reject'}.get((value.field('target'), node.attr))
                if value.value_type == 'python-promise' and node.attr == 'then':
                    async_target = 'Promise.then'
                if async_target:
                    return self.node(node, 'async-attribute', 'javascript-type' if async_target == 'JavaScript.Promise' else 'javascript-callable',
                                     value=value, name=node.attr, target=async_target)
            target = {( 'JavaScript', 'Array'): 'JavaScript.Array',
                      ('JavaScript.Array', 'of'): 'JavaScript.Array.of'}.get((value.field('target'), node.attr))
            if target:
                return self.node(node, 'attribute', 'javascript-callable' if target.endswith('.of') else 'javascript-type',
                                 value=value, name=node.attr, target=target)
            if value.value_type == 'javascript-array' and node.attr == 'length':
                return self.node(node, 'attribute', 'javascript-number', value=value, name='length')
            self.fail('PJS110' if (value.field('target') or '').startswith('JavaScript') else 'PJS120',
                      'Attribute is outside the approved JavaScript API.', node)
        if isinstance(node, ast.Call):
            if node.keywords or any(isinstance(argument, ast.Starred) for argument in node.args):
                self.fail('PJS100', 'Keyword and starred calls are deferred.', node)
            function = self.expression(node.func, scope)
            target = function.field('target')
            allowed = {'builtin:len': ('python-int', 1), 'builtin:print': ('python-none', None),
                       'builtin:isinstance': ('python-bool', 2), 'builtin:TypeError': ('python-exception', 1),
                       'JavaScript.Array.of': ('javascript-array', None)}
            if self.browser_enabled:
                allowed.update({'JavaScript.browser.' + name: ('python-promise', count) for name, count in _BROWSER_APIS.items()})
            if self.async_enabled:
                allowed.update({'JavaScript.Promise.resolve': ('python-promise', 1),
                                'JavaScript.Promise.reject': ('python-promise', 1),
                                'Promise.then': ('python-promise', None)})
            if target in allowed:
                kind, count = allowed[target]
                if count is not None and len(node.args) != count:
                    self.fail('PJS120', 'Unsupported argument count.', node)
            elif target in self.bindings and self.bindings[target].kind in {'function', 'source'}:
                kind = 'python-coroutine' if function.value_type == 'async-callable' else 'python-value'
            else:
                self.fail('PJS120', 'Call does not resolve to an approved direct callable.', node)
            arguments = tuple(self.expression(argument, scope) for argument in node.args)
            if any(argument.value_type == 'python-coroutine' for argument in arguments):
                self.fail('PJS120', 'Coroutine arguments must be awaited first.', node)
            if target == 'JavaScript.browser.on_click' and arguments[1].value_type not in {'callable', 'async-callable'}:
                self.fail('PJS120', 'on_click requires a known compiled Python callback.', node)
            if target == 'Promise.then' and (len(arguments) > 2 or any(
                    argument.value_type not in {'callable', 'python-none'} for argument in arguments)):
                self.fail('PJS120', 'then accepts up to two plain synchronous Python callbacks or None.', node)
            if target == 'builtin:isinstance' and arguments[1].field('target') not in {'builtin:' + name for name in _TYPES}:
                self.fail('PJS120', 'isinstance requires an approved builtin type binding.', node)
            return self.node(node, 'call', kind, function=function, arguments=arguments, target=target)
        if isinstance(node, ast.BinOp):
            operator = _BINARY.get(type(node.op))
            if operator is None:
                self.fail('PJS100', 'Binary operator is deferred.', node)
            left, right = self.expression(node.left, scope), self.expression(node.right, scope)
            kinds = {left.value_type, right.value_type}
            if kinds <= {'python-int', 'python-bool'}:
                kind = 'python-int'
            elif operator == '+' and kinds == {'python-str'}:
                kind = 'python-str'
            elif 'python-value' in kinds and kinds <= {'python-value', 'python-int', 'python-bool', 'python-str'}:
                kind = 'python-value'
            else:
                self.fail('PJS120', 'Operand types require a separately adopted operation.', node)
            return self.node(node, 'binary', kind, operator=operator, left=left, right=right)
        if isinstance(node, ast.UnaryOp):
            operator = {ast.Not: 'not', ast.UAdd: '+', ast.USub: '-'}.get(type(node.op))
            if operator is None:
                self.fail('PJS100', 'Unary operator is deferred.', node)
            value = self.expression(node.operand, scope)
            if operator != 'not' and value.value_type not in {'python-int', 'python-bool', 'python-value'}:
                self.fail('PJS120', 'Unary numeric operation requires a Python integer.', node)
            return self.node(node, 'unary', 'python-bool' if operator == 'not' else 'python-int', operator=operator, value=value)
        if isinstance(node, ast.BoolOp):
            values = tuple(self.expression(value, scope) for value in node.values)
            kinds = {value.value_type for value in values}
            return self.node(node, 'boolean', next(iter(kinds)) if len(kinds) == 1 else 'python-value',
                             operator='and' if isinstance(node.op, ast.And) else 'or', values=values)
        if isinstance(node, ast.Compare):
            operators = tuple(_COMPARE.get(type(operator)) for operator in node.ops)
            if None in operators:
                self.fail('PJS100', 'Comparison is deferred.', node)
            values = tuple(self.expression(value, scope) for value in [node.left, *node.comparators])
            for index, operator in enumerate(operators):
                if operator in {'is', 'is not'}:
                    for value in values[index:index + 2]:
                        if value.value_type in {'python-int', 'python-str', 'javascript-number'} or (
                            value.kind == 'tuple'
                        ):
                            self.fail('PJS120', 'Literal interning identity is outside this profile.', node)
            return self.node(node, 'compare', 'python-bool', operators=operators, values=values)
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                self.fail('PJS100', 'Slicing is deferred.', node)
            value, index = self.expression(node.value, scope), self.expression(node.slice, scope)
            if value.value_type not in {'python-str', 'python-tuple', 'python-value'} or index.value_type not in {'python-int', 'python-bool', 'python-value'}:
                self.fail('PJS120', 'Indexing requires an adopted sequence and integer.', node)
            return self.node(node, 'index', 'python-str' if value.value_type == 'python-str' else 'python-value', value=value, index=index)
        self.fail('PJS100', 'Unsupported expression: ' + type(node).__name__, node)

    def statements(self, nodes, scope=None, loop=0):
        return tuple(self.statement(node, scope, loop) for node in nodes)

    def statement(self, node, scope, loop):
        if self.browser_enabled and scope is None and not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign, ast.Pass)):
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                self.fail('PJS100', 'Browser module initialization requires imports, definitions or immutable constants.', node)
        if isinstance(node, (ast.Import, ast.ImportFrom)) and scope is None:
            if node not in self.tree.body:
                self.fail('PJS100', 'Imports require unconditional module bindings.', node)
            imports = self.source_imports.get((node.lineno, node.col_offset))
            if imports is not None:
                return self.node(node, 'source-import', module=imports[0].module,
                                 bindings=tuple((self.root[imported.name].id, imported.export) for imported in imports))
            names = [alias.asname or alias.name for alias in node.names]
            return self.node(node, 'import', bindings=tuple(self.root[name].id for name in names))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            asynchronous = isinstance(node, ast.AsyncFunctionDef)
            if asynchronous and not self.async_enabled:
                self.fail('PJS100', 'Async functions require the explicit async profile.', node)
            if node not in self.tree.body or scope or node.decorator_list or node.type_params or node.returns or any(arg.annotation for arg in [*node.args.posonlyargs, *node.args.args]):
                self.fail('PJS100', 'Nested, decorated, generic or annotated functions are deferred.', node)
            if node.args.vararg or node.args.kwarg or node.args.kwonlyargs:
                self.fail('PJS100', 'Variadic and keyword-only parameters are deferred.', node)
            if not all(_immutable(default) for default in node.args.defaults):
                self.fail('PJS100', 'Defaults must be immutable literals.', node)
            function_scope = 'function:' + node.name
            defaults = tuple(self.expression(default, None) for default in node.args.defaults)
            original = self.types.copy()
            body = self.statements(node.body, function_scope)
            self.types = original
            return self.node(node, 'function', binding=self.root[node.name].id,
                             parameters=tuple(self.locals[function_scope][arg.arg].id for arg in [*node.args.posonlyargs, *node.args.args]),
                             defaults=defaults, body=body, asynchronous=asynchronous)
        if isinstance(node, ast.Assign):
            if any(not isinstance(target, ast.Name) for target in node.targets):
                self.fail('PJS100', 'Only simple-name assignment is supported.', node)
            if scope is None and (node not in self.tree.body or not _immutable(node.value)):
                self.fail('PJS100', 'Module bindings must be unconditional immutable literals.', node)
            value = self.expression(node.value, scope)
            targets = tuple(self.resolve(target.id, scope, target).id for target in node.targets)
            for target in targets:
                self.types[target] = value.value_type
            return self.node(node, 'assign', targets=targets, value=value)
        if isinstance(node, ast.Expr):
            return self.node(node, 'expression', value=self.expression(node.value, scope))
        if isinstance(node, ast.Return):
            if scope is None:
                self.fail('PJS100', 'Return requires a function.', node)
            value = self.expression(node.value, scope) if node.value else None
            if value and (value.value_type == 'python-coroutine' or
                          (scope in self.async_scopes and value.value_type == 'python-promise')):
                self.fail('PJS120', 'Returning an unawaited coroutine or Promise is outside this profile.', node)
            return self.node(node, 'return', value=value)
        if isinstance(node, ast.If):
            test = self.expression(node.test, scope)
            original = self.types.copy()
            body = self.statements(node.body, scope, loop)
            left = self.types.copy()
            self.types = original.copy()
            otherwise = self.statements(node.orelse, scope, loop)
            right = self.types
            self.types = {key: left.get(key) if left.get(key) == right.get(key) else 'python-value'
                          for key in left.keys() | right.keys()}
            return self.node(node, 'if', test=test, body=body, otherwise=otherwise)
        if isinstance(node, ast.For):
            if scope is None or node.orelse or not isinstance(node.target, ast.Name):
                self.fail('PJS100', 'For requires a function, simple target and no else clause.', node)
            value = self.expression(node.iter, scope)
            if value.value_type not in {'python-str', 'python-tuple', 'python-value'}:
                self.fail('PJS120', 'For requires an adopted iterable.', node)
            target = self.resolve(node.target.id, scope, node.target).id
            original = self.types.copy()
            self.types[target] = 'python-str' if value.value_type == 'python-str' else 'python-value'
            body = self.statements(node.body, scope, loop + 1)
            self.types = {key: kind if kind == original.get(key) else 'python-value' for key, kind in (original | self.types).items()}
            return self.node(node, 'for', target=target, value=value, body=body)
        if isinstance(node, (ast.Break, ast.Continue)):
            if not loop:
                self.fail('PJS100', 'Loop control requires a loop.', node)
            return self.node(node, 'break' if isinstance(node, ast.Break) else 'continue')
        if isinstance(node, ast.Raise):
            value = self.expression(node.exc, scope) if node.exc else None
            if node.cause or value is None or value.value_type != 'python-exception':
                self.fail('PJS120', 'Only explicit adopted builtin errors may be raised.', node)
            return self.node(node, 'raise', value=value)
        if isinstance(node, ast.Pass):
            return self.node(node, 'pass')
        self.fail('PJS100', 'Unsupported statement: ' + type(node).__name__, node)


def parse_source(source: str, *, filename: str = '<source>', async_enabled: bool = False) -> ModuleIR:
    """Validate source and return immutable typed IR without executing target code."""
    if not isinstance(source, str) or not isinstance(filename, str):
        raise TypeError('source and filename must be strings')
    try:
        encoded = source.encode('utf-8')
    except UnicodeEncodeError:
        raise CompileError(Diagnostic('PJS100', 'Source must be valid UTF-8.', SourceSpan(filename, 1, 1, 1, 1), 'parse')) from None
    if len(encoded) > 1_048_576:
        raise CompileError(Diagnostic('PJS100', 'Source exceeds the 1 MiB profile limit.', SourceSpan(filename, 1, 1, 1, 1), 'parse'))
    if type(async_enabled) is not bool:
        raise TypeError('async_enabled must be bool')
    frontend = _FrontEnd(source, filename, async_enabled=async_enabled)
    body = frontend.statements(frontend.tree.body)
    return ModuleIR(filename, hashlib.sha256(encoded).hexdigest(),
                    tuple(frontend.bindings[key] for key in sorted(frontend.bindings)), body,
                    profile='python-browser-async/1' if async_enabled else 'python-browser/1')
