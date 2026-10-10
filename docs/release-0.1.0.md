# Hidden Moves 0.1.0

This initial experimental release publishes only the `hidden-moves` core
distribution under the MIT license. Python 3.11 or newer is required. Click is
the only runtime dependency.

```sh
python -m pip install hidden-moves==0.1.0
hidden-moves --help
hm moves list --json
```

The core provides typed registration, schemas, per-object binding, explicit
provider discovery/activation, and a selected capability catalog. Registries
start empty. Applications own credentials, authorization, resources, and the
execution of registered functions. Inspection does not execute capabilities.

The API remains experimental throughout 0.x. Patch releases preserve the
documented 0.1 contract; minor versions may contain documented breaking
changes. See [compatibility](COMPATIBILITY.md) and [usage](USAGE.md).

MCP, function-tool and GitHub Projects adapters, the text provider example,
public hosting and plugin-directory submission are outside this upload. Their
source and existing integration tests remain in the repository. Separate
trusted publishers and releases are required before uploading adapter packages.

The release is selected by a published GitHub release with tag `v0.1.0`.
`.github/workflows/release.yaml` checks the tag against package metadata,
builds only the core wheel/source distribution, checks metadata strictly,
runs core tests against the installed wheel, and exercises both CLI aliases
and module execution. Upload uses PyPI trusted publishing in the `pypi`
environment. The existing CI separately checks the complete source package
family on Linux, macOS and Windows with Python 3.11/3.13.
