import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from JavaScript.emitter import compile_source
from JavaScript.modules import SourceModule, compile_modules
from test_compiler_async import run_async
from test_compiler_emitter import run_node


class CompilerErrorOriginTests(unittest.TestCase):
    def assert_origin(self, source, *, asynchronous=False):
        oracle = '''import contextlib,io,json,traceback
source = ''' + repr(source) + '''
namespace={};output=io.StringIO()
try:
    with contextlib.redirect_stdout(output):
        exec(compile(source,'origin.py','exec'),namespace)
'''
        if asynchronous:
            oracle += "        import asyncio\n        asyncio.run(namespace['main']())\n"
        oracle += '''except Exception as error:
    frame=[frame for frame in traceback.extract_tb(error.__traceback__) if frame.filename=='origin.py'][-1]
    print(json.dumps({'stdout':output.getvalue(),'name':type(error).__name__,'message':str(error),'line':frame.lineno}))
'''
        expected = json.loads(subprocess.check_output([sys.executable, '-I', '-X', 'utf8', '-c', oracle], text=True, encoding='utf-8', timeout=10))
        artifact = compile_source(source, filename='origin.py', async_enabled=asynchronous)
        actual = run_async(artifact) if asynchronous else run_node(artifact)
        self.assertEqual(actual['stdout'], expected['stdout'])
        self.assertEqual(actual['error']['name'], expected['name'])
        self.assertEqual(actual['error']['message'], expected['message'])
        self.assertEqual(actual['error']['location']['filename'], 'origin.py')
        self.assertEqual(actual['error']['location']['line'], expected['line'])
        return actual

    def test_preconstructed_exception_reports_raise_instead_of_constructor(self):
        actual = self.assert_origin('def selected():\n    error=TypeError("bad")\n    print(error is error)\n    raise error\nselected()')
        self.assertEqual(actual['error']['location']['line'], 4)
        self.assertEqual(actual['error']['location']['column'], 5)

    def test_promise_value_origin_and_prior_callback_runtime_origins(self):
        cases = [
            'from JavaScript import Promise\nasync def main():\n    error=TypeError("rejected")\n    pending=Promise.reject(error)\n    await pending',
            'from JavaScript import Promise\ndef callback(value):\n    print("once")\n    error=TypeError("callback")\n    raise error\nasync def main():\n    await Promise.resolve(1).then(callback)',
            'async def inner():\n    return 1//0\nasync def main():\n    return await inner()',
            'from JavaScript import Promise\ndef identity(value):\n    return value\nasync def main():\n    error=TypeError("same object")\n    observed=await Promise.reject(error).then(None,identity)\n    print(error is observed)\n    raise error',
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assert_origin(source, asynchronous=True)

    def test_shared_runtime_retains_callback_module_origin(self):
        sources = (SourceModule.from_text('app', 'from JavaScript import Promise\nfrom helper import callback\nasync def main():\n    await Promise.resolve(1).then(callback)'),
                   SourceModule.from_text('helper', 'def callback(value):\n    error=TypeError("module")\n    raise error'))
        result = run_async(compile_modules(sources, entrypoint='app', async_enabled=True))
        self.assertEqual(result['error']['location']['filename'], 'helper.py')
        self.assertEqual(result['error']['location']['line'], 3)

    def test_native_traceback_maps_to_the_raise_statement(self):
        source = 'def selected():\n    error=TypeError("bad")\n    raise error\nselected()'
        artifact = compile_source(source, filename='origin.py')
        runner = '''import {createModule} from './app.mjs';import {SourceMap} from 'node:module';import {readFile} from 'node:fs/promises';
const map=new SourceMap(JSON.parse(await readFile(new URL('./app.mjs.map',import.meta.url))));
try{createModule()}catch(error){const match=error.stack.match(/app\\.mjs:(\\d+):(\\d+)/);console.log(JSON.stringify(map.findEntry(Number(match[1])-1,Number(match[2])-1)));}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for item in artifact.files:
                (root / item.path).write_bytes(item.data)
            (root / 'run.mjs').write_text(runner)
            result = json.loads(subprocess.check_output(['node', str(root / 'run.mjs')], text=True, timeout=10))
        self.assertEqual(result['originalSource'], 'origin.py')
        self.assertEqual(result['originalLine'], 2)
        self.assertEqual(result['originalColumn'], 4)
