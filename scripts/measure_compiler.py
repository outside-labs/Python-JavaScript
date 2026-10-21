"""Measure only the approved compiler corpus and shared computation fixtures."""

import argparse
from datetime import UTC, datetime
from functools import partial
import gzip
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tarfile
import tempfile
from threading import Thread
import time
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import url2pathname
import zlib

import JavaScript
from JavaScript._compiler_runtime import HELPERS, helper_closure
from JavaScript.emitter import OutputFile
from JavaScript.modules import SourceModule, compile_modules

import compiler_conformance as parity


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = [('required-maps', False, True), ('all-profile-maps', True, True),
            ('required-no-maps', False, False), ('all-profile-no-maps', True, False)]
WORKER = '''import {execute} from './measure-runtime.mjs';
self.onmessage=async({data})=>{
  try{
    const observations=[];
    for(const entry of data.entries)observations.push({id:entry.id,...await execute(entry.url,entry.export)});
    self.postMessage({id:data.id,observations});
  }catch(error){self.postMessage({id:data.id,error:String(error.stack)});}
};
self.postMessage({id:0});
'''
PAGE = '''<!doctype html><meta charset="utf-8"><title>Compiler measurement</title>
<script type="module">
let worker,sequence=0;const pending=new Map();
window.closeWorker=()=>{worker?.terminate();worker=null;for(const entry of pending.values())entry.reject(new Error('Worker closed'));pending.clear();};
window.openWorker=async()=>{
  window.closeWorker();worker=new Worker('./measure-worker.mjs',{type:'module'});
  await new Promise((resolve,reject)=>{
    worker.onmessage=({data})=>{if(data.id===0){resolve();return;}const entry=pending.get(data.id);if(!entry)return;pending.delete(data.id);data.error?entry.reject(new Error(data.error)):entry.resolve(data.observations);};
    worker.onerror=event=>reject(new Error(event.message));
  });
};
window.request=entries=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});worker.postMessage({id,entries});});
window.measureStartup=async()=>{const before=performance.now();await window.openWorker();const [observation]=await window.request([{id:'fixture',url:new URL('./app.mjs',location.href).href,export:'main'}]);return{wall_ms:performance.now()-before,...observation};};
</script>
'''


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def compile_case(case, *, all_helpers=False, source_map=True):
    modules = case.get('modules') or [{'name':'app', 'source':case['source']}]
    sources = tuple(SourceModule.from_text(item['name'], item['source'], is_package=item.get('package', False)) for item in modules)
    notices = (OutputFile('LICENSES/shimify.txt', parity.LICENSE.read_bytes(), 'notice'),) if case['id'].startswith('text-metrics') else ()
    # Include every helper available to this language profile; async/browser
    # helpers require different adapters and are not a valid synchronous baseline.
    available = set(HELPERS) - {'browser'}
    if not case.get('async'):
        available -= {'async', 'async-expose'}
    if all_helpers:
        with patch('JavaScript.modules.helper_closure', return_value=helper_closure(available)):
            return compile_modules(sources, entrypoint='app', source_map=source_map,
                                   async_enabled=case.get('async', False), notices=notices)
    return compile_modules(sources, entrypoint='app', source_map=source_map,
                           async_enabled=case.get('async', False), notices=notices)


def files_for(artifact, *, harness=False):
    files = {item.path:(item.data,item.role) for item in artifact.files}
    files['COMPILED-MANIFEST.json'] = (artifact.manifest_bytes,'metadata')
    if harness:
        files.update({'index.html':(PAGE.encode(),'measurement-harness'),
                      'measure-worker.mjs':(WORKER.encode(),'measurement-harness'),
                      'measure-runtime.mjs':((ROOT/'scripts/measure_compiler.mjs').read_bytes(),'measurement-harness')})
    return files


def sizes(artifact, files):
    buckets = {'executable-module':'generated_module_bytes', 'compatibility-helper':'helper_bytes',
               'source-map':'source_map_bytes', 'notice':'notice_bytes', 'metadata':'metadata_bytes',
               'measurement-harness':'measurement_harness_bytes'}
    result = {name:0 for name in buckets.values()}
    records, stream = [], io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for path, (data,role) in sorted(files.items()):
            result[buckets[role]] += len(data)
            compressed = gzip.compress(data, compresslevel=9, mtime=0)
            records.append({'path':path,'role':role,'size_bytes':len(data),
                            'sha256':hashlib.sha256(data).hexdigest(),'gzip_bytes':len(compressed)})
            member=tarfile.TarInfo(path)
            member.size=len(data);member.mode=0o644;member.mtime=0
            archive.addfile(member,io.BytesIO(data))
    compressed = gzip.compress(stream.getvalue(), compresslevel=9, mtime=0)
    result.update(input_source_bytes=sum(item['size'] for item in artifact.manifest['sources']),
                  interpreter_asset_bytes=0, complete_payload_bytes=sum(record['size_bytes'] for record in records),
                  gzip_file_transfer_bytes=sum(record['gzip_bytes'] for record in records),
                  canonical_tar_bytes=len(stream.getvalue()),gzip_tar_bytes=len(compressed),
                  gzip_tar_sha256=hashlib.sha256(compressed).hexdigest())
    return result,records,compressed


def write_files(root, files):
    root.mkdir(parents=True)
    for path,(data,_) in sorted(files.items()):
        destination=root/path
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(data)


def verify_results(entries, actual, expected):
    if len(actual)!=len(entries) or {item['id'] for item in actual}!={item['id'] for item in entries}:
        raise AssertionError('Missing or duplicate helper-conformance observations.')
    for item in actual:
        if item['result']!=expected[item['id']]:
            raise AssertionError((item['id'],'CPython',expected[item['id']],'compiled',item['result']))


def node_results(entries):
    script="import{execute}from "+json.dumps((ROOT/'scripts/measure_compiler.mjs').as_uri())+";let input='';for await(const chunk of process.stdin)input+=chunk;const entries=JSON.parse(input),results=[];for(const entry of entries)results.push({id:entry.id,...await execute(entry.url,entry.export)});console.log(JSON.stringify(results));"
    return json.loads(subprocess.check_output(['node','--input-type=module','--unhandled-rejections=strict','-e',script],
                      input=json.dumps(entries),text=True,encoding='utf-8',timeout=30))


def prepare_conformance(root):
    cases,_=parity.load_cases()
    entries,expected,records=[],{},[]
    for case in cases:
        reference=parity.reference(case)
        for all_helpers in [False,True]:
            identity=case['id']+('-all-profile' if all_helpers else '-required')
            artifact=compile_case(case,all_helpers=all_helpers)
            directory=root/'conformance'/identity
            write_files(directory,files_for(artifact))
            entries.append({'id':identity,'url':(directory/'app.mjs').as_uri(),'export':case.get('export')})
            expected[identity]=reference
            records.append({'id':identity,'case':case['id'],'helper_policy':'all-profile' if all_helpers else 'required',
                            'helpers':artifact.manifest['helpers'],'manifest_sha256':hashlib.sha256(artifact.manifest_bytes).hexdigest()})
    verify_results(entries,node_results(entries),expected)
    return entries,expected,records


def fixtures():
    cases,_=parity.load_cases()
    computation=next(case['source'] for case in cases if case['id']=='text-metrics-single-module')
    computation=computation[:computation.index('\nprint(metrics(')]
    app='from text_metrics import metrics\ndef main():\n    return metrics(""), metrics("A😀 é\\nline two"), metrics("a\\u00a0b")\n'
    return [dict(next(case for case in cases if case['id']=='numeric-and-unicode'),id='numeric-and-unicode'),
            {'id':'text-metrics','modules':[{'name':'app','source':app},{'name':'text_metrics','source':computation}],'export':'main'},
            {'id':'text-metrics-error','modules':[{'name':'app','source':'from text_metrics import metrics\ndef main():\n    return metrics(None)\n'},{'name':'text_metrics','source':computation}],'export':'main'}]


def prepare_measurements(root, repeats):
    rows=[]
    for case in fixtures():
        reference=parity.reference(case)
        # Warm the compiler and Unicode repr table before collecting build samples.
        for _,all_helpers,source_map in VARIANTS:
            compile_case(case,all_helpers=all_helpers,source_map=source_map)
        for variant,all_helpers,source_map in VARIANTS:
            samples=[];artifact=None
            for _ in range(repeats):
                before=time.perf_counter_ns()
                candidate=compile_case(case,all_helpers=all_helpers,source_map=source_map)
                samples.append(time.perf_counter_ns()-before)
                if artifact is not None and candidate!=artifact:
                    raise AssertionError('Compiler output changed between samples.')
                artifact=candidate
            files=files_for(artifact,harness=True)
            directory=root/'applications'/case['id']/variant
            write_files(directory,files)
            counts,records,compressed=sizes(artifact,files)
            available=set(HELPERS)-{'async','async-expose','browser'}
            row={'fixture':case['id'],'variant':variant,'language_profile':artifact.manifest['language_profile'],
                 'source_map':source_map,'helper_policy':'all-profile' if all_helpers else 'required',
                 'helpers':artifact.manifest['helpers'],'omitted_profile_helpers':sorted(available-set(artifact.manifest['helpers'])),
                 'sources':artifact.manifest['sources'],'manifest_sha256':hashlib.sha256(artifact.manifest_bytes).hexdigest(),
                 'sizes':counts,'files':records,'build_ns':samples,'median_build_ns':statistics.median(samples),'expected':reference}
            rows.append((row,directory,compressed))
    entries=[{'id':row['fixture']+'/'+row['variant'],'url':(directory/'app.mjs').as_uri(),'export':'main'} for row,directory,_ in rows]
    verify_results(entries,node_results(entries),{entry['id']:row['expected'] for entry,(row,_,_) in zip(entries,rows)})
    return rows


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def end_headers(self):
        # Every served file is immutable for the duration of one measurement run.
        self.send_header('Cache-Control','public, max-age=3600')
        super().end_headers()


class Server(ThreadingHTTPServer):
    request_queue_size=128


def worker_heap(browser,page):
    """Read the actual dedicated worker's V8 heap, independently of timings."""
    connection=browser.new_browser_cdp_session()
    session=None
    try:
        page_connection=page.context.new_cdp_session(page)
        try:
            context_id=page_connection.send('Target.getTargetInfo')['targetInfo']['browserContextId']
        finally:
            page_connection.detach()
        target=next(item for item in connection.send('Target.getTargets')['targetInfos']
                    if item['type']=='worker' and item['url']==page.workers[0].url
                    and item.get('browserContextId')==context_id)
        session=connection.send('Target.attachToTarget',{'targetId':target['targetId'],'flatten':False})['sessionId']
        responses={}
        def receive(event):
            message=json.loads(event['message'])
            if event['sessionId']==session and 'id' in message:
                responses[message['id']]=message
        connection.on('Target.receivedMessageFromTarget',receive)
        for identity,method in enumerate(['HeapProfiler.collectGarbage','Runtime.getHeapUsage'],1):
            connection.send('Target.sendMessageToTarget',{'sessionId':session,'message':json.dumps({'id':identity,'method':method})})
            deadline=time.monotonic()+10
            while identity not in responses and time.monotonic()<deadline:
                page.wait_for_timeout(5)
            response=responses.get(identity)
            if response is None or 'error' in response:
                raise RuntimeError(('Worker heap measurement failed',response))
        return responses[2]['result']
    finally:
        if session is not None:
            connection.send('Target.detachFromTarget',{'sessionId':session})
        connection.detach()


def observe_browser(root,rows,entries,expected,*,channel,repeats):
    from playwright.sync_api import sync_playwright
    server=Server(('127.0.0.1',0),partial(Handler,directory=str(root)))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    requests=[];errors=[]
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(channel=channel)
            def monitored_context():
                context=browser.new_context()
                context.on('request',lambda request:requests.append((request.method,request.url)))
                context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
                return context
            try:
                # Test the entire positive reference corpus in both helper modes.
                with monitored_context() as context:
                    page=context.new_page();page.set_default_timeout(30000)
                    page.goto(base+'/'+rows[0][1].relative_to(root).as_posix()+'/index.html')
                    page.evaluate('window.openWorker()')
                    browser_entries=[{**entry,'url':base+'/'+Path(url2pathname(urlsplit(entry['url']).path)).relative_to(root).as_posix()} for entry in entries]
                    actual=page.evaluate('entries=>window.request(entries)',browser_entries)
                    verify_results(entries,actual,expected)
                    page.evaluate('window.closeWorker()')
                for row,directory,_ in rows:
                    url=base+'/'+directory.relative_to(root).as_posix()+'/index.html'
                    cold=[];warm=[];memory=[]
                    for _ in range(repeats):
                        with monitored_context() as context:
                            page=context.new_page();page.set_default_timeout(30000);page.goto(url)
                            observation=page.evaluate('window.measureStartup()')
                            if observation.pop('result')!=row['expected']:
                                raise AssertionError('Cold browser computation differs from CPython.')
                            cold.append(observation)
                    with monitored_context() as context:
                        page=context.new_page();page.set_default_timeout(30000);page.goto(url)
                        first=page.evaluate('window.measureStartup()')
                        if first['result']!=row['expected']:
                            raise AssertionError('Warm-up computation differs from CPython.')
                        for _ in range(repeats):
                            observation=page.evaluate('window.measureStartup()')
                            if observation.pop('result')!=row['expected']:
                                raise AssertionError('Warm browser computation differs from CPython.')
                            warm.append(observation)
                    for _ in range(repeats):
                        with monitored_context() as context:
                            page=context.new_page();page.set_default_timeout(30000);page.goto(url)
                            page.evaluate('window.openWorker()')
                            before=worker_heap(browser,page)
                            observation=page.evaluate("window.request([{id:'fixture',url:new URL('./app.mjs',location.href).href,export:'main'}])")
                            if observation[0]['result']!=row['expected']:
                                raise AssertionError('Memory observation differs from CPython.')
                            after=worker_heap(browser,page)
                            memory.append({'baseline':before,'retained_module_and_result':after,
                                           'used_size_delta_bytes':after['usedSize']-before['usedSize']})
                    row['browser']={'cold_context_samples':cold,'warm_context_samples':warm,'memory_samples':memory,
                                    'median_cold_ms':statistics.median(item['wall_ms'] for item in cold),
                                    'median_warm_ms':statistics.median(item['wall_ms'] for item in warm)}
                if errors:
                    raise AssertionError(('Unhandled browser errors',errors))
                if not all(method=='GET' and url.startswith(base+'/') for method,url in requests):
                    raise AssertionError('Measurement fixtures made nonlocal/nonstatic requests.')
                return {'version':browser.version,'channel':channel,'playwright_version':version('playwright'),
                        'helper_conformance_cases':len(entries),'local_static_gets_only':True,
                        'requested_paths':sorted({url.removeprefix(base) for _,url in requests})}
            finally:
                browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def measure(output,*,repeats=5,browser=False,channel=None):
    if type(repeats) is not int or not 3<=repeats<=31:
        raise ValueError('Use 3–31 samples per condition.')
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new measurement output directory.')
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        entries,expected,conformance=prepare_conformance(root)
        rows=prepare_measurements(root,repeats)
        browser_info=observe_browser(root,rows,entries,expected,channel=channel,repeats=repeats) if browser else None
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        modified=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True))
        package_root=Path(JavaScript.__file__).parent
        compiler_sources={path.relative_to(package_root).as_posix():hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                          for path in sorted(package_root.rglob('*')) if path.is_file() and path.suffix in {'.py','.mjs'}}
        report={'kind':'python-javascript-compiler-measurements','schema_version':1,'suite':'compiler-footprint/1',
                'collected_at_utc':datetime.now(UTC).isoformat(),'repository_revision':revision,'working_tree_modified':modified,
                'compiler_version':version('Python-JavaScript'),'compiler_source_sha256':compiler_sources,
                'compiler_source_hash_policy':'Installed .py/.mjs files with canonical LF line endings',
                'python':platform.python_version(),
                'node':subprocess.check_output(['node','--version'],text=True).strip(),
                'host':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'processor':platform.processor(),'logical_cpu_count':os.cpu_count()},
                'browser':browser_info,'samples_per_condition':repeats,
                'measurement_scripts':{name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in ['measure_compiler.py','measure_compiler.mjs','compiler_conformance.py','compiler_conformance.mjs']},
                'corpus':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in [parity.FIXTURES/'compiler_contract.json',parity.FIXTURES/'compiler_parity.json',parity.LICENSE]},
                'compression':{'per_file':'gzip level 9, mtime 0; excludes HTTP headers','archive':'canonical USTAR then gzip level 9, mtime 0','zlib_version':zlib.ZLIB_RUNTIME_VERSION},
                'methods':{'build':'Warm imported compiler and Unicode repr table; compilation and manifest generation only; excludes filesystem writes and Python startup.',
                           'cold':'Fresh browser context and worker per sample; browser process and OS caches remain warm/uncontrolled. Timer covers worker creation, imports, initialization, one call and result message; excludes document navigation.',
                           'warm':'One context, explicit untimed warm-up, then a fresh worker for each observation. HTTP cache is shared; code-cache reuse is browser-controlled.',
                           'memory':'Separate fresh-context worker samples. CDP HeapProfiler.collectGarbage then Runtime.getHeapUsage before import and after retaining one module/result. Used/total V8 heap, embedder heap and backing storage are bytes; excludes process RSS, other processes, and native/code allocations not exposed by this API.',
                           'scope':'Synchronous compiled-module browser fixtures, including measurement harness, maps/notices/manifest. Browser-host SDK and pocket PWA shell are measured separately. All-profile baseline includes every helper valid for the same profile; no new feature is enabled.'},
                'helper_conformance':{'node':'pass','browser':'pass' if browser else 'not-run','observations':conformance},
                'applications':[row for row,_,_ in rows]}
        output.mkdir(parents=True)
        written=[]
        try:
            payloads={row['fixture']+'-'+row['variant']+'.tar.gz':compressed for row,_,compressed in rows}
            payloads['report.json']=encoded(report)
            for name,data in payloads.items():
                path=output/name
                with path.open('xb') as stream:
                    written.append(path)
                    stream.write(data)
        except BaseException:
            for path in reversed(written):path.unlink(missing_ok=True)
            try:output.rmdir()
            except OSError:pass
            raise
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--channel')
    args=parser.parse_args()
    try:
        report=measure(args.output,repeats=args.repeats,browser=args.browser,channel=args.channel)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({'report':str(args.output/'report.json'),'applications':len(report['applications']),
                      'helper_conformance':len(report['helper_conformance']['observations']),
                      'browser':None if report['browser'] is None else {key:report['browser'][key] for key in ['version','channel','playwright_version','helper_conformance_cases','local_static_gets_only']}}))


if __name__=='__main__':
    main()
