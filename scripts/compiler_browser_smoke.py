"""Exercise the compiled worker/host target using local assets and HTTP fixtures."""

import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import time

from playwright.sync_api import sync_playwright

from JavaScript.browser import compile_browser
from JavaScript.modules import SourceModule


ROOT = Path(__file__).resolve().parents[1]
APP = '''from JavaScript import Promise
from JavaScript.browser import read_text, write_text, on_click, unsubscribe, fetch_text
from text_metrics import metrics
async def run(text):
    current = await read_text("input")
    if current != text:
        raise TypeError("input changed during this run")
    print(metrics(text))
async def load(text):
    response = await fetch_text(await read_text("url"))
    print(response[0], response[2])
async def clear(text):
    await write_text("result", "")
async def fail(text):
    if text == "raise":
        error = TypeError("explicit value")
        raise error
    if text == "reject":
        error = TypeError("rejected value")
        pending = Promise.reject(error)
        await pending
    return 1 // 0
async def busy(text):
    await write_text("status", "busy")
    total = 0
    for first in text:
        for second in text:
            for third in text:
                total = total + 1
    await write_text("status", "completed")
async def main():
    for ignored in (1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40):
        temporary = await on_click("unused", run)
        await unsubscribe(temporary)
    await on_click("run", run)
    await on_click("fetch", load)
    await on_click("clear", clear)
    await on_click("fail", fail)
    await on_click("busy", busy)
'''


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.observations.append({'path': self.path, 'cookie': self.headers.get('Cookie')})
        if self.path in {'/fixture.txt', '/large.txt', '/slow.txt', '/missing.txt', '/denied.txt', '/redirect'}:
            if self.path == '/slow.txt':
                time.sleep(3)
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/fixture.txt')
                self.end_headers()
                return
            body = b'x' * 128 if self.path == '/large.txt' else b'missing' if self.path == '/missing.txt' else b'local fixture'
            self.send_response(404 if self.path == '/missing.txt' else 200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        super().do_GET()


def sources():
    corpus = json.loads((ROOT / 'tests/fixtures/compiler_contract.json').read_text(encoding='utf-8'))
    reference = next(case['source'] for case in corpus['cases'] if case['id'] == 'text-metrics-single-module')
    metrics = reference[reference.index('SEPARATORS ='):reference.index('\nprint(metrics(')]
    metrics = 'from .helpers import character_count\n' + metrics
    return (SourceModule.from_text('app', APP),
            SourceModule.from_text('text_metrics', 'from .metrics import metrics', is_package=True),
            SourceModule.from_text('text_metrics.metrics', metrics),
            SourceModule.from_text('text_metrics.helpers', 'def character_count(text):\n    return len(text)'))


def smoke(channel=None):
    artifact = compile_browser(sources(), entrypoint='app')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for item in artifact.files:
            (root / item.path).parent.mkdir(parents=True, exist_ok=True)
            (root / item.path).write_bytes(item.data)
        subprocess.run([sys.executable, str(ROOT / 'examples/browser_text_metrics.py'), '--output', str(root / 'example')], check=True, capture_output=True, text=True, timeout=15)
        for item in artifact.manifest['files']:
            assert hashlib.sha256((root / item['path']).read_bytes()).hexdigest() == item['sha256']
        servers, threads = [], []
        for _ in range(2):
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
            server.observations = []
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append(server)
            threads.append(thread)
        origin = f'http://127.0.0.1:{servers[0].server_port}'
        cross = f'http://127.0.0.1:{servers[1].server_port}'
        app = {'manifest_sha256': hashlib.sha256(artifact.manifest_bytes).hexdigest(), 'profile': 'compiled-javascript',
               'profile_version': 1, 'entrypoint': 'app.mjs', 'engine': None}
        urls = [origin + path for path in ['/fixture.txt', '/large.txt', '/redirect', '/slow.txt', '/missing.txt']] + [cross + '/fixture.txt']
        html = '''<!doctype html><meta charset="utf-8"><title>Text metrics</title>
<textarea id="input"></textarea><input id="url"><button id="run">Run</button>
<button id="fetch">Fetch</button><button id="clear">Clear</button><button id="fail">Error</button>
<button id="busy">Busy</button><button id="unused">Unused</button><pre id="result"></pre><p id="status"></p>
<script type="module">
import {mountCompiledApplication} from './browser-host.mjs';
const controls=Object.fromEntries(['input','url','run','fetch','clear','fail','busy','unused','result','status'].map(name=>[name,document.getElementById(name)]));
window.failures=[];window.start=(overrides={},denyFetch=false)=>{
  window.controller?.stop();controls.result.textContent='';controls.status.textContent='';window.failures=[];
  window.controller=mountCompiledApplication({application:APPLICATION,
    capabilities:[{id:'output/1'},{id:'dom-text/1',controls:['input','url','result','status']},
      {id:'dom-events/1',controls:['run','fetch','clear','fail','busy','unused'],events:['click']},{id:'handles/1'},{id:'fetch/1',urls:URLS}].filter(value=>!denyFetch||value.id!=='fetch/1'),
    controls,eventInputs:{run:'input',fetch:'input',clear:'input',fail:'input',busy:'input',unused:'input'},output:controls.result,
    limits:{deadline_ms:2000,response_bytes:64,...overrides},onError:error=>{window.failures.push(error);controls.status.textContent=error.type+': '+error.message;}});
  return window.controller.ready;
};controls.url.value=URLS[0];window.start().catch(()=>{});
</script>'''.replace('APPLICATION', json.dumps(app)).replace('URLS', json.dumps(urls))
        (root / 'index.html').write_text(html, encoding='utf-8')
        checks = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=channel)
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    page.set_default_timeout(10000)
                    page.goto(origin)
                    page.wait_for_function('window.controller?.stats().subscriptions===5')
                    assert page.evaluate('window.failures.length') == 0
                    checks.append('callback-release-and-ready')
                    values = ['', 'hello world', 'A😀 é\nline two', 'a\u00a0b']
                    source = next(item.data.decode() for item in sources() if item.name == 'text_metrics.metrics')
                    reference = (next(item.data.decode() for item in sources() if item.name == 'text_metrics.helpers') + '\n' +
                                 source.replace('from .helpers import character_count\n', '') + '\nimport json\nprint(json.dumps([str(metrics(value)) for value in ' + repr(values) + ']))')
                    oracle = json.loads(subprocess.check_output([sys.executable, '-I', '-S', '-X', 'utf8', '-c', reference], text=True))
                    for value, expected in zip(values, oracle):
                        page.click('#clear')
                        page.wait_for_function('document.getElementById("result").textContent===""')
                        page.fill('#input', value)
                        page.click('#run')
                        page.wait_for_function('expected=>document.getElementById("result").textContent===expected', arg=expected + '\n')
                    checks.append('cpython-client-metrics-parity')
                    context.set_offline(True)
                    page.fill('#input', 'Offline😀')
                    page.click('#clear')
                    page.wait_for_function('document.getElementById("result").textContent===""')
                    page.click('#run')
                    page.wait_for_function('document.getElementById("result").textContent==="(8, 1, 1)\\n"')
                    context.set_offline(False)
                    checks.append('loaded-worker-offline-computation')
                    page.evaluate("document.cookie='fixture_cookie=present; SameSite=Lax'")
                    page.click('#clear');page.wait_for_function('document.getElementById("result").textContent===""')
                    page.click('#fetch')
                    page.wait_for_function('document.getElementById("result").textContent==="200 local fixture\\n"')
                    assert [row for row in servers[0].observations if row['path'] == '/fixture.txt'][-1]['cookie'] is None
                    checks.append('native-fetch-credentials-omitted')
                    page.click('#clear');page.wait_for_function('document.getElementById("result").textContent===""')
                    page.fill('#url', origin + '/missing.txt');page.click('#fetch')
                    page.wait_for_function('document.getElementById("result").textContent==="404 missing\\n"')
                    checks.append('native-fetch-http-status')
                    for path, expected in [('/denied.txt', 'DENIED'), ('/large.txt', 'QUOTA'), ('/redirect', 'IO'), (cross + '/fixture.txt', 'IO'), ('/slow.txt', 'TIMEOUT')]:
                        page.evaluate('async options=>{await window.start(options)}', {'deadline_ms': 1000} if path == '/slow.txt' else {})
                        page.wait_for_function('window.controller.stats().subscriptions===5')
                        page.fill('#url', path if path.startswith('http') else origin + path)
                        page.click('#fetch')
                        page.wait_for_function('window.failures.length===1')
                        error = page.evaluate('window.failures[0]')
                        assert error['code'] == expected, error
                        assert error['location']['filename'] == 'app.py', error
                        assert page.evaluate('window.controller.stats().subscriptions') == 0
                    assert not any(row['path'] == '/denied.txt' for row in servers[0].observations)
                    checks.append('fetch-grants-size-redirect-cors-timeout')
                    page.evaluate('window.start()');page.wait_for_function('window.controller.stats().subscriptions===5')
                    page.fill('#url', origin + '/slow.txt')
                    with page.expect_event('requestfailed', predicate=lambda request: request.url == origin + '/slow.txt') as stopped:
                        with page.expect_request(origin + '/slow.txt'):
                            page.click('#fetch')
                        page.evaluate('window.controller.stop()')
                    assert stopped.value.failure
                    assert page.evaluate('window.controller.stats().pending') == 0
                    assert page.evaluate('window.failures.length') == 0
                    checks.append('fetch-stop-cancellation')
                    page.evaluate('window.start({},true).catch(()=>{})')
                    page.wait_for_function('window.failures.length===1')
                    assert page.evaluate('window.failures[0].code') == 'UNAVAILABLE'
                    assert page.evaluate('window.controller.stats().subscriptions') == 0
                    checks.append('missing-required-capability')
                    page.evaluate('window.start()');page.wait_for_function('window.controller.stats().subscriptions===5')
                    page.click('#fail');page.wait_for_function('window.failures.length===1')
                    error = page.evaluate('window.failures[0]')
                    assert error['type'] == 'ZeroDivisionError' and error['location']['line'] == next(i for i,line in enumerate(APP.splitlines(),1) if line.strip()=='return 1 // 0'), error
                    checks.append('python-error-source-location')
                    for value, statement in [('raise','raise error'),('reject','await pending')]:
                        page.evaluate('window.start()');page.wait_for_function('window.controller.stats().subscriptions===5')
                        page.fill('#input',value);page.click('#fail');page.wait_for_function('window.failures.length===1')
                        error=page.evaluate('window.failures[0]')
                        assert error['type']=='TypeError' and error['location']['line']==next(i for i,line in enumerate(APP.splitlines(),1) if line.strip()==statement),error
                    checks.append('preconstructed-raise-and-rejection-origins')
                    sessions = []
                    for _ in range(3):
                        page.evaluate('window.start()');page.wait_for_function('window.controller.stats().subscriptions===5')
                        sessions.append(page.evaluate('window.controller.stats().session'))
                        page.evaluate('window.controller.stop()')
                        assert page.evaluate('window.controller.stats()')['subscriptions'] == 0
                    assert len(set(sessions)) == len(sessions)
                    checks.append('stop-restart-handle-baseline')
                    page.evaluate('window.start()');page.wait_for_function('window.controller.stats().subscriptions===5')
                    page.fill('#input', 'x' * 2000);page.click('#busy')
                    page.wait_for_function('document.getElementById("status").textContent==="busy"')
                    page.evaluate('window.controller.stop();document.getElementById("status").textContent="Stopped"')
                    assert page.evaluate('window.controller.stats().state') == 'closed'
                    assert page.locator('#status').inner_text() == 'Stopped'
                    checks.append('busy-worker-termination')
                    page.goto(origin + '/example/')
                    page.wait_for_function('document.getElementById("status").textContent==="Ready"')
                    page.fill('#input', 'A😀 é\nline two');page.click('#run')
                    page.wait_for_function('document.getElementById("result").textContent==="(14, 4, 2)\\n"')
                    page.click('#stop');assert page.locator('#status').inner_text() == 'Stopped'
                    page.click('#restart');page.wait_for_function('document.getElementById("status").textContent==="Ready"')
                    checks.append('subdirectory-user-example')
                    return {'browser': browser.version, 'compiler_abi': artifact.manifest['compiler']['abi'],
                            'host_protocol': 1, 'input_mode': 'compiled-module', 'checks': checks}
                finally:
                    browser.close()
        finally:
            for server in servers:
                server.shutdown();server.server_close()
            for thread in threads:
                thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = smoke(args.channel)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
