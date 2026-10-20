import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import JavaScript
from JavaScript.browser import compile_browser
from JavaScript.compiler import CompileError
from JavaScript.emitter import compile_source
from JavaScript.modules import SourceModule


SOURCE = '''from JavaScript.browser import read_text as read, write_text, on_click, unsubscribe, fetch_text
async def selected(text):
    print(text)
async def main():
    subscription = await on_click("run", selected)
    value = await read("input")
    await write_text("result", value)
    await unsubscribe(subscription)
    response = await fetch_text("https://example.invalid/text")
    print(response[0], response[2])
'''


class CompilerBrowserTests(unittest.TestCase):
    def test_profile_capabilities_hashes_static_closure_and_source_maps(self):
        sources = (SourceModule.from_text('app', SOURCE),)
        artifact = compile_browser(sources, entrypoint='app')
        self.assertEqual(artifact, compile_browser(sources, entrypoint='app'))
        manifest = artifact.manifest
        self.assertEqual(manifest['compiler']['abi'], 'python-browser-host-esm/1')
        self.assertEqual(manifest['language_profile'], 'python-browser-modules-host-async/1')
        self.assertEqual(manifest['browser']['capabilities'], ['dom-events/1', 'dom-text/1', 'fetch/1', 'handles/1', 'output/1'])
        paths = {item.path for item in artifact.files}
        self.assertTrue({'browser-host.mjs', 'browser-worker.mjs', 'browser-protocol.mjs'} <= paths)
        for record, item in zip(manifest['files'], artifact.files):
            self.assertEqual(record['path'], item.path)
            self.assertEqual(record['sha256'], hashlib.sha256(item.data).hexdigest())
            self.assertEqual(record['size'], len(item.data))
        for edge in manifest['imports']:
            self.assertIn(edge['from'], paths)
            self.assertIn(edge['to'], paths)

    def test_compiled_bridge_types_callbacks_and_release_without_host_execution_fallback(self):
        artifact = compile_browser((SourceModule.from_text('app', SOURCE),), entrypoint='app')
        runner = '''import {createModule} from './app.mjs';
let stdout='',callback=null;const calls=[];
const str=value=>({type:'str',codepoints:Array.from(value,ch=>ch.codePointAt(0))});
const host={registerCallback:fn=>{callback=fn;return{type:'handle',owner:'worker',kind:'callback',id:'w1'}},
releaseCallback:()=>{callback=null},request:async(operation,args)=>{
 calls.push({operation,args});
 if(operation==='events.subscribe'){await callback(str('A😀'));return{type:'handle',owner:'main',kind:'event.subscription',id:'m1'}}
 if(operation==='dom.read')return str('A😀');
 if(operation==='fetch.text')return{type:'dict',entries:[[str('status'),{type:'int',value:'200'}],[str('url'),str('https://example.invalid/text')],[str('text'),str('local')]]};
 return{type:'none'};
}};
const app=createModule({host,write:text=>stdout+=text});await app.main();
console.log(JSON.stringify({stdout,calls,released:callback===null}));
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for item in artifact.files:
                (root / item.path).write_bytes(item.data)
            (root / 'run.mjs').write_text(runner, encoding='utf-8')
            result = subprocess.run(['node', '--unhandled-rejections=strict', str(root / 'run.mjs')],
                                    check=True, capture_output=True, text=True, encoding='utf-8', timeout=10)
        result = json.loads(result.stdout)
        self.assertEqual(result['stdout'], 'A😀\n200 local\n')
        self.assertTrue(result['released'])
        self.assertEqual([call['operation'] for call in result['calls']], ['events.subscribe', 'dom.read', 'dom.write', 'events.unsubscribe', 'fetch.text'])
        self.assertEqual(result['calls'][2]['args']['text']['codepoints'], [65, 0x1f600])

    def test_protocol_shapes_sequences_stale_sessions_and_negative_capabilities(self):
        protocol = Path(JavaScript.__file__).parent / '_browser/browser-protocol.mjs'
        fixture = Path(__file__).parent / 'fixtures/browser_protocol.mjs'
        subprocess.run(['node', str(fixture), protocol.as_uri()], check=True, capture_output=True, text=True, timeout=10)

    def test_browser_imports_initialization_and_entry_boundaries_fail_without_execution(self):
        sources = ['print("initialization")\nasync def main():\n    pass',
                   'async def main(value):\n    return value', 'def main():\n    return 1',
                   'from JavaScript.browser import location\nasync def main():\n    pass',
                   'from JavaScript.browser import on_click\nasync def main():\n    await on_click("run",1)',
                   'from JavaScript.browser import *\nasync def main():\n    pass']
        for source in sources:
            with self.subTest(source=source), self.assertRaises(CompileError):
                compile_browser((SourceModule.from_text('app', source),), entrypoint='app')
        with self.assertRaises(CompileError):
            compile_source(SOURCE, async_enabled=True)
