# PyPI releases

Each distribution has an independent PyPI trusted publisher using GitHub owner
`outside-labs`, repository `hidden_moves`, and workflow filename `release.yaml`.
The environment must match the selected package exactly:

| Distribution | Version | GitHub release tag | GitHub environment |
| --- | --- | --- | --- |
| `hidden-moves` | `0.1.0` | `v0.1.0` | `pypi` |
| `hidden-moves-mcp` | `0.1.0` | `v0.1.0-mcp` | `pypi-mcp` |
| `hidden-moves-openai` | `0.1.0` | `v0.1.0-openai` | `pypi-openai` |
| `hidden-moves-github-projects` | `0.1.0` | `v0.1.0-github-projects` | `pypi-github-projects` |

Tags start with `v`; adapter suffixes distinguish versions in the shared
repository. The core's original `v0.1.0` tag and uploaded files stay in place.
For later releases, update the selected package's metadata version and use that
version with the same suffix. Published PyPI files cannot be overwritten.

Prepare a focused PR and let the platform CI pass before its squash merge. A
published GitHub release at the verified main commit starts `release.yaml`:

```sh
gh release create v0.1.0-mcp --repo outside-labs/hidden_moves \
  --target VERIFIED_MAIN_COMMIT --title 'Hidden Moves MCP 0.1.0' \
  --notes-file RELEASE_NOTES.md
```

Replace the tag/title for the selected package. The workflow validates the exact
tag against its metadata, builds only that package's wheel and source archive,
checks metadata and artifact isolation, and tests the installed wheel. Test-only
provider wheels stay outside the upload directory. Publishing downloads only
the selected artifact and requests an OIDC token in its configured environment.

After publication, check both files on PyPI, compare their SHA256 digests with the
workflow artifact, and install the exact version in a fresh environment. Adapter
tests exercise local transports or offline function dispatch; they do not make
an external model request.

Backpack has its own repository, `outside-labs/backpack`, distribution
`backpack-store`, `release.yaml` workflow and `pypi` environment. Its independent
initial tag is `v0.1.0`; Python imports use `backpack_store`.

## Pending GitHub Projects publication

The GitHub Projects release route is prepared. Its initial upload is deferred
until a pending-publisher slot is available and the PyPI publisher is configured:

| Pending publisher field | Value |
| --- | --- |
| PyPI project name | `hidden-moves-github-projects` |
| Owner | `outside-labs` |
| Repository | `hidden_moves` |
| Workflow filename | `release.yaml` |
| Environment | `pypi-github-projects` |

Once this publisher is ready, publish the matching `v0.1.0-github-projects`
GitHub release at a verified main commit. The workflow first verifies the
ordinary client without optional integrations, then installs the published
adapters and `backpack-store` for the provider, write-profile and snapshot tests.
The ordinary client has no mandatory runtime dependencies.
