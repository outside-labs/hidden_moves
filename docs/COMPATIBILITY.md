# Experimental compatibility policy

Hidden Moves and its provider contract remain experimental in the 0.x series.
Documented breaking changes may occur between minor versions; migration notes
identify removed imports, commands, and changed contracts. Patch releases within
one minor series preserve documented behavior; optional descriptive fields may be
added without changing existing meanings.

The supported public surfaces are the exported core registration/binding types,
the `hidden_moves.moves` entry-point factory contract, neutral definitions/schemas,
the selected catalog, and each adapter's documented exports. Internal helpers are
not compatibility promises. Providers construct definitions explicitly; activation
and target configuration remain application choices.

Adapters declare the tested `hidden-moves>=0.1,<0.2` range. A new core minor needs
deliberate adapter testing and a corresponding compatibility-range change. Adapter
release numbers need not remain identical to core release numbers.

## Neutral definition data

`MoveDefinition.to_dict()` and `Moves.explain()` produce the documented 0.1 neutral
definition view. Existing field meanings and schema conversion remain compatible
within 0.1 patch releases. A breaking serialized-shape change requires a minor
release and migration notes; consumers must accept additive optional fields.

The view has no embedded durable format version. Applications persisting it must
record the core minor-series identity alongside their own envelope/schema version,
and explicitly migrate that envelope when adopting an incompatible core minor.
Definition data is descriptive: loading it never reconstructs callable code.
Provider code and registered ordinary functions remain the executable authority.

## Evidence and release gates

CI builds wheels from sdists, inspects their contents and metadata, installs the
actual wheels, and exercises providers, commands, adapters, and transport on Linux,
macOS, and Windows with Python 3.11/3.13. This is an experimental support baseline,
not a promise of a stable 1.x API. Broader model/schema support needs its own tests.

Package upload and public service deployment are separate publication decisions.
One successful consumer does not remove the experimental label. Stabilization
requires Projects and Backpack consumer evidence, public/provider boundary tests,
supported-platform checks, and a deliberate compatibility commitment.
