# Source candidate packaging

The package is an unpublished candidate, not permission to distribute it. The owner selected MIT for Engine Room code; LICENSE must be included.
Governance ratification and final publication approval remain owner decisions. Required
third-party licence texts remain intact. No provider credentials, runtime state, binaries,
models, Git history or development archive are included.

From an inspected committed checkout with Git and Python 3.12 or newer:

```text
python scripts/release/build_source.py --output <new-output-path.zip>
```

The builder reads committed blobs from HEAD (or an exact --revision commit), not working
files. New/uncommitted changes are deliberately absent. Its explicit allowlist includes
product source, tests, connector/runtime/controller files, selected guides and third-party
notices. It rejects symlinks/submodules and state-bearing paths within that scope. It does
not replace privacy or secret inspection of the selected bytes. Review the exact revision
and run the full source/history/package privacy checks before any push or publication.

SOURCE_MANIFEST.json records source revision, each file's SHA-256 and byte count. ZIP entry
order, timestamps and permissions are fixed for reproducibility. Existing output is never
overwritten. An external SHA-256 identifies the complete archive; a manifest inside an
archive is not an independent signature or proof of provenance.

Inspect the ZIP inventory and verify each extracted file against the manifest before launch.
Use a new isolated per-user source/state directory. Run python -m unittest discover -s tests -q
and Windows tests/test-model-planning.ps1 from the extracted directory. Packaging-specific
Git-fixture tests require Git. No test authorizes real provider login or paid allocation.
Actual clean-account installation, prerequisites, private controller/connector acceptance,
third-party notices, billing validation and final exact independent review remain release gates.
