"""Install exactly the locally built artifact, including its PyPI dependencies."""

from pathlib import Path
import subprocess
import sys
import tomllib


def main():
    suffix = "*.whl" if sys.argv[1:] == ["wheel"] else "*.tar.gz" if sys.argv[1:] == ["sdist"] else None
    if suffix is None:
        raise SystemExit("Usage: install_distribution.py wheel|sdist")
    artifacts = list(Path("dist").glob(suffix))
    if len(artifacts) != 1:
        raise SystemExit(f"Expected one {suffix} artifact, found {len(artifacts)}")
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    subprocess.run([sys.executable, "-m", "pip", "install", "--force-reinstall", str(artifacts[0])], check=True)
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    # New interpreter: imports must resolve from the installed artifact, not src.
    subprocess.run([
        sys.executable, "-c",
        "from importlib.metadata import version; import sys; import JavaScript, fetch_api, JSON; "
        "assert version('Python-JavaScript') == sys.argv[1]; "
        "assert 'site-packages' in JavaScript.__file__; "
        "assert JavaScript.fetch is fetch_api.fetch; "
        "print('Installed namespace:', JavaScript.__file__)",
        version,
    ], check=True)


if __name__ == "__main__":
    main()
