import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from JavaScript.compiler import CompileError
from JavaScript.emitter import OutputFile, compile_source
from JavaScript.modules import SourceModule, compile_modules
from test_compiler_emitter import run_node


def source(name, text, *, package=False):
    return SourceModule.from_text(name, text, is_package=package)


class CompilerModuleTests(unittest.TestCase):
    def assert_parity(self, sources, entrypoint='app'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for item in sources:
                path = root / item.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item.data)
            oracle = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c',
                'import sys,importlib;sys.path.insert(0,sys.argv[1]);importlib.import_module(sys.argv[2])',
                temporary, entrypoint], capture_output=True, text=True, encoding='utf-8', timeout=5)
        artifact = compile_modules(sources, entrypoint=entrypoint)
        result = run_node(artifact)
        self.assertEqual(result['stdout'], oracle.stdout.replace('\r\n', '\n'))
        self.assertEqual(result['error']['name'] if result['error'] else None,
                         oracle.stderr.splitlines()[-1].split(':', 1)[0] if oracle.returncode else None)
        return result

    def test_text_metrics_relative_imports_and_package_reexports(self):
        # The supported helper bytes are the reduced source form, without the
        # unused reverse utility whose slice syntax remains outside this profile.
        corpus = json.loads((Path(__file__).parent / 'fixtures/compiler_contract.json').read_text(encoding='utf-8'))
        reference = next(item['source'] for item in corpus['cases'] if item['id'] == 'text-metrics-single-module')
        metrics = reference[reference.index('SEPARATORS ='):reference.index('\nprint(metrics(')]
        metrics = metrics.replace('character_count(text)', 'count_characters(text)')
        sources = (source('app', 'from text_metrics import metrics as selected\n'
            'print(selected(""))\nprint(selected("A😀 é\\nline two"))'),
            source('text_metrics', 'from .metrics import metrics', package=True),
            source('text_metrics.metrics', 'from .helpers import character_count as count_characters\n' + metrics),
            source('text_metrics.helpers', 'def character_count(text):\n    return len(text)'))
        self.assert_parity(sources)
        bad = (source('app', 'from text_metrics import metrics\nmetrics(1)'), *sources[1:])
        result = self.assert_parity(bad)
        self.assertEqual(result['error']['location']['filename'], 'text_metrics/metrics.py')
        self.assertEqual(result['error']['message'], 'text must be str')

    def test_initialization_order_cached_imports_and_module_entry(self):
        sources = (source('app', 'print("app-before")\nfrom pkg.worker import work\n'
            'from pkg.worker import work as again\nprint(work(), again())'),
            source('pkg', 'print("package-before")\nfrom .worker import work\nprint("package-after")', package=True),
            source('pkg.worker', 'print("worker")\ndef work():\n    return 7'))
        result = self.assert_parity(sources)
        self.assertEqual(result['stdout'], 'app-before\npackage-before\nworker\npackage-after\n7 7\n')
        # Loading a child as the entry still executes its initializer once even
        # when that initializer itself imports the child.
        self.assert_parity(sources, 'pkg.worker')

    def test_shared_values_defaults_aliases_and_separate_contexts(self):
        sources = (source('app', 'from helper import echo, echo as alias, default\n'
            'def selected():\n    first = default()\n    second = default()\n'
            '    return first is second, echo(first) is first, isinstance(echo("😀"), str), len(echo((1, 2)))\n'
            'print(echo is alias, selected())'),
            source('helper', 'def echo(value):\n    return value\ndef default(value=(1, "😀")):\n    return value'))
        self.assert_parity(sources)
        result = run_node(compile_modules(sources, entrypoint='app'),
            'const one=createModule({write: text=>stdout+=text});'
            'const two=createModule({write: text=>stdout+=text});'
            'stdout+=String(one.echo===one.alias)+":"+String(one.echo!==two.echo)+":"+one.echo(9007199254740993n).toString();')
        self.assertIsNone(result['error'])
        self.assertTrue(result['stdout'].endswith('true:true:9007199254740993'))

    def test_manifest_closure_provenance_maps_and_notices(self):
        sources = (source('app', 'from helper import size\nprint(size("A😀"))'),
                   source('helper', 'def size(value):\n    return len(value)'),
                   source('unused', 'raise RuntimeError("never parse this unsupported source")'))
        notice = OutputFile('LICENSES/upstream.txt', b'Original notice\n', 'notice')
        artifact = compile_modules(sources, entrypoint='app', notices=(notice,))
        self.assertEqual(artifact, compile_modules(tuple(reversed(sources)), entrypoint='app', notices=(notice,)))
        manifest = artifact.manifest
        self.assertEqual(manifest['compiler']['abi'], 'python-browser-modules-esm/1')
        self.assertEqual([item['module'] for item in manifest['modules']], ['app', 'helper'])
        self.assertEqual(manifest['source_imports'], [{'from': 'app', 'to': 'helper'}])
        self.assertEqual(manifest['notices'], ['LICENSES/upstream.txt', 'NOTICES.txt'])
        self.assertIn(notice, artifact.files)
        by_path = {item.path: item for item in artifact.files}
        for record in manifest['files']:
            self.assertEqual(record['sha256'], hashlib.sha256(by_path[record['path']].data).hexdigest())
            self.assertEqual(record['size'], len(by_path[record['path']].data))
        for record in manifest['imports']:
            self.assertIn(record['from'], by_path)
            self.assertIn(record['to'], by_path)
        for module in manifest['modules']:
            mapping = json.loads(by_path[module['file'] + '.map'].data)
            original = next(item for item in sources if item.name == module['module'])
            self.assertEqual(mapping['sources'], [original.filename])
            self.assertEqual(mapping['sourcesContent'], [original.data.decode()])
            self.assertEqual(module['sha256'], original.sha256)
        no_maps = compile_modules(sources, entrypoint='app', source_map=False)
        self.assertNotIn('source-map', {item.role for item in no_maps.files})
        self.assertNotIn('javascript', manifest['helpers'])
        self.assertNotIn('iterate', manifest['helpers'])

    def test_import_and_initialization_boundaries_fail_without_execution(self):
        cases = [
            (source('app', 'import helper'), source('helper', 'pass')),
            (source('app', 'from helper import *'), source('helper', 'pass')),
            (source('app', 'from missing import selected'),),
            (source('app', 'from helper import absent'), source('helper', 'pass')),
            (source('app', 'from helper import selected'), source('helper', 'from app import selected')),
            (source('app', 'if True:\n    from helper import selected'), source('helper', 'def selected():\n    pass')),
            (source('app', 'def selected():\n    from helper import x'), source('helper', 'x=1')),
            (source('app', 'from pkg.helper import x'), source('pkg.helper', 'x=1')),
            (source('app', 'from helper import x'), source('helper', 'class x:\n    pass')),
            (source('app', 'from helper import Array'), source('helper', 'from JavaScript import Array')),
            (source('app', 'from helper import x\nx=1'), source('helper', 'x=1')),
            (source('app', 'from pkg import x'), source('pkg', 'values=[]\nx=1', package=True)),
            (source('app', 'from helper import x'), source('helper', 'x=1\ndef unused(text):\n    return text[::-1]')),
            (source('app', 'from ...helper import x'),),
            (source('app', '__import__("helper")'),),
        ]
        for sources in cases:
            with self.subTest(source=sources[0].data), self.assertRaises(CompileError) as caught:
                compile_modules(sources, entrypoint='app')
            self.assertIn(caught.exception.diagnostic.code, {'PJS100', 'PJS110'})
        with self.assertRaises(CompileError):
            compile_source('from helper import selected')
        result = self.assert_parity((source('app', 'print(later())\nfrom helper import later'),
                                    source('helper', 'def later():\n    return 1')))
        self.assertEqual(result['error']['location']['line'], 1)

    def test_verified_input_limits_and_portable_output_paths(self):
        item = source('app', 'pass')
        with self.assertRaises(ValueError):
            SourceModule('app', b'pass', '0' * 64)
        for name in ['sys', 'JavaScript', 'os.local', 'x-y', '__main__', 'class']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                source(name, 'pass')
        for filename in ['../app.py', '/app.py', 'CON.py', 'app.py\n', 'x\\app.py']:
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                SourceModule.from_text('app', 'pass', filename=filename)
        for sources in [(), (item,) * 2, tuple(source('app' + str(i), 'pass') for i in range(33))]:
            with self.assertRaises(ValueError):
                compile_modules(sources, entrypoint='app')
        with self.assertRaises(TypeError):
            compile_modules([item], entrypoint='app')
        for notice in [OutputFile('LICENSES/../app.mjs', b'x', 'notice'),
                       OutputFile('LICENSES/CON.txt', b'x', 'notice'),
                       OutputFile('LICENSES/x', b'', 'notice'),
                       OutputFile('LICENSES/x', b'x', 'executable-module')]:
            with self.subTest(notice=notice), self.assertRaises(ValueError):
                compile_modules((item,), entrypoint='app', notices=(notice,))
        with self.assertRaises(ValueError):
            compile_modules((item,), entrypoint='app', notices=(
                OutputFile('LICENSES/x', b'x', 'notice'), OutputFile('LICENSES/x/y', b'y', 'notice')))
