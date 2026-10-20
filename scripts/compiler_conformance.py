"""Compare approved emitted modules in Node and browser workers with CPython."""

import argparse
from contextlib import redirect_stdout
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from threading import Thread
import traceback

from JavaScript.compiler import CompileError
from JavaScript.emitter import OutputFile, compile_source
from JavaScript.modules import SourceModule, compile_modules


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
RUNNER = ROOT / 'scripts/compiler_conformance.mjs'
LICENSE = FIXTURES / 'licenses/SHIMIFY-LICENSE.txt'


def load_cases():
    contract = json.loads((FIXTURES / 'compiler_contract.json').read_text(encoding='utf-8'))
    parity = json.loads((FIXTURES / 'compiler_parity.json').read_text(encoding='utf-8'))
    cases = [dict(case, family='core') for case in contract['cases']] + parity['cases']
    identities = [case['id'] for case in cases + contract['boundaries'] + parity['boundaries']]
    if len(identities) != len(set(identities)):
        raise ValueError('Conformance identities must be unique.')
    return cases, contract['boundaries'] + parity['boundaries']


def typed(value):
    if value is None:
        return {'type': 'none'}
    if type(value) is bool:
        return {'type': 'bool', 'value': value}
    if type(value) is int:
        return {'type': 'int', 'value': str(value)}
    if type(value) is str:
        return {'type': 'str', 'codepoints': list(map(ord, value))}
    if type(value) is tuple:
        return {'type': 'tuple', 'items': list(map(typed, value))}
    raise TypeError('Unadopted reference result: ' + type(value).__name__)


def oracle(case):
    """Test-only trusted fixture execution in a fresh isolated reference process."""
    output, result, failure = io.StringIO(), None, None
    sources = case['modules'] if 'modules' in case else [{'name': 'app', 'source': case['source']}]
    namespace = {'__name__': '__main__'}
    owned = {item['name'].replace('.', '/') + ('/__init__.py' if item.get('package') else '.py'): item['source'] for item in sources}
    with tempfile.TemporaryDirectory() as temporary, redirect_stdout(output):
        root = Path(temporary)
        try:
            if 'modules' in case:
                import importlib
                for name, source in owned.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(source, encoding='utf-8')
                sys.path.insert(0, str(root))
                namespace = vars(importlib.import_module('app'))
            else:
                exec(compile(case['source'], 'app.py', 'exec'), namespace)
            if case.get('export'):
                result = namespace[case['export']]()
                if case.get('async'):
                    import asyncio
                    result = asyncio.run(result)
        except Exception as error:
            result = None
            frames = []
            for frame in traceback.extract_tb(error.__traceback__):
                filename = frame.filename
                try:
                    filename = Path(filename).relative_to(root).as_posix()
                except ValueError:
                    pass
                if filename in owned:
                    frames.append((filename, frame))
            filename, frame = frames[-1]
            line = owned[filename].splitlines()[frame.lineno - 1]
            # CPython's code-position columns use UTF-8 bytes; the profile uses code points.
            column = len(line.encode('utf-8')[:frame.colno].decode('utf-8')) + 1
            failure = {'name': type(error).__name__, 'message': str(error),
                       'location': {'filename': filename, 'line': frame.lineno, 'column': column}}
    return {'stdout': output.getvalue(), 'value': typed(result), 'error': failure}


def compile_case(case):
    notices = (OutputFile('LICENSES/shimify.txt', LICENSE.read_bytes(), 'notice'),) if case.get('borrowed') else ()
    if 'modules' in case or notices:
        modules = case.get('modules') or [{'name': 'app', 'source': case['source']}]
        sources = tuple(SourceModule.from_text(item['name'], item['source'], is_package=item.get('package', False)) for item in modules)
        return compile_modules(sources, entrypoint='app', async_enabled=case.get('async', False), notices=notices)
    return compile_source(case['source'], async_enabled=case.get('async', False))


def reference(case):
    process = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()), '--oracle'],
                             input=json.dumps(case), text=True, encoding='utf-8', capture_output=True, check=True, timeout=15)
    return json.loads(process.stdout)


def prepare(root):
    cases, boundaries = load_cases()
    entries, expected, artifacts = [], {}, {}
    for case in cases:
        # The shared computation is borrowed from Shimify and carries its exact MIT notice.
        if case['id'] == 'text-metrics-single-module':
            case = dict(case, borrowed=True)
        artifact = compile_case(case)
        directory = root / case['id']
        for item in artifact.files:
            path = directory / item.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item.data)
        entries.append({'id': case['id'], 'url': './' + case['id'] + '/app.mjs', 'export': case.get('export')})
        expected[case['id']] = reference(case)
        artifacts[case['id']] = artifact
        if 'stdout' in case and expected[case['id']]['stdout'] != case['stdout']:
            raise AssertionError('Reference corpus expectation drifted: ' + case['id'])
    rejected = []
    for case in boundaries:
        try:
            compile_source(case['source'], async_enabled=case.get('async', False))
        except CompileError as error:
            diagnostic = error.diagnostic.code
            if diagnostic != case['diagnostic']:
                raise AssertionError((case['id'], diagnostic, case['diagnostic']))
            rejected.append({'id': case['id'], 'classification': case['classification'], 'diagnostic': diagnostic})
        else:
            raise AssertionError('Unsupported fixture compiled: ' + case['id'])
    (root / 'runner.mjs').write_bytes(RUNNER.read_bytes())
    (root / 'cases.json').write_text(json.dumps(entries), encoding='utf-8')
    return cases, expected, artifacts, rejected


def run_node(root):
    launcher = "import {readFile} from 'node:fs/promises';import {runCases} from './runner.mjs';const cases=JSON.parse(await readFile(new URL('./cases.json',import.meta.url)));console.log(JSON.stringify(await runCases(cases)));"
    (root / 'node.mjs').write_text(launcher, encoding='utf-8')
    return json.loads(subprocess.check_output(['node', '--unhandled-rejections=strict', str(root / 'node.mjs')], text=True, encoding='utf-8', timeout=40))


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run_browser(root, channel):
    from playwright.sync_api import sync_playwright
    (root / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Compiler conformance</title>', encoding='utf-8')
    (root / 'worker.mjs').write_text("import {runCases} from './runner.mjs';self.onmessage=async event=>{try{self.postMessage({result:await runCases(event.data)})}catch(error){self.postMessage({failure:String(error.stack)})}};", encoding='utf-8')
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=channel)
            try:
                page = browser.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.set_default_timeout(30000)
                result = page.evaluate("""async()=>{
                  const cases=await (await fetch('./cases.json')).json();
                  const worker=new Worker('./worker.mjs',{type:'module'});
                  try{return await new Promise((resolve,reject)=>{
                    const timer=setTimeout(()=>reject(new Error('Conformance worker timed out')),25000);
                    worker.onmessage=event=>{clearTimeout(timer);event.data.failure?reject(new Error(event.data.failure)):resolve(event.data.result)};
                    worker.onerror=event=>{clearTimeout(timer);reject(new Error(event.message))};
                    worker.postMessage(cases);
                  })}finally{worker.terminate()}
                }""")
                return result, browser.version
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def mapped_frames(root, artifact, stack):
    maps = {item.path.removesuffix('.map'): json.loads(item.data) for item in artifact.files if item.role == 'source-map'}
    consumer = """import {SourceMap} from 'node:module';let text='';for await(const chunk of process.stdin)text+=chunk;
const {maps,stack}=JSON.parse(text),frames=[];
for(const match of stack.matchAll(/(?:[/\\\\])([^/\\\\():\\s]+\\.mjs):(\\d+):(\\d+)/g)){
 if(!maps[match[1]])continue;
 const entry=new SourceMap(maps[match[1]]).findEntry(Number(match[2])-1,Number(match[3])-1);
 if(entry.originalSource!==undefined)frames.push({filename:entry.originalSource,line:entry.originalLine+1,column:entry.originalColumn+1});
}console.log(JSON.stringify(frames));"""
    process = subprocess.run(['node', '--input-type=module', '-e', consumer], input=json.dumps({'maps': maps, 'stack': stack}),
                             capture_output=True, text=True, encoding='utf-8', timeout=10, check=True)
    return json.loads(process.stdout)


def compare(cases, expected, actual, artifacts, root):
    if len(actual['cases']) != len(cases) or len({item['id'] for item in actual['cases']}) != len(cases):
        raise AssertionError('Missing or duplicate target cases.')
    by_id = {item['id']: item for item in actual['cases']}
    records = []
    for case in cases:
        observed = dict(by_id[case['id']])
        observed.pop('id')
        stack = observed.pop('stack', '')
        if observed['error']:
            observed['error']['location'] = {key: observed['error']['location'][key] for key in ['filename', 'line', 'column']}
        if observed != expected[case['id']]:
            raise AssertionError((case['id'], 'reference', expected[case['id']], 'target', observed))
        frames = mapped_frames(root, artifacts[case['id']], stack) if stack else []
        if case.get('traceback'):
            origin = expected[case['id']]['error']['location']
            if not frames or (frames[0]['filename'], frames[0]['line']) != (origin['filename'], origin['line']):
                raise AssertionError((case['id'], 'mapped traceback', frames, 'origin', origin))
        records.append({'id': case['id'], 'family': case['family'], 'status': 'pass', **observed, 'mapped_frames': frames})
    if actual['native'] != {'array-length': 3, 'promise-order': ['sync', 'callback', 'await'], 'utf16-length': 2}:
        raise AssertionError(('native observation drift', actual['native']))
    return {'cases': records, 'native': actual['native']}


def conformance(*, browser=False, channel=None):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        cases, expected, artifacts, rejected = prepare(root)
        node = compare(cases, expected, run_node(root), artifacts, root)
        targets = {'node': {'version': subprocess.check_output(['node', '--version'], text=True).strip(), **node}}
        if browser:
            actual, browser_version = run_browser(root, channel)
            targets['browser-worker'] = {'version': browser_version, **compare(cases, expected, actual, artifacts, root)}
        digest = hashlib.sha256()
        for path in [FIXTURES / 'compiler_contract.json', FIXTURES / 'compiler_parity.json', RUNNER, LICENSE]:
            data = path.read_bytes()
            digest.update(len(data).to_bytes(8, 'big'))
            digest.update(data)
        return {'schema_version': 1, 'suite': 'compiler-parity/1', 'corpus_sha256': digest.hexdigest(),
                'reference': {'implementation': platform.python_implementation(), 'version': platform.python_version()},
                'execution': 'ahead-of-time emitted modules; no target Python fallback',
                'targets': targets, 'boundaries': rejected,
                'artifacts': {name: hashlib.sha256(item.manifest_bytes).hexdigest() for name, item in artifacts.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oracle', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--channel')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.oracle:
        print(json.dumps(oracle(json.load(sys.stdin))))
        return
    report = conformance(browser=args.browser, channel=args.channel)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'suite': report['suite'], 'reference': report['reference'], 'targets': {
        name: {'version': target['version'], 'passed': len(target['cases'])} for name, target in report['targets'].items()}, 'boundaries': len(report['boundaries'])}))


if __name__ == '__main__':
    main()
