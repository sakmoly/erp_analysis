"""Map bottom-nav shell module keys to overview dashboard boards."""

from __future__ import annotations

# Bottom nav uses short keys (receivables); dashboards live on *_overview boards.
SHELL_MODULE_TO_DASHBOARD: dict[str, str] = {
	"receivables": "receivables_overview",
	"inventory": "inventory_overview",
	"collection": "collection_overview",
	"executive": "executive_overview",
}

DASHBOARD_TO_SHELL_MODULE: dict[str, str] = {
	v: k for k, v in SHELL_MODULE_TO_DASHBOARD.items()
}

# Extra aliases the mobile app may send when opening a tab or deep link.
DASHBOARD_BOARD_ALIASES: dict[str, str] = {
	**SHELL_MODULE_TO_DASHBOARD,
	"receivables_home": "receivables_overview",
	"inventory_home": "inventory_overview",
	"collection_home": "collection_overview",
	"executive_home": "executive_overview",
}


def resolve_dashboard_board_id(dashboard_id: str | None) -> str:
	"""Normalize mobile route/board keys to profile dashboard_id."""
	key = (dashboard_id or "home").strip()
	if not key:
		return "home"
	return DASHBOARD_BOARD_ALIASES.get(key, key)


def shell_module_dashboard(module_key: str | None) -> str | None:
	"""Overview dashboard for a bottom-nav shell module, if configured."""
	return SHELL_MODULE_TO_DASHBOARD.get((module_key or "").strip())
