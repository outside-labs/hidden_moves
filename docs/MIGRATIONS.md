# Experimental migration notes

## Narrowed 0.1.0 framework

Before the first public package upload, the framework was narrowed to registration,
binding, schema description, discovery, selected catalogs, and their generic CLI.

Removed experimental imports: `hidden_moves.builtins`, `hidden_moves.command_set`,
`hidden_moves.kit`, `hidden_moves.notes`, and `hidden_moves.connectors`, together
with unused `logs`, `palette`, and `presets` prototypes. Their historical source is
available at commit `1e3aade2c7325166c96c490ded17058f3cefce61`.

Replace automatic `builtin_registry()` assembly with `Registry()` or `Moves()` and
explicit registration of application-owned functions. Replace specialized `text`,
`json`, and `cmd` commands with explicitly activated providers and
`moves call NAME --arguments JSON`, or invoke the ordinary library directly.

Both `hidden-moves`/`hm` and `hidden-moves-mcp` start with an empty registry. The
installed text example advertises `example.text.repeat` and target-bound
`example.text.prefix`. The latter can be inspected without a target; an application
host supplies a string target before selecting it for invocation. No automatic
credential or target injection was added.
