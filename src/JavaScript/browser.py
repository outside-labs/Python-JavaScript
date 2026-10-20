"""Build the explicit compiled browser profile and its local host assets."""

import ast
import hashlib
from importlib.resources import files

from .compiler import CompileError, Diagnostic, SourceSpan
from .emitter import CompiledArtifact, OutputFile, _json
from .modules import SourceModule, compile_modules


def compile_browser(sources: tuple[SourceModule, ...], *, entrypoint: str,
                    source_map: bool = True, notices: tuple[OutputFile, ...] = ()) -> CompiledArtifact:
    """Compile a verified allowlist with async main(), without executing it."""
    artifact = compile_modules(sources, entrypoint=entrypoint, source_map=source_map,
                               async_enabled=True, browser_enabled=True, notices=notices)
    entry = next(source for source in sources if source.name == entrypoint)
    tree = ast.parse(entry.data.decode('utf-8'))
    main = next((node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'main'), None)
    if main is None or len(main.args.defaults) != len(main.args.posonlyargs) + len(main.args.args):
        raise CompileError(Diagnostic('PJS110', 'Browser entry requires an async main() callable without required arguments.',
                                     SourceSpan(entry.filename, 1, 1, 1, 1), 'bind'))
    if any(len(source.filename) > 256 for source in sources):
        raise ValueError('Browser source identities must fit the host protocol filename limit of 256.')
    required = set()
    if 'print' in artifact.manifest['helpers']:
        required.add('output/1')
    for source in sources:
        if source.filename not in {record['path'] for record in artifact.manifest['sources']}:
            continue
        for node in ast.walk(ast.parse(source.data.decode('utf-8'))):
            if isinstance(node, ast.ImportFrom) and node.module == 'JavaScript.browser':
                for alias in node.names:
                    if alias.name in {'read_text', 'write_text'}:
                        required.add('dom-text/1')
                    elif alias.name in {'on_click', 'unsubscribe'}:
                        required.update({'dom-events/1', 'handles/1'})
                    elif alias.name == 'fetch_text':
                        required.add('fetch/1')
    output = list(artifact.files)
    names = ['browser-protocol.mjs', 'browser-host.mjs', 'browser-worker.mjs']
    for name in names:
        data = files('JavaScript').joinpath('_browser', name).read_bytes()
        if name == 'browser-worker.mjs':
            marker = b'/*CAPABILITIES*/[]'
            if data.count(marker) != 1:
                raise ValueError('Browser worker template identity mismatch.')
            data = data.replace(marker, _json(sorted(required)).encode())
        output.append(OutputFile(name, data, 'executable-module' if name == 'browser-worker.mjs' else 'compatibility-helper'))
    output = tuple(sorted(output, key=lambda item: item.path))
    manifest = artifact.manifest
    manifest['browser'] = {'protocol': 'pocket-python-host', 'version': 1, 'host': 'browser-host.mjs',
                           'worker': 'browser-worker.mjs', 'entrypoint_export': 'main', 'capabilities': sorted(required)}
    manifest['imports'].extend([{'from': 'browser-host.mjs', 'to': 'browser-protocol.mjs'},
                                {'from': 'browser-host.mjs', 'to': 'browser-worker.mjs'},
                                {'from': 'browser-worker.mjs', 'to': 'app.mjs'},
                                {'from': 'browser-worker.mjs', 'to': 'browser-protocol.mjs'}])
    manifest['imports'].sort(key=lambda item: (item['from'], item['to']))
    manifest['files'] = [{'path': item.path, 'size': len(item.data), 'sha256': hashlib.sha256(item.data).hexdigest(), 'role': item.role} for item in output]
    return CompiledArtifact(output, (_json(manifest) + '\n').encode())
