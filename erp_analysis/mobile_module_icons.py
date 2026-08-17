"""Default mobile module icon keys (Ionicons names for Expo / React Native)."""

from __future__ import annotations

# Logical keys only — mobile app maps these to Ionicons (e.g. @expo/vector-icons).
DEFAULT_MODULE_ICON_KEYS: dict[str, str] = {
	"sales": "bar-chart-outline",
	"receivables": "wallet-outline",
	"inventory": "cube-outline",
	"approvals": "checkmark-circle-outline",
	"catalogue": "book-outline",
	"push": "notifications-outline",
	"settings": "settings-outline",
	"executive": "briefcase-outline",
	"collection": "cash-outline",
	"sales_performance": "trending-up-outline",
	"sales_orders": "receipt-outline",
	"payables": "arrow-down-circle-outline",
	"purchase": "bag-outline",
	"customer_360": "people-outline",
	"profitability": "pie-chart-outline",
	"exceptions": "alert-circle-outline",
	"approval_analytics": "stats-chart-outline",
	"sales_overview": "flask-outline",
	# Future / optional module keys
	"inventory_health": "pulse-outline",
	"retail": "storefront-outline",
	"fashion": "shirt-outline",
	"pos_analysis": "phone-portrait-outline",
}


def get_module_icon_key(module_key: str, explicit: str | None = None) -> str | None:
	"""Profile row icon_key wins; otherwise use default map."""
	if explicit and str(explicit).strip():
		return str(explicit).strip()
	key = (module_key or "").strip().lower()
	return DEFAULT_MODULE_ICON_KEYS.get(key)
