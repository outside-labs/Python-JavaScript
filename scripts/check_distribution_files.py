"""Check exact publication contents and declared companion dependency metadata."""

from email.parser import BytesParser
from pathlib import Path
import sys
import tarfile
import tomllib
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    project_data = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    project = project_data['project']
    version = project['version']
    directory = Path(sys.argv[1]) if sys.argv[1:] else root / 'dist'
    prefix = f'python_javascript-{version}'
    modules = {p.relative_to(root / 'src').as_posix(): p for p in (root / 'src/JavaScript').rglob('*')
               if p.is_file() and (p.suffix in {'.py', '.mjs'} or p.name == 'py.typed')}
    wheels = list(directory.glob('*.whl'))
    sources = list(directory.glob('*.tar.gz'))
    assert len(wheels) == len(sources) == 1, 'Expected exactly one wheel and sdist'
    assert wheels[0].name == prefix + '-py3-none-any.whl'
    assert sources[0].name == prefix + '.tar.gz'
    info = prefix + '.dist-info/'
    with zipfile.ZipFile(wheels[0]) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        assert len(names) == len(set(names)), 'Duplicate wheel files'
        assert set(names) == set(modules) | {info + name for name in ['METADATA', 'WHEEL', 'RECORD']}, 'Unexpected wheel files'
        for name, path in modules.items():
            assert archive.read(name) == path.read_bytes(), name
        metadata = BytesParser().parsebytes(archive.read(info + 'METADATA'))
        assert metadata['Name'] == project['name'] and metadata['Version'] == version
        assert metadata['Requires-Python'] == project['requires-python']
        expected_dependencies = {'javascript-fetch-api>=0.2.0,<0.3.0', 'javascript-json>=0.1.0,<0.2.0'}
        assert set(metadata.get_all('Requires-Dist', [])) == expected_dependencies
    allowed = {'PKG-INFO', 'pyproject.toml', 'pyproject.toml.orig', 'README.md'}
    allowed |= {'src/' + name for name in modules}
    for pattern in project_data['tool']['uv']['build-backend']['source-include']:
        allowed |= {p.relative_to(root).as_posix() for p in root.glob(pattern) if p.is_file()}
    with tarfile.open(sources[0]) as archive:
        files = [item for item in archive.getmembers() if item.isfile()]
        names = [item.name for item in files]
        assert len(names) == len(set(names)), 'Duplicate sdist files'
        assert all(item.isdir() or item.isfile() for item in archive.getmembers()), 'Nonregular sdist entry'
        assert set(names) == {prefix + '/' + name for name in allowed}, 'Unexpected sdist files'
        for name in allowed - {'PKG-INFO', 'pyproject.toml', 'pyproject.toml.orig'}:
            assert archive.extractfile(prefix + '/' + name).read() == (root / name).read_bytes(), name
    print(f'Verified {len(modules)} package files and {len(allowed)} source-distribution files for {version}')


if __name__ == '__main__':
    main()
