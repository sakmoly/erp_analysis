"""Shared helpers for whitelisted mobile API methods."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

import frappe


_RPC_NOISE = frozenset({"cmd", "method", "csrf_token", "args"})


def clean_kwargs(kwargs: dict) -> dict:
	for key in _RPC_NOISE | {"kwargs"}:
		kwargs.pop(key, None)
	return kwargs


def expand_rpc_kwargs(kwargs: dict | None = None) -> dict:
	"""Merge ``form_dict`` / JSON body into kwargs and strip Frappe RPC noise (avoids 417 from missing params)."""
	out = dict(kwargs or {})
	clean_kwargs(out)
	for key, value in (frappe.form_dict or {}).items():
		if key in _RPC_NOISE:
			continue
		if key not in out or out.get(key) in (None, ""):
			out[key] = value
	for nested_key in ("data", "kwargs"):
		raw = out.get(nested_key) or (frappe.form_dict or {}).get(nested_key)
		if not raw:
			continue
		try:
			parsed = frappe.parse_json(raw) if isinstance(raw, str) else raw
		except Exception:
			continue
		if not isinstance(parsed, dict):
			continue
		for key, value in parsed.items():
			if key in _RPC_NOISE:
				continue
			if key not in out or out.get(key) in (None, ""):
				out[key] = value
		out.pop(nested_key, None)
	return out


def get_arg(name: str, default=None, overrides: Optional[dict] = None):
	if overrides is not None and name in overrides:
		value = overrides.get(name)
		return value if value is not None and value != "" else default
	value = frappe.form_dict.get(name)
	return value if value is not None and value != "" else default


def get_date_arg(*names: str, default=None):
	"""Read a date param from snake_case or camelCase aliases."""
	for name in names:
		value = get_arg(name)
		if value is not None and value != "":
			return value
	return default


def to_int(value, default=0) -> int:
	try:
		return int(value)
	except Exception:
		return default


def to_bool(value, default: bool = False) -> bool:
	if value is None or value == "":
		return default
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return bool(value)
	text = str(value).strip().lower()
	if text in ("0", "false", "no", "off"):
		return False
	if text in ("1", "true", "yes", "on"):
		return True
	return default


def to_date(value: Optional[str]) -> date:
	try:
		return frappe.utils.getdate(value) if value else frappe.utils.getdate(date.today())
	except Exception:
		return frappe.utils.getdate(date.today())


def absolute_file_url(path: str) -> str:
	if not path:
		return ""
	if path.startswith(("http://", "https://")):
		return path
	base = frappe.utils.get_url()
	if path.startswith("/files/"):
		return f"{base}{path}"
	return f"{base}/files/{path}"


def resolve_customer_id(value: Any) -> Optional[str]:
	"""Accept customer id string, JSON string, or mobile `{ id, customer_name }` object."""
	if value is None or value == "":
		return None
	if isinstance(value, dict):
		return (value.get("id") or value.get("name") or "").strip() or None
	if isinstance(value, str):
		text = value.strip()
		if text.startswith("{"):
			try:
				parsed = json.loads(text)
				if isinstance(parsed, dict):
					return resolve_customer_id(parsed)
			except Exception:
				pass
		return text or None
	return str(value).strip() or None
