"""Original, dependency-selected ECMAScript helpers for python-browser/1."""

from functools import lru_cache
import json


HELPERS = {
    'error': ((), r'''
class $PyError extends Error {
  constructor(name, message, location) { super(message); this.name = name; this.location = location; }
}
function $fail(name, message, location) { throw new $PyError(name, message, location); }
'''),
    'binding': (('error',), r'''
const $UNBOUND = Symbol('unbound');
function $get(value, name, local, location) {
  if (value === $UNBOUND) $fail(local ? 'UnboundLocalError' : 'NameError',
    local ? `cannot access local variable '${name}' where it is not associated with a value` : `name '${name}' is not defined`, location);
  return value;
}
'''),
    'str': ((), r'''
class $Str {
  constructor(codepoints) { this.type = 'str'; this.codepoints = Object.freeze(codepoints); Object.freeze(this); }
}
function $str(points) { return new $Str(points); }
function $text(value) { return value.codepoints.map(point => String.fromCodePoint(point)).join(''); }
'''),
    'tuple': ((), r'''
class $Tuple {
  constructor(items) { this.type = 'tuple'; this.items = Object.freeze(items); Object.freeze(this); }
}
const $EMPTY = new $Tuple([]);
function $tuple(items) { return items.length ? new $Tuple(items) : $EMPTY; }
'''),
    'numeric': (('error',), r'''
function $number(value, location) {
  if (typeof value === 'bigint') return value;
  if (typeof value === 'boolean') return value ? 1n : 0n;
  $fail('TypeError', 'Operation requires an adopted Python integer.', location);
}
'''),
    'truth': (('error', 'str', 'tuple'), r'''
function $truth(value, location) {
  if (value === null || typeof value === 'boolean' || typeof value === 'bigint') return Boolean(value);
  if (value instanceof $Str) return value.codepoints.length !== 0;
  if (value instanceof $Tuple) return value.items.length !== 0;
  $fail('TypeError', 'Truth testing this value is outside python-browser/1.', location);
}
'''),
    'binary': (('numeric', 'str'), r'''
function $binary(operator, left, right, location) {
  if (operator === '+' && left instanceof $Str && right instanceof $Str) return $str([...left.codepoints, ...right.codepoints]);
  left = $number(left, location); right = $number(right, location);
  if (operator === '+') return left + right;
  if (operator === '-') return left - right;
  if (operator === '*') return left * right;
  if (right === 0n) $fail('ZeroDivisionError', operator === '//' ? 'division by zero' : 'integer modulo by zero', location);
  let quotient = left / right;
  if (left % right !== 0n && (left < 0n) !== (right < 0n)) quotient -= 1n;
  return operator === '//' ? quotient : left - quotient * right;
}
'''),
    'unary': (('numeric', 'truth'), r'''
function $unary(operator, value, location) {
  if (operator === 'not') return !$truth(value, location);
  value = $number(value, location); return operator === '-' ? -value : value;
}
'''),
    'equal': (('numeric', 'str', 'tuple'), r'''
function $equal(left, right, location) {
  if (left === right) return true;
  if (['bigint', 'boolean'].includes(typeof left) && ['bigint', 'boolean'].includes(typeof right)) return $number(left, location) === $number(right, location);
  if (left instanceof $Str && right instanceof $Str) return left.codepoints.length === right.codepoints.length && left.codepoints.every((point, index) => point === right.codepoints[index]);
  if (left instanceof $Tuple && right instanceof $Tuple) return left.items.length === right.items.length && left.items.every((value, index) => $equal(value, right.items[index], location));
  return false;
}
function $order(left, right, location) {
  if (['bigint', 'boolean'].includes(typeof left) && ['bigint', 'boolean'].includes(typeof right)) {
    left = $number(left, location); right = $number(right, location); return left < right ? -1 : left > right ? 1 : 0;
  }
  const strings = left instanceof $Str && right instanceof $Str;
  const tuples = left instanceof $Tuple && right instanceof $Tuple;
  if (!strings && !tuples) $fail('TypeError', 'Ordering requires matching adopted sequence or numeric values.', location);
  const a = strings ? left.codepoints : left.items, b = strings ? right.codepoints : right.items;
  for (let index = 0; index < Math.min(a.length, b.length); index++) {
    if (strings ? a[index] !== b[index] : !$equal(a[index], b[index], location)) return strings ? (a[index] < b[index] ? -1 : 1) : $order(a[index], b[index], location);
  }
  return a.length < b.length ? -1 : a.length > b.length ? 1 : 0;
}
'''),
    'compare': (('equal',), r'''
function $compare(operator, left, right, location) {
  if (operator === '==' || operator === '!=') return $equal(left, right, location) === (operator === '==');
  if (operator === 'is' || operator === 'is not') {
    if (left !== null && right !== null && typeof left !== 'boolean' && typeof right !== 'boolean' &&
        (typeof left === 'bigint' || typeof right === 'bigint' || left instanceof $Str || right instanceof $Str || typeof left === 'number' || typeof right === 'number')) {
      $fail('TypeError', 'Integer/string interning identity is outside python-browser/1.', location);
    }
    return (left === right) === (operator === 'is');
  }
  if (operator === 'in' || operator === 'not in') {
    let found = false;
    if (right instanceof $Tuple) found = right.items.some(value => $equal(left, value, location));
    else if (right instanceof $Str && left instanceof $Str) {
      outer: for (let start = 0; start <= right.codepoints.length - left.codepoints.length; start++) {
        for (let offset = 0; offset < left.codepoints.length; offset++) if (left.codepoints[offset] !== right.codepoints[start + offset]) continue outer;
        found = true; break;
      }
    } else $fail('TypeError', 'Membership requires adopted string/tuple values.', location);
    return found === (operator === 'in');
  }
  const order = $order(left, right, location);
  return operator === '<' ? order < 0 : operator === '<=' ? order <= 0 : operator === '>' ? order > 0 : order >= 0;
}
'''),
    'index': (('numeric', 'str', 'tuple'), r'''
function $index(value, index, location) {
  const string = value instanceof $Str;
  if (!string && !(value instanceof $Tuple)) $fail('TypeError', 'Indexing requires a Python str or tuple.', location);
  const items = string ? value.codepoints : value.items;
  index = $number(index, location); if (index < 0n) index += BigInt(items.length);
  if (index < 0n || index >= BigInt(items.length)) $fail('IndexError', string ? 'string index out of range' : 'tuple index out of range', location);
  return string ? $str([items[Number(index)]]) : items[Number(index)];
}
'''),
    'iterate': (('error', 'str', 'tuple'), r'''
function $iterate(value, location) {
  if (value instanceof $Str) return value.codepoints.map(point => $str([point]));
  if (value instanceof $Tuple) return value.items;
  $fail('TypeError', 'Iteration requires a Python str or tuple.', location);
}
'''),
    'call': (('error',), r'''
class $Callable {
  constructor(name, count, defaults, body) { Object.assign(this, {name, count, defaults, body}); Object.freeze(this); }
}
let $depth = 0;
function $fn(name, count, defaults, body) { return new $Callable(name, count, defaults, body); }
function $call(fn, args, location) {
  if (!(fn instanceof $Callable)) $fail('TypeError', 'Value is not an adopted callable.', location);
  if (fn.count !== null) {
    if (args.length < fn.count - fn.defaults.length || args.length > fn.count) $fail('TypeError', `${fn.name}() received an unsupported argument count`, location);
    for (let index = args.length; index < fn.count; index++) args.push(fn.defaults[index - (fn.count - fn.defaults.length)]);
  }
  if ($depth >= 128) $fail('RecursionError', 'Maximum compiled call depth (128) exceeded.', location);
  $depth++;
  try { return fn.body(args, location); } finally { $depth--; }
}
'''),
    'len': (('call', 'str', 'tuple'), r'''
const $len = $fn('len', 1, [], (args, location) => {
  const value = args[0];
  if (value instanceof $Str) return BigInt(value.codepoints.length);
  if (value instanceof $Tuple) return BigInt(value.items.length);
  $fail('TypeError', 'len() requires an adopted Python str or tuple.', location);
});
'''),
    'types': (('call', 'str', 'tuple'), r'''
const $types = Object.freeze({str: Symbol('str'), int: Symbol('int'), bool: Symbol('bool'), tuple: Symbol('tuple')});
const $isinstance = $fn('isinstance', 2, [], (args, location) => {
  const [value, type] = args;
  if (type === $types.str) return value instanceof $Str;
  if (type === $types.tuple) return value instanceof $Tuple;
  if (type === $types.int) return typeof value === 'bigint' || typeof value === 'boolean';
  if (type === $types.bool) return typeof value === 'boolean';
  $fail('TypeError', 'isinstance() requires an adopted builtin type.', location);
});
'''),
    'exception': (('call', 'str'), r'''
const $TypeError = $fn('TypeError', 1, [], (args, location) => {
  if (!(args[0] instanceof $Str)) $fail('TypeError', 'TypeError() requires a str message in this profile.', location);
  return new $PyError('TypeError', $text(args[0]), location);
});
'''),
    'repr': (('error', 'str', 'tuple'), r'''
const $nonprintable = __NONPRINTABLE__;
function $printable(point) {
  let low = 0, high = $nonprintable.length;
  while (low < high) { const mid = (low + high) >> 1; if ($nonprintable[mid][1] < point) low = mid + 1; else high = mid; }
  return low === $nonprintable.length || point < $nonprintable[low][0];
}
function $repr(value, location, quoteString = false) {
  if (value === null) return 'None';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'bigint' || typeof value === 'number') return value.toString();
  if (value instanceof $Str) {
    if (!quoteString) {
      if (value.codepoints.some(point => point >= 0xd800 && point <= 0xdfff)) $fail('TypeError', 'Surrogate text output requires a separately adopted sink.', location);
      return $text(value);
    }
    const quote = !value.codepoints.includes(39) || value.codepoints.includes(34) ? "'" : '"';
    return quote + value.codepoints.map(point => {
      if (point === 92 || point === quote.codePointAt(0)) return '\\' + String.fromCodePoint(point);
      if (point === 9) return '\\t'; if (point === 10) return '\\n'; if (point === 13) return '\\r';
      if (!$printable(point)) return (point < 256 ? '\\x' : point < 65536 ? '\\u' : '\\U') + point.toString(16).padStart(point < 256 ? 2 : point < 65536 ? 4 : 8, '0');
      return String.fromCodePoint(point);
    }).join('') + quote;
  }
  if (value instanceof $Tuple) return '(' + value.items.map(item => $repr(item, location, true)).join(', ') + (value.items.length === 1 ? ',' : '') + ')';
  if (value instanceof $PyError) return value.message;
  $fail('TypeError', 'Printing this value is outside python-browser/1.', location);
}
'''),
    'print': (('call', 'repr'), r'''
const $print = $fn('print', null, [], (args, location) => { write(args.map(value => $repr(value, location)).join(' ') + '\n'); return null; });
'''),
    'javascript': (('call',), r'''
class $JSArray { constructor(values) { this.values = values; } }
const $of = $fn('Array.of', null, [], args => new $JSArray(args));
const $JArray = Object.freeze({of: $of});
const $JS = Object.freeze({Array: $JArray});
function $attribute(value, name, location) {
  if (value === $JS && name === 'Array') return $JArray;
  if (value === $JArray && name === 'of') return $of;
  if (value instanceof $JSArray && name === 'length') return value.values.length;
  $fail('TypeError', 'Attribute is outside the approved JavaScript registry.', location);
}
'''),
    'input': (('call', 'str', 'tuple'), r'''
function $input(value, location, depth = 0, seen = new Set()) {
  if (depth > 64) $fail('TypeError', 'Input nesting exceeds 64.', location);
  if (value === null || ['boolean', 'bigint'].includes(typeof value) || value instanceof $Str || value instanceof $Tuple) return value;
  if (typeof value === 'string') return $str(Array.from(value, character => character.codePointAt(0)));
  if (typeof value !== 'object' || seen.has(value)) $fail('TypeError', 'Input requires an adopted Python value.', location);
  if (value.type === 'str' && Array.isArray(value.codepoints) && value.codepoints.length <= 1048576 && Array.from(value.codepoints).every(point => Number.isInteger(point) && point >= 0 && point <= 0x10ffff)) return $str([...value.codepoints]);
  if (value.type === 'tuple' && Array.isArray(value.items)) {
    seen.add(value); const items = Array.from(value.items, item => $input(item, location, depth + 1, seen)); seen.delete(value); return $tuple(items);
  }
  $fail('TypeError', 'Use BigInt, string, bool, null or explicit str/tuple input; JavaScript Number/Array is not Python int/tuple.', location);
}
function $expose(value, location) {
  return value instanceof $Callable ? (...args) => $call(value, args.map(argument => $input(argument, location)), location) : value;
}
'''),
}


@lru_cache(maxsize=1)
def _nonprintable_ranges():
    ranges, start = [], None
    for point in range(0x110000):
        if not chr(point).isprintable():
            if start is None:
                start = point
        elif start is not None:
            ranges.append([start, point - 1])
            start = None
    if start is not None:
        ranges.append([start, 0x10ffff])
    return json.dumps(ranges, separators=(',', ':'))


def helper_closure(required):
    ordered = []
    def visit(name):
        if name in ordered:
            return
        for dependency in HELPERS[name][0]:
            visit(dependency)
        ordered.append(name)
    for name in sorted(required):
        visit(name)
    return tuple(ordered)


def helper_source(name):
    source = HELPERS[name][1].strip()
    if name == 'repr':
        source = source.replace('__NONPRINTABLE__', _nonprintable_ranges())
    return source
