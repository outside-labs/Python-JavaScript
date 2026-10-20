import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from JavaScript.compiler import CompileError, parse_source
from JavaScript.emitter import compile_source
from JavaScript.modules import SourceModule, compile_modules


def run_async(artifact, invocation='await app.main();', options='write: text=>stdout+=text'):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for file in artifact.files:
            (root / file.path).write_bytes(file.data)
        (root / 'run.mjs').write_text(
            "import {createModule} from './app.mjs';let stdout='',error=null;\n"
            "const controller=new AbortController();let listeners=0;"
            "const signal={get aborted(){return controller.signal.aborted},"
            "addEventListener(...args){listeners++;controller.signal.addEventListener(...args)},"
            "removeEventListener(...args){listeners--;controller.signal.removeEventListener(...args)}};\n"
            "try { const app=createModule({" + options + "});" + invocation + " }"
            "catch(caught){error={name:caught.name,message:caught.message,code:caught.code,location:caught.location};}"
            "await new Promise(resolve=>setImmediate(resolve));"
            "console.log(JSON.stringify({stdout,error,listeners}));", encoding='utf-8')
        process = subprocess.run(['node', '--unhandled-rejections=strict', str(root / 'run.mjs')],
                                 check=True, capture_output=True, text=True, encoding='utf-8', timeout=10)
        return json.loads(process.stdout)


class CompilerAsyncTests(unittest.TestCase):
    def assert_parity(self, source):
        oracle = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', source + '\nimport asyncio\nasyncio.run(main())'],
                                capture_output=True, text=True, encoding='utf-8', timeout=10)
        result = run_async(compile_source(source, filename='async_case.py', async_enabled=True))
        self.assertEqual(result['stdout'], oracle.stdout.replace('\r\n', '\n'))
        self.assertEqual(result['error']['name'] if result['error'] else None,
                         oracle.stderr.splitlines()[-1].split(':', 1)[0] if oracle.returncode else None)
        return result

    def test_lazy_coroutines_defaults_order_and_reuse(self):
        self.assert_parity('''async def selected(value=(1, "😀")):
    print("inside", value)
    return value
async def main():
    pending = selected()
    print("before")
    first = await pending
    print("after", first)
    second = await selected()
    print(first is second)
''')
        result = self.assert_parity('''async def selected():
    return 1
async def main():
    pending = selected()
    print(await pending)
    await pending
''')
        self.assertEqual(result['error']['message'], 'cannot reuse already awaited coroutine')

    def test_promise_conversion_chained_callbacks_and_errors_once(self):
        source = '''from JavaScript import Promise as P
def add(value):
    print("callback", value)
    return P.resolve(value + 1)
def recover(error):
    print("recovered")
    return 8
async def main():
    print(await P.resolve(9007199254740993).then(add))
    print(await P.reject(TypeError("bad")).then(None, recover))
'''
        self.assert_parity(source)
        result = self.assert_parity('''from JavaScript import Promise
def fail(value):
    print("once")
    raise TypeError("callback failed")
async def main():
    print(await Promise.resolve(1).then(fail))
''')
        self.assertEqual(result['error']['message'], 'callback failed')
        self.assertEqual(result['error']['location']['line'], 4)

    def test_await_in_chained_comparisons_short_circuit_and_loops(self):
        self.assert_parity('''import JavaScript as JS
async def mark(value):
    print(value)
    return await JS.Promise.resolve(value)
async def main():
    print(await mark(1) < await mark(2) < await mark(3))
    print(await mark(3) < await mark(2) < await mark(1))
    print(False and await mark("never"))
    print(True or await mark("never"))
    for value in (1, 2):
        print(await mark(value))
''')

    def test_cross_module_await_preserves_values_and_provenance(self):
        sources = (SourceModule.from_text('app', 'from helper import selected as main'),
                   SourceModule.from_text('helper', 'from JavaScript import Promise\nasync def selected():\n    print(await Promise.resolve(("😀", 9007199254740993)))'))
        artifact = compile_modules(sources, entrypoint='app', async_enabled=True)
        result = run_async(artifact)
        self.assertIsNone(result['error'])
        self.assertEqual(result['stdout'], "('😀', 9007199254740993)\n")
        self.assertEqual(artifact.manifest['language_profile'], 'python-browser-modules-async/1')
        self.assertIn('async-expose', artifact.manifest['helpers'])
        artifact = compile_source('async def main():\n    return 1 // 0', async_enabled=True, filename='original.py')
        error = run_async(artifact)['error']
        self.assertEqual(error['name'], 'ZeroDivisionError')
        self.assertEqual(error['location']['filename'], 'original.py')
        self.assertEqual(error['location']['line'], 2)

    def test_cancellation_checkpoints_release_listeners_and_reject_exports(self):
        artifact = compile_source('from JavaScript import Promise\nasync def main():\n    print("begin")\n'
                                  '    value = await Promise.resolve(1)\n    print("after", value)', async_enabled=True)
        for invocation in ['controller.abort();await app.main();',
                           'const pending=app.main();queueMicrotask(()=>controller.abort());await pending;']:
            result = run_async(artifact, invocation, 'write: text=>stdout+=text,signal')
            self.assertEqual(result['error']['code'], 'CANCELLED')
            self.assertNotIn('after', result['stdout'])
            self.assertEqual(result['listeners'], 0)
        # An output sink can cancel synchronously while a coroutine is starting.
        result = run_async(artifact, options='write: text=>{stdout+=text;controller.abort()},signal')
        self.assertEqual(result['error']['code'], 'CANCELLED')
        self.assertEqual(result['stdout'], 'begin\n')
        self.assertEqual(result['listeners'], 0)
        result = run_async(artifact, options='write: text=>stdout+=text,signal')
        self.assertIsNone(result['error'])
        self.assertEqual(result['listeners'], 0)

    def test_async_call_bound_and_rejected_forms(self):
        artifact = compile_source('async def main():\n    return await main()', async_enabled=True)
        self.assertEqual(run_async(artifact)['error']['name'], 'RecursionError')
        sources = ['async def main():\n    return await 1',
                   'from JavaScript import Promise\nasync def callback(value):\n    return value\n'
                   'async def main():\n    return await Promise.resolve(1).then(callback)',
                   'from JavaScript import Promise\nasync def main():\n    return Promise.resolve(1)',
                   'async def main():\n    return main()',
                   'async def main():\n    async for value in ():\n        pass',
                   'async def main():\n    async with thing:\n        pass',
                   'from JavaScript import fetch\nasync def main():\n    return await fetch("url")',
                   'from JavaScript import Promise\nPromise.all(())']
        for source in sources:
            with self.subTest(source=source), self.assertRaises(CompileError):
                compile_source(source, async_enabled=True)
        with self.assertRaises(CompileError):
            parse_source('async def main():\n    return 1')
        with self.assertRaises(TypeError):
            parse_source('pass', async_enabled=1)
