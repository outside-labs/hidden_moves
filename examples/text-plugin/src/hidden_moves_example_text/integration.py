"""Definitions are constructed only when the provider is explicitly loaded."""

from hidden_moves import MoveAnnotations, MoveSpec

from .text import prefix_text, repeat_text


def provide_moves() -> tuple[MoveSpec, ...]:
	return (
		MoveSpec(
			name="repeat",
			namespace="example.text",
			func=repeat_text,
			annotations=MoveAnnotations(
				read_only=True, destructive=False, idempotent=True, external=False,
			),
			metadata={"examples": [{"value": "hello", "count": 2}]},
		),
		MoveSpec(
			name="prefix", namespace="example.text", func=prefix_text,
			bind_target=True, target_types=(str,),
			annotations=MoveAnnotations(
				read_only=True, destructive=False, idempotent=True, external=False,
			),
		),
	)
