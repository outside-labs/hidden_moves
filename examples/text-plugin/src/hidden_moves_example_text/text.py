"""Ordinary Python behavior, independent of the optional integration module."""


def repeat_text(value: str, count: int = 2, *, separator: str = " ") -> str:
	"""Repeat text with a separator, returning an empty string for zero repeats."""
	if count < 0:
		raise ValueError("count must be nonnegative.")
	return separator.join([value] * count)


def prefix_text(prefix: str, value: str) -> str:
	"""Prepend a configured prefix to text without changing either value."""
	return prefix + value
