import json
from pathlib import Path
import tempfile
import unittest

from JavaScript.compiler import CompileError, parse_source


CORPUS = Path(__file__).parent / 'fixtures' / 'compiler_contract.json'


class CompilerFrontEndTests(unittest.TestCase):
    def test_adopted_corpus_is_accepted_or_diagnosed(self):
        corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
        for case in corpus['cases']:
            with self.subTest(case=case['id']):
                self.assertEqual(parse_source(case['source']).profile, 'python-browser/1')
        for case in corpus['boundaries']:
            with self.subTest(boundary=case['id']):
                with self.assertRaises(CompileError) as caught:
                    parse_source(case['source'], filename='boundary.py')
                self.assertEqual(caught.exception.diagnostic.code, case['diagnostic'])
                self.assertEqual(caught.exception.diagnostic.span.filename, 'boundary.py')

    def test_large_integers_determinism_and_serialization_are_lossless(self):
        source = 'print(9007199254740993)'
        module = parse_source(source, filename='example.py')
        encoded = json.dumps(module.to_dict(), sort_keys=True)
        self.assertEqual(encoded, json.dumps(parse_source(source, filename='example.py').to_dict(), sort_keys=True))
        constant = module.body[0].field('value').field('arguments')[0]
        self.assertEqual(constant.value_type, 'python-int')
        self.assertEqual(constant.field('value'), '9007199254740993')
        exported = module.to_dict()
        exported['body'][0]['span']['line'] = 99
        exported['bindings'][0]['name'] = 'changed'
        self.assertEqual(module.body[0].span.line, 1)
        self.assertNotEqual(module.bindings[0].name, 'changed')

    def test_aliases_resolve_by_binding_and_shadowing_is_not_intrinsic(self):
        for statement in ['import JavaScript as JS', 'from JavaScript import Array as A']:
            expression = 'JS.Array.of(1)' if statement.startswith('import ') else 'A.of(1)'
            module = parse_source(statement + '\ndef selected():\n    return ' + expression + '.length')
            encoded = json.dumps(module.to_dict())
            self.assertIn('JavaScript.Array.of', encoded)
            self.assertIn('javascript-array', encoded)
        for source in [
            'from JavaScript import Array as A\ndef selected(A):\n    return A.of(1)',
            'def selected(len):\n    return len(1)',
        ]:
            with self.assertRaises(CompileError) as caught:
                parse_source(source)
            self.assertEqual(caught.exception.diagnostic.code, 'PJS120')
        own = parse_source('def len(value):\n    return value + 1\nprint(len(2))')
        self.assertIn('module:len', {binding.id for binding in own.bindings})
        self.assertNotIn('builtin:len', {binding.id for binding in own.bindings})

    def test_scopes_recursion_and_branch_types_are_preserved(self):
        source = ('VALUE = 4\ndef first(value):\n    if value:\n        item = 1\n'
                  '    else:\n        item = "text"\n    return item + VALUE\n'
                  'def second(value):\n    return first(value)')
        module = parse_source(source)
        parameters = [binding for binding in module.bindings if binding.kind == 'parameter']
        self.assertEqual(len({binding.id for binding in parameters}), 2)
        self.assertEqual({binding.name for binding in parameters}, {'value'})
        parse_source('def factorial(n):\n    if n:\n        return n * factorial(n - 1)\n    return 1')

    def test_source_locations_count_characters_after_unicode(self):
        source = 'é = 1; eval("text")'
        with self.assertRaises(CompileError) as caught:
            parse_source(source, filename='unicode.py')
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, 'PJS110')
        self.assertEqual(diagnostic.phase, 'bind')
        self.assertEqual(diagnostic.span.column, source.index('eval') + 1)
        self.assertEqual(diagnostic.span.line, 1)
        self.assertIn('unicode.py:1:', str(caught.exception))

    def test_unsupported_operations_and_initialization_fail_without_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'must-not-exist'
            source = f'open({str(target)!r}, "w").write("executed")'
            with self.assertRaises(CompileError):
                parse_source(source)
            self.assertFalse(target.exists())
        for source in [
            'values = []', 'value = len("x")', 'def f(value=list()):\n    return value',
            'def f():\n    while True:\n        pass', 'def f():\n    return 1.5',
            'def f():\n    return "text" + 1', 'def f():\n    return missing',
            'def f():\n    return (1, 2)[:1]', 'def f():\n    import os',
            'print(1 is 1)', 'print((1, 2) is (1, 2))',
            'if False:\n    import os', 'if True:\n    def nested():\n        pass',
        ]:
            with self.subTest(source=source), self.assertRaises(CompileError):
                parse_source(source)
        with self.assertRaises(CompileError):
            parse_source('def invalid(')
        with self.assertRaises(CompileError):
            parse_source('\ud800')
        with self.assertRaises(CompileError):
            parse_source('#' * 1_048_577)
