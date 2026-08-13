"""Manual loader for PRINTECHS-B2B Mobile App Profile (opt-in — no user/profile links)."""

from __future__ import annotations

from typing import Optional


def ensure_profile(company: Optional[str] = None, update_existing: bool = False):
	"""bench --site <site> execute erp_analysis.scripts.load_printechs_b2b_profile.ensure_profile"""
	from erp_analysis.fixtures.printechs_b2b_profile import ensure_profile as _ensure

	return _ensure(company=company, update_existing=bool(update_existing))
