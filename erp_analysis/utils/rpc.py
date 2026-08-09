"""Shared helpers for whitelisted mobile API methods."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

import frappe


def clean_kwargs(kwargs: dict) -> dict:
	for key in ("cmd", "method", "csrf_token", "args", "kwargs"):
		kwargs.pop(key, None)
	return kwargs


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
