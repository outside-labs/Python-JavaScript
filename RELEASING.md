# Publishing Python-JavaScript

The distribution name is `Python-JavaScript`; the Python import is `JavaScript`.
Requires Python 3.14 or later.

## Trusted Publisher

The PyPI publisher must match these values exactly:

| Field | Value |
| --- | --- |
| PyPI project | `Python-JavaScript` |
| GitHub owner | `outside-labs` |
| Repository | `Python-JavaScript` |
| Workflow | `release.yaml` |
| Environment | `pypi` |

The GitHub environment is named `pypi`. Publishing uses OpenID Connect; no API
token belongs in the repository or workflow.

## Release

1. Merge the passing task PRs and confirm final main CI on all three platforms.
2. Confirm both declared companions are available on PyPI. Verify clean wheel
   and sdist installs and review the packaged file list.
3. Set the package version and matching changelog. Create and publish the GitHub
   release with tag `v<version>` targeting the verified main commit.
4. Monitor Release: tag/version validation, source/wheel build, strict metadata,
   installed-wheel and installed-sdist tests, then publication via `pypi`.
5. Verify a new environment can install `Python-JavaScript==<version>` from PyPI,
   run the examples/tests, and compare published SHA256 hashes with build artifacts.

Publishing a GitHub release triggers upload; a tag push alone does not. PyPI
versions are immutable. Repository visibility stays private; published artifacts
include package source. No open-source license has been selected for this release.
