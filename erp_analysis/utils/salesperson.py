"""Sales Person name normalization for mobile / dashboard variance."""

from __future__ import annotations

import difflib
import re
from functools import lru_cache

import frappe


def _normalize_key(name: str) -> str:
	return re.sub(r"\s+", " ", (name or "").strip().casefold())


@lru_cache(maxsize=1)
def _salesperson_lookup() -> dict[str, str]:
	lookup: dict[str, str] = {}
	for row in frappe.get_all("Sales Person", fields=["name", "sales_person_name"], limit=0):
		for value in (row.name, row.get("sales_person_name")):
			if value:
				lookup[_normalize_key(value)] = row.name
	return lookup


def resolve_salesperson_name(name: str | None) -> str | None:
	"""Map mobile/employee label to canonical Sales Person name."""
	if not name:
		return name

	lookup = _salesperson_lookup()
	key = _normalize_key(name)
	if key in lookup:
		return lookup[key]

	candidates = list({v for v in lookup.values()})
	close = difflib.get_close_matches(name.strip(), candidates, n=1, cutoff=0.82)
	if close:
		return close[0]

	# Extra help for common double-letter typos (Mohammmed → Mohammed).
	for candidate in candidates:
		if difflib.SequenceMatcher(None, key, _normalize_key(candidate)).ratio() >= 0.88:
			return candidate

	return name.strip()


def resolve_salesperson_names(names: list[str] | tuple[str, ...] | None) -> list[str]:
	if not names:
		return []
	seen: set[str] = set()
	resolved: list[str] = []
	for name in names:
		canonical = resolve_salesperson_name(name)
		if canonical and canonical not in seen:
			seen.add(canonical)
			resolved.append(canonical)
	return resolved


def clear_salesperson_lookup_cache():
	_salesperson_lookup.cache_clear()
