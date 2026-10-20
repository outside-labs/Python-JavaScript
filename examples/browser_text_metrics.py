"""Build a local text-metrics browser application from the approved source corpus."""

import argparse
import hashlib
import json
from pathlib import Path

from JavaScript.browser import compile_browser
from JavaScript.emitter import OutputFile
from JavaScript.modules import SourceModule


ROOT = Path(__file__).resolve().parents[1]
APP = '''from JavaScript.browser import on_click
from text_metrics import metrics
async def display(text):
    print(metrics(text))
async def main():
    await on_click("run", display)
'''


def build(output):
    corpus = json.loads((ROOT / 'tests/fixtures/compiler_contract.json').read_text(encoding='utf-8'))
    reference = next(case['source'] for case in corpus['cases'] if case['id'] == 'text-metrics-single-module')
    computation = reference[:reference.index('\nprint(metrics(')]
    artifact = compile_browser((SourceModule.from_text('app', APP), SourceModule.from_text('text_metrics', computation)), entrypoint='app',
        notices=(OutputFile('LICENSES/shimify.txt', (ROOT / 'tests/fixtures/licenses/SHIMIFY-LICENSE.txt').read_bytes(), 'notice'),))
    identity = {'manifest_sha256': hashlib.sha256(artifact.manifest_bytes).hexdigest(), 'profile': 'compiled-javascript',
                'profile_version': 1, 'entrypoint': 'app.mjs', 'engine': None}
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Text metrics</title><style>
body{font:1.1rem system-ui,sans-serif;max-width:44rem;margin:4rem auto;padding:0 1.5rem;color:#19362c;background:#f4f7f1}
textarea{box-sizing:border-box;width:100%;min-height:12rem;padding:1rem;font:inherit;border:1px solid #779287;border-radius:.5rem;background:white}
button{padding:.6rem 1rem;font:inherit;border:1px solid #779287;border-radius:.4rem;background:white;cursor:pointer}
#run{background:#225841;color:white}nav{display:flex;gap:.5rem;margin:1rem 0}pre{min-height:3rem;white-space:pre-wrap;padding:1rem;background:white;border-radius:.5rem}
</style><main><h1>Text metrics</h1><p>Count characters, words and lines locally in your browser.</p>
<label for="input">Text</label><textarea id="input" placeholder="Write something…"></textarea>
<nav><button id="run" disabled>Run</button><button id="stop">Stop</button><button id="restart">Restart</button></nav>
<p>Characters, words, lines</p><pre id="result" aria-live="polite"></pre><p id="status" role="status"></p></main>
<script type="module">
import {mountCompiledApplication} from './browser-host.mjs';
const byId=name=>document.getElementById(name);let current;
function start(){
  current?.stop();byId('run').disabled=true;byId('result').textContent='';byId('status').textContent='Starting…';
  const active=mountCompiledApplication({application:APPLICATION,
    capabilities:[{id:'output/1'},{id:'dom-text/1',controls:['input']},{id:'dom-events/1',controls:['run'],events:['click']},{id:'handles/1'}],
    controls:{input:byId('input'),run:byId('run')},eventInputs:{run:'input'},output:byId('result'),
    onError:error=>{byId('status').textContent=error.type+': '+error.message;}});
  current=active;active.ready.then(async()=>{
    while(current===active&&active.stats().state==='ready'&&active.stats().subscriptions<1)await new Promise(requestAnimationFrame);
    if(current===active&&active.stats().state==='ready'){byId('run').disabled=false;byId('status').textContent='Ready';}
  },()=>{});
}
byId('stop').addEventListener('click',()=>{current?.stop();byId('run').disabled=true;byId('status').textContent='Stopped';});
byId('restart').addEventListener('click',start);start();
</script></html>'''.replace('APPLICATION', json.dumps(identity))
    files = {item.path: item.data for item in artifact.files}
    files.update({'COMPILED-MANIFEST.json': artifact.manifest_bytes, 'index.html': html.encode('utf-8')})
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new output directory.')
    output.mkdir(parents=True)
    written, directories = [], []
    try:
        parents = {parent for name in files for parent in (output / name).parents if parent != output and output in parent.parents}
        for directory in sorted(parents, key=lambda path: len(path.parts)):
            directory.mkdir()
            directories.append(directory)
        for name, data in files.items():
            path = output / name
            with path.open('xb') as stream:
                written.append(path)
                stream.write(data)
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        for directory in reversed(directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            output.rmdir()
        except OSError:
            pass
        raise
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.output)
    except ValueError as error:
        parser.error(str(error))
    print('Created ' + str(args.output))


if __name__ == '__main__':
    main()
