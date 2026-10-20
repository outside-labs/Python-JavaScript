import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from JavaScript.compiler import CompileError
from JavaScript.emitter import compile_source


CORPUS = Path(__file__).parent / 'fixtures' / 'compiler_contract.json'


def run_node(artifact, invocation='createModule({write: text => stdout += text});'):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for file in artifact.files:
            (root / file.path).write_bytes(file.data)
        runner = ("import {createModule} from './app.mjs'; let stdout=''; let error=null;\n"
                  "try { " + invocation + " } catch (caught) { error={name:caught.name,message:caught.message,location:caught.location}; }\n"
                  "console.log(JSON.stringify({stdout,error}));")
        (root / 'run.mjs').write_text(runner, encoding='utf-8')
        process = subprocess.run(['node', str(root / 'run.mjs')], check=True,
                                 capture_output=True, text=True, encoding='utf-8', timeout=10)
        return json.loads(process.stdout)


class CompilerEmitterTests(unittest.TestCase):
    def assert_parity(self, source):
        oracle = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', source],
                                capture_output=True, text=True, encoding='utf-8', timeout=5)
        result = run_node(compile_source(source, filename='case.py'))
        self.assertEqual(result['stdout'], oracle.stdout.replace('\r\n', '\n'))
        if oracle.returncode:
            self.assertIsNotNone(result['error'])
            self.assertEqual(result['error']['name'], oracle.stderr.splitlines()[-1].split(':', 1)[0])
            self.assertEqual(result['error']['location']['filename'], 'case.py')
        else:
            self.assertIsNone(result['error'], result['error'])
        return result

    def test_corpus_executes_as_emitted_modules(self):
        corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
        for case in corpus['cases']:
            with self.subTest(case=case['id']):
                result = self.assert_parity(case['source'])
                self.assertEqual(result['stdout'], case['stdout'])
        for case in corpus['boundaries']:
            with self.subTest(boundary=case['id']), self.assertRaises(CompileError):
                compile_source(case['source'])

    def test_single_evaluation_short_circuit_order_and_loop_control(self):
        self.assert_parity('''def mark(value):
    print(value)
    return value
def selected():
    total = 0
    for value in (1, 2, 3, 4):
        if value == 2:
            continue
        if value == 4:
            break
        total = total + value
    return total
print(mark(1) < mark(2) < mark(3))
print(mark(3) < mark(2) < mark(1))
print(mark('') and mark('never'))
print(mark(()) or mark('fallback'))
print(selected())''')

    def test_scalar_tuple_unicode_and_registry_semantics(self):
        self.assert_parity('''import JavaScript as JS
def selected():
    original = (1,)
    alias = original
    return original is alias, () == (), not (), True + 2, '😀'[-1], '😀' in 'A😀', 2 in (1, 2)
print(JS.Array.of(1, 2).length)
print(selected())
print(('a\\nb', "a'b", '\\x08', '\\u00a0', '\\ud800'))
print(('\\U0001fae9', '\\u0301'))
print(len('\\ud83d\\ude00'), len('😀'), '\\ud83d\\ude00' == '😀')
print(-7 // 3, 7 // -3, -7 % 3, 7 % -3, (1, 2) < (1, 3))''')

    def test_defaults_preserve_definition_time_identity_and_recursion(self):
        self.assert_parity('''def same(value=(1, 2)):
    return value
def selected():
    first = same()
    second = same()
    return first is second
def factorial(value):
    if value:
        return value * factorial(value - 1)
    return 1
print(selected(), factorial(6))''')
        result = run_node(compile_source('def forever():\n    return forever()\nforever()'))
        self.assertEqual(result['error']['name'], 'RecursionError')

    def test_runtime_errors_keep_source_and_output_before_failure(self):
        sources = [
            'print("before")\n1 // 0', 'print("before")\n(1,)[5]',
            'def selected(value):\n    if value:\n        item = 1\n    return item\nselected(False)',
            'print(later())\ndef later():\n    return 1',
            'def selected(value):\n    return value + 1\nselected()',
            'def selected(value):\n    if not isinstance(value, str):\n        raise TypeError("text must be str")\n    return len(value)\nselected(1)',
            'A.of(1)\nfrom JavaScript import Array as A',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assert_parity(source)
        error = run_node(compile_source('def selected():\n    return 1 // 0\nselected()', filename='original.py'))['error']
        self.assertEqual(error['location']['filename'], 'original.py')
        self.assertEqual(error['location']['line'], 2)
        self.assertEqual(error['location']['column'], 12)

    def test_exports_enforce_inputs_and_independent_module_state(self):
        artifact = compile_source('def size(text):\n    return len(text)\ndef echo(value):\n    return value')
        result = run_node(artifact, "const app=createModule({write: text => stdout+=text}); stdout=app.size('A😀').toString();")
        self.assertEqual(result['stdout'], '2')
        result = run_node(artifact, "const app=createModule(); app.echo(9007199254740992);")
        self.assertEqual(result['error']['name'], 'TypeError')
        result = run_node(artifact, "const app=createModule(); const value={type:'tuple',items:[]}; value.items.push(value); app.echo(value);")
        self.assertEqual(result['error']['name'], 'TypeError')

    def test_manifest_determinism_closure_hashes_and_optional_maps(self):
        source = 'def selected(value):\n    return value + 1'
        artifact = compile_source(source)
        self.assertEqual(artifact, compile_source(source))
        manifest = artifact.manifest
        self.assertEqual(manifest['kind'], 'python-javascript-compiled')
        self.assertEqual(manifest['imports'], [])
        self.assertIn('binary', manifest['helpers'])
        self.assertNotIn('javascript', manifest['helpers'])
        self.assertNotIn('print', manifest['helpers'])
        self.assertEqual(manifest['application_exports'], ['selected'])
        for record, file in zip(manifest['files'], artifact.files):
            self.assertEqual(record['path'], file.path)
            self.assertEqual(record['size'], len(file.data))
            self.assertEqual(record['sha256'], hashlib.sha256(file.data).hexdigest())
        source_map = json.loads(next(file.data for file in artifact.files if file.role == 'source-map'))
        self.assertEqual(source_map['sourcesContent'], [source])
        self.assertEqual(source_map['version'], 3)
        self.assertTrue(any(source_map['mappings'].split(';')))
        code = next(file.data.decode() for file in artifact.files if file.role == 'executable-module')
        generated_line = next(index for index, line in enumerate(code.splitlines()) if 'return $binary' in line)
        consumer = "import {SourceMap} from 'node:module'; const input=JSON.parse(process.argv[1]); console.log(JSON.stringify(new SourceMap(input.map).findEntry(input.line,4)));"
        result = subprocess.run(['node', '--input-type=module', '-e', consumer,
                                 json.dumps({'map': source_map, 'line': generated_line})],
                                check=True, capture_output=True, text=True, timeout=5)
        mapping = json.loads(result.stdout)
        self.assertEqual(mapping['originalLine'], 1)
        self.assertEqual(mapping['originalColumn'], 4)
        self.assertEqual(mapping['originalSource'], 'app.py')
        manifest['files'][0]['sha256'] = 'changed'
        self.assertNotEqual(artifact.manifest['files'][0]['sha256'], 'changed')
        no_map = compile_source(source, source_map=False)
        self.assertNotIn('sourceMappingURL', next(file.data.decode() for file in no_map.files if file.role == 'executable-module'))
        self.assertNotIn('source-map', {file.role for file in no_map.files})
        for invalid in ['../app.mjs', 'app.js', 'app.mjs\nexecute', 'é.mjs']:
            with self.assertRaises(ValueError):
                compile_source('pass', module_name=invalid)
