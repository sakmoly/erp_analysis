"""Collection dashboard breakdowns and attention lists (Payment Entry actuals)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, List, Optional

import frappe
from frappe.utils import fmt_money, get_first_day, getdate, nowdate

from erp_analysis.permissions.access_profile import resolve_territory_scope, si_territory_sql
from erp_analysis.services.kpi.collection import get_collection_period_kpis

COLLECTION_AMOUNT_FORMAT = "currency_integer"
COLLECTION_AMOUNT_BASIS = "gl_net"  # General Ledger net (debit − credit) on MoP account


def format_collection_amount(amount: Any, currency: str = "SAR") -> str:
	"""Full SAR amount for mobile (no K/M suffix, no decimals)."""
	return fmt_money(float(amount or 0), currency=currency or "SAR", precision=0)


def _period_bounds(
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
) -> tuple[date, date]:
	end = getdate(to_date or nowdate())
	start = getdate(from_date) if from_date else get_first_day(end)
	return start, end


def _company_sql(company: Optional[str], alias: str = "pe") -> tuple[str, list[Any]]:
	if not company:
		return "", []
	return f" AND {alias}.company = %s", [company]


def _customer_territory_sql(
	territories: Optional[List[str]],
	alias: str = "c",
) -> tuple[str, list[Any]]:
	return si_territory_sql(territories, field=f"{alias}.territory")


def _assign_collection_branch_territory(
	customer_territory: Optional[str],
	mode_of_payment: Optional[str],
	known_territories: set[str],
) -> str:
	"""Branch bucket: MoP suffix territory wins (matches GL cash/cheque accounts)."""
	mop_branch = _mode_of_payment_territory_suffix(mode_of_payment)
	if mop_branch and mop_branch in known_territories:
		return mop_branch
	return (customer_territory or "").strip() or "Unassigned"


def _fetch_scoped_receive_payments(
	company: Optional[str],
	start: date,
	end: date,
	territories: Optional[List[str]] = None,
	*,
	customer_territory: Optional[str] = None,
) -> list[dict[str, Any]]:
	"""Submitted Receive PE rows in profile scope (paid amount, not allocated)."""
	company_sql, company_params = _company_sql(company)
	terr_sql, terr_params = _customer_territory_sql(territories)
	extra_sql = ""
	extra_params: list[Any] = []
	if customer_territory:
		extra_sql = " AND COALESCE(c.territory, 'Unassigned') = %s"
		extra_params.append(customer_territory)

	return frappe.db.sql(
		f"""
		SELECT
			pe.name AS payment_entry,
			pe.party AS customer,
			COALESCE(c.customer_name, pe.party) AS customer_name,
			COALESCE(c.territory, 'Unassigned') AS territory,
			COALESCE(pe.base_paid_amount, pe.paid_amount, 0) AS paid_amount,
			pe.mode_of_payment
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabCustomer` c ON c.name = pe.party AND pe.party_type = 'Customer'
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		  {extra_sql}
		""",
		tuple([start, end, *company_params, *terr_params, *extra_params]),
		as_dict=True,
	)


def _mop_default_account_map(company: Optional[str]) -> dict[str, str]:
	if not company:
		return {}
	cache_key = f"collection_mop_accounts:{company}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return dict(cached)
	rows = frappe.db.sql(
		"""
		SELECT parent AS mode_of_payment, default_account
		FROM `tabMode of Payment Account`
		WHERE company = %s AND default_account IS NOT NULL AND default_account != ''
		""",
		(company,),
		as_dict=True,
	)
	out = {str(r.mode_of_payment): str(r.default_account) for r in rows}
	frappe.cache().set_value(cache_key, out, expires_in_sec=3600)
	return out


def _gl_net_for_accounts(
	company: Optional[str],
	start: date,
	end: date,
	accounts: list[str],
) -> dict[str, dict[str, float]]:
	if not company or not accounts:
		return {}
	placeholders = ", ".join(["%s"] * len(accounts))
	rows = frappe.db.sql(
		f"""
		SELECT
			gle.account,
			COALESCE(SUM(gle.debit), 0) AS debit,
			COALESCE(SUM(gle.credit), 0) AS credit
		FROM `tabGL Entry` gle
		WHERE gle.company = %s
		  AND gle.is_cancelled = 0
		  AND gle.posting_date BETWEEN %s AND %s
		  AND gle.account IN ({placeholders})
		GROUP BY gle.account
		""",
		tuple([company, start, end, *accounts]),
		as_dict=True,
	)
	out: dict[str, dict[str, float]] = {}
	for row in rows:
		debit = float(row.debit or 0)
		credit = float(row.credit or 0)
		out[row.account] = {
			"debit": round(debit, 2),
			"credit": round(credit, 2),
			"net": round(debit - credit, 2),
		}
	for acc in accounts:
		out.setdefault(acc, {"debit": 0.0, "credit": 0.0, "net": 0.0})
	return out


def _gl_net_for_mode_of_payment(
	company: Optional[str],
	mode_of_payment: str,
	start: date,
	end: date,
	*,
	account_map: Optional[dict[str, str]] = None,
	gl_cache: Optional[dict[str, dict[str, float]]] = None,
) -> dict[str, float]:
	account_map = account_map or _mop_default_account_map(company)
	account = account_map.get(mode_of_payment)
	if not account:
		return {"debit": 0.0, "credit": 0.0, "net": 0.0, "gl_account": None}
	if gl_cache is None:
		gl_cache = _gl_net_for_accounts(company, start, end, [account])
	stats = gl_cache.get(account) or {"debit": 0.0, "credit": 0.0, "net": 0.0}
	return {**stats, "gl_account": account}


def _summarize_modes_gl_net(
	company: Optional[str],
	start: date,
	end: date,
	mode_payment_counts: dict[str, int],
	*,
	currency: str = "SAR",
	mode_pe_paid: Optional[dict[str, float]] = None,
	drill_territory: Optional[str] = None,
	known_territories: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
	"""Branch MoP totals = GL net (debit − credit); shared MoPs use PE paid in drill scope."""
	if not mode_payment_counts:
		return []
	known_territories = known_territories or set()
	account_map = _mop_default_account_map(company)
	accounts = list({account_map[m] for m in mode_payment_counts if m in account_map})
	gl_cache = _gl_net_for_accounts(company, start, end, accounts)
	rows: list[dict[str, Any]] = []
	for mop, payment_count in mode_payment_counts.items():
		mop_branch = _mode_of_payment_territory_suffix(mop)
		use_gl = bool(mop_branch and mop_branch in known_territories)
		if drill_territory and not use_gl:
			net = round(float((mode_pe_paid or {}).get(mop, 0)), 2)
			basis = "payment_entry_paid"
			row = {
				"mode_of_payment": mop,
				"gl_account": account_map.get(mop),
				"debit": net,
				"credit": 0.0,
				"collected": net,
				"net": net,
				"amount_basis": basis,
				"collected_display": format_collection_amount(net, currency),
				"payment_count": int(payment_count),
			}
		else:
			gl = _gl_net_for_mode_of_payment(
				company, mop, start, end, account_map=account_map, gl_cache=gl_cache
			)
			net = float(gl.get("net") or 0)
			row = {
				"mode_of_payment": mop,
				"gl_account": gl.get("gl_account"),
				"debit": gl.get("debit", 0.0),
				"credit": gl.get("credit", 0.0),
				"collected": net,
				"net": net,
				"amount_basis": COLLECTION_AMOUNT_BASIS,
				"collected_display": format_collection_amount(net, currency),
				"payment_count": int(payment_count),
			}
		rows.append(row)
	rows.sort(key=lambda r: float(r.get("net") or 0), reverse=True)
	return rows


def _territory_branch_gl_net(
	company: Optional[str],
	start: date,
	end: date,
	branch: str,
	known_territories: set[str],
) -> float:
	"""Sum GL net for MoP default accounts whose MoP suffix is this branch."""
	if branch not in known_territories:
		return 0.0
	account_map = _mop_default_account_map(company)
	accounts: set[str] = set()
	for mop, account in account_map.items():
		if _mode_of_payment_territory_suffix(mop) == branch:
			accounts.add(account)
	if not accounts:
		return 0.0
	gl_cache = _gl_net_for_accounts(company, start, end, list(accounts))
	return round(sum(float(gl_cache[a]["net"]) for a in accounts), 2)


def _aggregate_territory_drill_payments(
	rows: list[dict[str, Any]],
	*,
	drill_territory: str,
	known_territories: set[str],
	company: Optional[str],
	start: date,
	end: date,
	currency: str = "SAR",
) -> tuple[float, int, list[dict[str, Any]]]:
	"""Full drill totals (GL net by MoP; payment_count from matching PE rows)."""
	count = 0
	mode_payment_counts: dict[str, int] = {}
	mode_pe_paid: dict[str, float] = {}
	for row in rows:
		ok, _ = _payment_matches_territory_drill(
			customer_territory=row.territory,
			mode_of_payment=row.mode_of_payment,
			drill_territory=drill_territory,
			known_territories=known_territories,
		)
		if not ok:
			continue
		count += 1
		mop = (row.mode_of_payment or "").strip() or "Unassigned"
		mode_payment_counts[mop] = mode_payment_counts.get(mop, 0) + 1
		mode_pe_paid[mop] = mode_pe_paid.get(mop, 0.0) + float(row.paid_amount or 0)
	mop_rows = _summarize_modes_gl_net(
		company,
		start,
		end,
		mode_payment_counts,
		currency=currency,
		mode_pe_paid=mode_pe_paid,
		drill_territory=drill_territory,
		known_territories=known_territories,
	)
	total = round(sum(float(r["net"]) for r in mop_rows), 2)
	return total, count, mop_rows


def get_collection_by_territory(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	start, end = _period_bounds(from_date, to_date)
	known = _known_branch_territory_names(company)
	rows = _fetch_scoped_receive_payments(company, start, end, territories)
	buckets: dict[str, dict[str, Any]] = {}
	for row in rows:
		key = _assign_collection_branch_territory(row.territory, row.mode_of_payment, known)
		bucket = buckets.setdefault(key, {"territory": key, "collected": 0.0, "payment_count": 0})
		bucket["payment_count"] += 1
		if key in known:
			continue
		bucket["collected"] += float(row.paid_amount or 0)

	for branch in known:
		net = _territory_branch_gl_net(company, start, end, branch, known)
		if net == 0 and branch not in buckets:
			continue
		bucket = buckets.setdefault(
			branch, {"territory": branch, "collected": 0.0, "payment_count": 0}
		)
		bucket["collected"] = net
		bucket["amount_basis"] = COLLECTION_AMOUNT_BASIS

	out = sorted(buckets.values(), key=lambda r: float(r["collected"]), reverse=True)[: int(limit)]
	for row in out:
		row["collected"] = round(float(row["collected"]), 2)
		row["payment_count"] = int(row["payment_count"])
		row.setdefault("amount_basis", COLLECTION_AMOUNT_BASIS if row["territory"] in known else "payment_entry_paid")
	return out


def get_collection_by_mode_of_payment(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	limit: int = 50,
	territories: Optional[List[str]] = None,
	territory: Optional[str] = None,
) -> list[dict[str, Any]]:
	"""Totals by Mode of Payment (aligns with GL cash/cheque accounts)."""
	start, end = _period_bounds(from_date, to_date)
	known = _known_branch_territory_names(company)
	rows = _fetch_scoped_receive_payments(company, start, end, territories)
	if territory:
		rows = [
			row
			for row in rows
			if _payment_matches_territory_drill(
				customer_territory=row.territory,
				mode_of_payment=row.mode_of_payment,
				drill_territory=territory,
				known_territories=known,
			)[0]
		]
	mode_payment_counts: dict[str, int] = {}
	mode_pe_paid: dict[str, float] = {}
	for row in rows:
		mop = (row.mode_of_payment or "").strip() or "Unassigned"
		mode_payment_counts[mop] = mode_payment_counts.get(mop, 0) + 1
		mode_pe_paid[mop] = mode_pe_paid.get(mop, 0.0) + float(row.paid_amount or 0)

	currency = frappe.db.get_value("Company", company, "default_currency") if company else "SAR"
	out = _summarize_modes_gl_net(
		company,
		start,
		end,
		mode_payment_counts,
		currency=currency,
		mode_pe_paid=mode_pe_paid,
		drill_territory=territory,
		known_territories=known,
	)
	return out[: int(limit)]


def get_collection_by_customer(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	start, end = _period_bounds(from_date, to_date)
	rows = _fetch_scoped_receive_payments(company, start, end, territories)
	if territory:
		known = _known_branch_territory_names(company)
		rows = [
			row
			for row in rows
			if _payment_matches_territory_drill(
				customer_territory=row.territory,
				mode_of_payment=row.mode_of_payment,
				drill_territory=territory,
				known_territories=known,
			)[0]
		]

	buckets: dict[str, dict[str, Any]] = {}
	for row in rows:
		key = row.customer or ""
		bucket = buckets.setdefault(
			key,
			{
				"customer": row.customer,
				"customer_name": row.customer_name,
				"territory": row.territory or "",
				"collected": 0.0,
				"payment_count": 0,
			},
		)
		bucket["collected"] += float(row.paid_amount or 0)
		bucket["payment_count"] += 1

	out = sorted(buckets.values(), key=lambda r: float(r["collected"]), reverse=True)[: int(limit)]
	for row in out:
		row["collected"] = round(float(row["collected"]), 2)
		row["payment_count"] = int(row["payment_count"])
	return out


def get_collection_dashboard_payload(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	territory: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	start, end = _period_bounds(from_date, to_date)
	if territories is None:
		territories = resolve_territory_scope(
			requested=territory, company=company, purpose="view", module="sales"
		)
	currency = frappe.db.get_value("Company", company, "default_currency") if company else "SAR"
	kpis = get_collection_period_kpis(
		company=company, as_of=end, territory=territory, territories=territories
	)
	return {
		"meta": {"amount_format": COLLECTION_AMOUNT_FORMAT, "currency": currency},
		"kpis": {
			**kpis,
			"amount_format": COLLECTION_AMOUNT_FORMAT,
			"today_display": format_collection_amount(kpis.get("today"), currency),
			"mtd_display": format_collection_amount(kpis.get("mtd"), currency),
			"ytd_display": format_collection_amount(kpis.get("ytd"), currency),
		},
		"period": {"from_date": str(start), "to_date": str(end)},
		"by_territory": get_collection_by_territory(
			company=company, from_date=start, to_date=end, limit=limit, territories=territories
		),
		"by_customer": get_collection_by_customer(
			company=company,
			from_date=start,
			to_date=end,
			territory=territory,
			limit=limit,
			territories=territories,
		),
		"by_mode_of_payment": get_collection_by_mode_of_payment(
			company=company,
			from_date=start,
			to_date=end,
			territory=territory,
			limit=50,
			territories=territories,
		),
	}


def get_overdue_customers(
	company: Optional[str] = None,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	terr_sql, terr_params = si_territory_sql(territories, field="si.territory")

	rows = frappe.db.sql(
		f"""
		SELECT
			si.customer AS customer,
			COALESCE(c.customer_name, si.customer) AS customer_name,
			COALESCE(c.territory, '') AS territory,
			COALESCE(SUM(si.outstanding_amount), 0) AS total_outstanding,
			COALESCE(SUM(
				CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount ELSE 0 END
			), 0) AS overdue,
			MIN(CASE WHEN si.due_date < CURDATE() THEN si.due_date END) AS oldest_due_date
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE si.docstatus = 1
		  AND si.outstanding_amount > 0
		  AND si.company = %s
		  {terr_sql}
		GROUP BY si.customer, c.customer_name, c.territory
		HAVING overdue > 0
		ORDER BY overdue DESC
		LIMIT %s
		""",
		(company, *terr_params, int(limit)),
		as_dict=True,
	)

	return [
		{
			"customer": row.customer,
			"customer_name": row.customer_name,
			"territory": row.territory,
			"overdue": round(float(row.overdue or 0), 2),
			"total_outstanding": round(float(row.total_outstanding or 0), 2),
			"oldest_due_date": str(row.oldest_due_date) if row.oldest_due_date else None,
		}
		for row in rows
	]


def _advances_territory_scope(
	company: Optional[str],
	*,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> Optional[List[str]]:
	"""Same territory scope as receivables / collection attention."""
	if territories is not None:
		return territories
	return resolve_territory_scope(
		requested=territory,
		company=company,
		purpose="view",
		module="receivables",
	)


def _advances_customer_join_and_terr_sql(
	territories: Optional[List[str]],
) -> tuple[str, str, list[Any]]:
	if not territories:
		return "", "", []
	party_join = """
		INNER JOIN `tabCustomer` c
			ON c.name = pe.party AND pe.party_type = 'Customer'
	"""
	terr_sql, terr_params = _customer_territory_sql(territories)
	return party_join, terr_sql, terr_params


def get_customer_advances_by_customer(
	company: Optional[str] = None,
	min_unallocated: float = 0.01,
	limit: int = 50,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	scope = _advances_territory_scope(company, territory=territory, territories=territories)
	party_join, terr_sql, terr_params = _advances_customer_join_and_terr_sql(scope)
	company_sql, company_params = _company_sql(company)

	rows = frappe.db.sql(
		f"""
		SELECT
			pe.party AS customer,
			COALESCE(c.customer_name, pe.party) AS customer_name,
			COALESCE(c.territory, '') AS territory,
			COALESCE(SUM(pe.unallocated_amount), 0) AS advance_amount,
			COUNT(pe.name) AS payment_count
		FROM `tabPayment Entry` pe
		{party_join or "LEFT JOIN `tabCustomer` c ON c.name = pe.party AND pe.party_type = 'Customer'"}
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  {company_sql}
		  AND pe.unallocated_amount >= %s
		  {terr_sql}
		GROUP BY pe.party, c.customer_name, c.territory
		HAVING advance_amount > 0
		ORDER BY advance_amount DESC
		LIMIT %s
		""",
		tuple([*company_params, float(min_unallocated), *terr_params, int(limit)]),
		as_dict=True,
	)

	return [
		{
			"customer": row.customer,
			"customer_name": row.customer_name,
			"territory": row.territory,
			"advance_amount": round(float(row.advance_amount or 0), 2),
			"payment_count": int(row.payment_count or 0),
		}
		for row in rows
	]


def get_customer_advances_summary(
	company: Optional[str] = None,
	min_unallocated: float = 0.01,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return {"total_advance": 0, "customer_count": 0, "payment_count": 0}

	scope = _advances_territory_scope(company, territory=territory, territories=territories)
	party_join, terr_sql, terr_params = _advances_customer_join_and_terr_sql(scope)
	company_sql, company_params = _company_sql(company)
	min_val = float(min_unallocated)

	row = frappe.db.sql(
		f"""
		SELECT
			COALESCE(SUM(pe.unallocated_amount), 0) AS total_advance,
			COUNT(DISTINCT pe.party) AS customer_count,
			COUNT(pe.name) AS payment_count
		FROM `tabPayment Entry` pe
		{party_join}
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  {company_sql}
		  AND pe.unallocated_amount >= %s
		  {terr_sql}
		""",
		tuple([*company_params, min_val, *terr_params]),
		as_dict=True,
	)
	data = row[0] if row else {}
	return {
		"total_advance": round(float(data.get("total_advance") or 0), 2),
		"customer_count": int(data.get("customer_count") or 0),
		"payment_count": int(data.get("payment_count") or 0),
	}


def get_customer_advances_chart_series(
	company: Optional[str] = None,
	limit: int = 10,
	territory: Optional[str] = None,
	territories: Optional[List[str]] = None,
	min_unallocated: float = 0.01,
) -> list[dict[str, Any]]:
	rows = get_customer_advances_by_customer(
		company=company,
		min_unallocated=min_unallocated,
		limit=limit,
		territory=territory,
		territories=territories,
	)
	series: list[dict[str, Any]] = []
	for row in rows:
		label = row.get("customer_name") or row.get("customer") or "Unknown"
		amount = float(row.get("advance_amount") or 0)
		point: dict[str, Any] = {
			"label": label,
			"value": round(amount, 2),
			"dimension_value": row.get("customer") or label,
			"customer": row.get("customer"),
			"advance_amount": round(amount, 2),
		}
		if row.get("territory"):
			point["territory"] = row["territory"]
		if row.get("payment_count"):
			point["payment_count"] = int(row["payment_count"])
		series.append(point)
	return series


def get_unallocated_payments(
	company: Optional[str] = None,
	min_unallocated: float = 100.0,
	limit: int = 20,
	territories: Optional[List[str]] = None,
	party: Optional[str] = None,
) -> list[dict[str, Any]]:
	company = company or frappe.defaults.get_user_default("Company")
	if not company:
		return []

	party_join = ""
	terr_sql = ""
	terr_params: list[Any] = []
	party_filter_sql = ""
	party_filter_params: list[Any] = []
	if party:
		party_filter_sql = " AND pe.party = %s"
		party_filter_params.append(party)

	if territories:
		party_join = """
			INNER JOIN `tabCustomer` c
				ON c.name = pe.party AND pe.party_type = 'Customer'
		"""
		terr_sql, terr_params = _customer_territory_sql(territories)

	rows = frappe.db.sql(
		f"""
		SELECT
			pe.name AS payment_entry,
			pe.party,
			pe.posting_date,
			COALESCE(pe.base_paid_amount, 0) AS paid_amount,
			COALESCE(pe.unallocated_amount, 0) AS unallocated_amount
		FROM `tabPayment Entry` pe
		{party_join}
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.company = %s
		  AND pe.unallocated_amount >= %s
		  {party_filter_sql}
		  {terr_sql}
		ORDER BY pe.unallocated_amount DESC
		LIMIT %s
		""",
		(company, float(min_unallocated), *party_filter_params, *terr_params, int(limit)),
		as_dict=True,
	)

	return [
		{
			"payment_entry": row.payment_entry,
			"party": row.party,
			"posting_date": str(row.posting_date),
			"paid_amount": round(float(row.paid_amount or 0), 2),
			"unallocated_amount": round(float(row.unallocated_amount or 0), 2),
		}
		for row in rows
	]


_BREAKDOWN_TYPES = frozenset({"territory", "salesperson", "customer"})

_TERRITORY_DRILL_FILTER_NOTE = (
	"Territory drill includes customer territory or mode-of-payment branch suffix; "
	"receipts tied to another branch MoP (e.g. Cash Collection - Dammam) are excluded."
)


def _known_branch_territory_names(company: Optional[str] = None) -> set[str]:
	cache_key = f"collection_branch_territories:{company or ''}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return set(cached)
	names: set[str] = set()
	if frappe.db.table_exists("Territory"):
		rows = frappe.get_all("Territory", pluck="name", filters={"is_group": 0})
		names.update(str(n).strip() for n in rows if str(n).strip())
	if company:
		customer_terrs = frappe.db.sql(
			"""
			SELECT DISTINCT territory FROM `tabCustomer`
			WHERE territory IS NOT NULL AND territory != ''
			  AND (disabled = 0 OR disabled IS NULL)
			""",
			as_dict=True,
		)
		names.update(str(r.territory).strip() for r in customer_terrs if r.territory)
	frappe.cache().set_value(cache_key, list(names), expires_in_sec=3600)
	return names


def _mode_of_payment_territory_suffix(mode_of_payment: Optional[str]) -> Optional[str]:
	text = (mode_of_payment or "").strip()
	if not text or " - " not in text:
		return None
	return text.rsplit(" - ", 1)[-1].strip() or None


def _payment_matches_territory_drill(
	*,
	customer_territory: Optional[str],
	mode_of_payment: Optional[str],
	drill_territory: str,
	known_territories: set[str],
) -> tuple[bool, Optional[str]]:
	"""Territory drill: customer territory OR MoP branch suffix; hide other-branch MoP."""
	bid = (drill_territory or "").strip()
	if not bid:
		return False, None
	cust = (customer_territory or "").strip() or "Unassigned"
	mop = (mode_of_payment or "").strip()
	mop_branch = _mode_of_payment_territory_suffix(mop)

	if mop_branch and mop_branch in known_territories and mop_branch != bid:
		return False, "other_branch_mop"

	if cust == bid:
		return True, None
	if mop_branch == bid:
		return True, None
	if mop.endswith(f" - {bid}"):
		return True, None
	return False, None


def _resolve_collection_period(
	from_date: Optional[str],
	to_date: Optional[str],
	period: Optional[str],
) -> tuple[date, date, str]:
	if from_date and to_date:
		start, end = _period_bounds(from_date, to_date)
		return start, end, (period or "custom").strip().lower()
	from erp_analysis.services.sales_period import resolve_period_dates

	start, end, period_key = resolve_period_dates(from_date, to_date, period=period or "ytd")
	return start, end, period_key


def _breakdown_filter_sql(
	breakdown_type: str,
	breakdown_id: str,
	*,
	company_params: list[Any],
) -> tuple[str, list[Any], str]:
	"""Return SQL fragment, extra params, and human label for breakdown drill."""
	btype = (breakdown_type or "").strip().lower()
	bid = (breakdown_id or "").strip()
	if btype not in _BREAKDOWN_TYPES:
		frappe.throw(f"Unsupported breakdown_type: {breakdown_type}")
	if not bid:
		frappe.throw("breakdown_id is required for collection payment list")

	if btype == "territory":
		if bid.lower() in ("unassigned", ""):
			return " AND COALESCE(c.territory, 'Unassigned') = 'Unassigned'", [], "Unassigned"
		mop_like = f"% - {bid}"
		return (
			" AND (COALESCE(c.territory, 'Unassigned') = %s OR pe.mode_of_payment LIKE %s)",
			[bid, mop_like],
			bid,
		)

	if btype == "customer":
		return " AND pe.party_type = 'Customer' AND pe.party = %s", [bid], bid

	# salesperson — payment must allocate to an SI with this sales person on Sales Team
	if not frappe.db.table_exists("Sales Team"):
		return " AND 1=0", [], bid
	sp_sql = """
		AND EXISTS (
			SELECT 1
			FROM `tabPayment Entry Reference` per_f
			INNER JOIN `tabSales Invoice` si_f ON si_f.name = per_f.reference_name
				AND per_f.reference_doctype = 'Sales Invoice'
			INNER JOIN `tabSales Team` st_f ON st_f.parent = si_f.name
				AND st_f.parenttype = 'Sales Invoice'
			WHERE per_f.parent = pe.name
			  AND COALESCE(st_f.sales_person, 'Unassigned') = %s
		)
	"""
	return sp_sql, [bid], bid


def _payment_entry_salesperson(payment_entry: str) -> Optional[str]:
	if not frappe.db.table_exists("Sales Team"):
		return None
	row = frappe.db.sql(
		"""
		SELECT COALESCE(st.sales_person, 'Unassigned') AS salesperson
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabSales Invoice` si ON si.name = per.reference_name
			AND per.reference_doctype = 'Sales Invoice'
		INNER JOIN `tabSales Team` st ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
		WHERE per.parent = %s
		ORDER BY per.allocated_amount DESC
		LIMIT 1
		""",
		(payment_entry,),
		as_dict=True,
	)
	return row[0].salesperson if row else None


def _party_bank_label(party_bank_account: Optional[str], bank: Optional[str]) -> Optional[str]:
	raw = (party_bank_account or bank or "").strip()
	if not raw:
		return None
	if frappe.db.exists("Bank Account", raw):
		return frappe.db.get_value("Bank Account", raw, "account_name") or raw
	return raw


def _fetch_payment_allocations(payment_names: list[str]) -> dict[str, list[dict[str, Any]]]:
	if not payment_names:
		return {}
	placeholders = ", ".join(["%s"] * len(payment_names))
	rows = frappe.db.sql(
		f"""
		SELECT
			per.parent AS payment_entry,
			per.reference_name AS invoice,
			per.reference_doctype AS invoice_type,
			COALESCE(per.allocated_amount, 0) AS allocated_amount,
			CASE
				WHEN per.reference_doctype = 'Sales Invoice' AND si.name IS NOT NULL
				THEN COALESCE(si.outstanding_amount, 0)
				ELSE NULL
			END AS outstanding_after
		FROM `tabPayment Entry Reference` per
		LEFT JOIN `tabSales Invoice` si ON si.name = per.reference_name
			AND per.reference_doctype = 'Sales Invoice'
		WHERE per.parent IN ({placeholders})
		ORDER BY per.parent, per.idx
		""",
		tuple(payment_names),
		as_dict=True,
	)
	out: dict[str, list[dict[str, Any]]] = {name: [] for name in payment_names}
	for row in rows:
		entry = {
			"invoice": row.invoice,
			"invoice_type": row.invoice_type or "Sales Invoice",
			"allocated_amount": round(float(row.allocated_amount or 0), 2),
		}
		if row.outstanding_after is not None:
			entry["outstanding_after"] = round(float(row.outstanding_after or 0), 2)
		out.setdefault(row.payment_entry, []).append(entry)
	return out


def get_collection_payments_payload(
	company: Optional[str] = None,
	from_date: Optional[str] = None,
	to_date: Optional[str] = None,
	period: Optional[str] = None,
	breakdown_type: Optional[str] = None,
	breakdown_id: Optional[str] = None,
	payment_entry: Optional[str] = None,
	limit: int = 500,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	"""Payment Entry (Receive) list/detail for collection breakdown drill on mobile."""
	start, end, period_key = _resolve_collection_period(from_date, to_date, period)
	company = company or frappe.defaults.get_user_default("Company")
	currency = frappe.db.get_value("Company", company, "default_currency") if company else "SAR"

	if territories is None:
		territories = resolve_territory_scope(company=company, purpose="view", module="sales")

	company_sql, company_params = _company_sql(company)
	terr_sql, terr_params = _customer_territory_sql(territories)

	breakdown_sql = ""
	breakdown_params: list[Any] = []
	breakdown_label = ""
	if payment_entry:
		pe_name = (payment_entry or "").strip()
		if not pe_name:
			frappe.throw("payment_entry is required for detail view")
		breakdown_sql = " AND pe.name = %s"
		breakdown_params = [pe_name]
		breakdown_type = (breakdown_type or "").strip().lower() or None
		breakdown_id = (breakdown_id or "").strip() or None
		breakdown_label = breakdown_id or pe_name
	elif breakdown_type and breakdown_id:
		breakdown_sql, breakdown_params, breakdown_label = _breakdown_filter_sql(
			breakdown_type, breakdown_id, company_params=company_params
		)
	else:
		frappe.throw("breakdown_type and breakdown_id are required unless payment_entry is set")

	limit = max(1, min(int(limit or 500), 2000))
	btype_normalized = (breakdown_type or "").strip().lower() if not payment_entry else ""

	candidate_rows = frappe.db.sql(
		f"""
		SELECT
			pe.name AS payment_entry,
			pe.posting_date,
			pe.reference_date,
			pe.party AS customer,
			COALESCE(c.customer_name, pe.party) AS customer_name,
			COALESCE(c.territory, 'Unassigned') AS territory,
			COALESCE(pe.base_paid_amount, pe.paid_amount, 0) AS paid_amount,
			pe.paid_to AS currency,
			pe.mode_of_payment,
			pe.receipt_no,
			pe.reference_no,
			pe.remarks,
			pe.docstatus,
			pe.party_bank_account,
			pe.bank
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabCustomer` c ON c.name = pe.party AND pe.party_type = 'Customer'
		WHERE pe.docstatus = 1
		  AND pe.payment_type = 'Receive'
		  AND pe.party_type = 'Customer'
		  AND pe.posting_date BETWEEN %s AND %s
		  {company_sql}
		  {terr_sql}
		  {breakdown_sql}
		ORDER BY pe.posting_date DESC, pe.name DESC
		LIMIT 10000
		""",
		tuple([start, end, *company_params, *terr_params, *breakdown_params]),
		as_dict=True,
	)

	hidden_other_branch = 0
	totals_by_mode_of_payment: list[dict[str, Any]] = []
	drill_payment_count = 0
	total_collected = 0.0

	if btype_normalized == "territory" and (breakdown_id or "").strip() and not payment_entry:
		drill_territory = (breakdown_id or "").strip()
		known_territories = _known_branch_territory_names(company)
		total_collected, drill_payment_count, totals_by_mode_of_payment = _aggregate_territory_drill_payments(
			candidate_rows,
			drill_territory=drill_territory,
			known_territories=known_territories,
			company=company,
			start=start,
			end=end,
			currency=currency,
		)
		for row in candidate_rows:
			ok, reason = _payment_matches_territory_drill(
				customer_territory=row.territory,
				mode_of_payment=row.mode_of_payment,
				drill_territory=drill_territory,
				known_territories=known_territories,
			)
			if not ok and reason == "other_branch_mop":
				hidden_other_branch += 1
		filtered_rows = [
			row
			for row in candidate_rows
			if _payment_matches_territory_drill(
				customer_territory=row.territory,
				mode_of_payment=row.mode_of_payment,
				drill_territory=drill_territory,
				known_territories=known_territories,
			)[0]
		]
		rows = filtered_rows[:limit]
	else:
		rows = candidate_rows[:limit]
		drill_payment_count = len(candidate_rows)
		mode_payment_counts: dict[str, int] = {}
		for row in candidate_rows:
			mop = (row.mode_of_payment or "").strip() or "Unassigned"
			mode_payment_counts[mop] = mode_payment_counts.get(mop, 0) + 1
		totals_by_mode_of_payment = _summarize_modes_gl_net(
			company, start, end, mode_payment_counts, currency=currency
		)
		total_collected = round(sum(float(r["net"]) for r in totals_by_mode_of_payment), 2)

	pe_names = [row.payment_entry for row in rows]
	alloc_map = _fetch_payment_allocations(pe_names)

	items: list[dict[str, Any]] = []
	for row in rows:
		paid = round(float(row.paid_amount or 0), 2)
		sp = _payment_entry_salesperson(row.payment_entry)
		receipt_no = (row.receipt_no or "").strip() or row.payment_entry
		reference_no = (row.reference_no or "").strip() or None
		mode_of_payment = (row.mode_of_payment or "").strip() or None
		items.append(
			{
				"payment_entry": row.payment_entry,
				"posting_date": str(row.posting_date) if row.posting_date else None,
				"reference_date": str(row.reference_date) if row.reference_date else None,
				"customer": row.customer,
				"customer_name": row.customer_name,
				"territory": row.territory,
				"salesperson": sp,
				"paid_amount": paid,
				"paid_amount_display": format_collection_amount(paid, currency),
				"amount_format": COLLECTION_AMOUNT_FORMAT,
				"currency": currency,
				"mode_of_payment": mode_of_payment,
				"receipt_number": receipt_no,
				"receipt_no": receipt_no,
				"reference_no": reference_no,
				"remarks": row.remarks or "",
				"status": "Submitted" if int(row.docstatus or 0) == 1 else "Draft",
				"party_bank": _party_bank_label(row.party_bank_account, row.bank),
				"allocated_invoices": alloc_map.get(row.payment_entry) or [],
			}
		)

	meta: dict[str, Any] = {
		"currency": currency,
		"company": company,
		"from_date": str(start),
		"to_date": str(end),
		"period": period_key,
		"breakdown_type": (breakdown_type or "").strip().lower() or None,
		"breakdown_id": (breakdown_id or "").strip() or None,
		"breakdown_label": breakdown_label,
		"amount_format": COLLECTION_AMOUNT_FORMAT,
		"amount_basis": COLLECTION_AMOUNT_BASIS,
		"total_collected": round(total_collected, 2),
		"total_collected_display": format_collection_amount(total_collected, currency),
		"payment_count": drill_payment_count,
		"payment_count_in_response": len(items),
		"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
	}
	if btype_normalized == "territory" and (breakdown_id or "").strip() and not payment_entry:
		meta["territory_drill_filter"] = {
			"breakdown_id": (breakdown_id or "").strip(),
			"payments_hidden_other_branch": hidden_other_branch,
			"filter_note": _TERRITORY_DRILL_FILTER_NOTE,
		}

	return {
		"meta": meta,
		"summary": {
			"collected": round(total_collected, 2),
			"net": round(total_collected, 2),
			"collected_display": format_collection_amount(total_collected, currency),
			"amount_format": COLLECTION_AMOUNT_FORMAT,
			"amount_basis": COLLECTION_AMOUNT_BASIS,
			"payment_count": drill_payment_count,
			"payment_count_in_response": len(items),
			"totals_by_mode_of_payment": totals_by_mode_of_payment,
		},
		"items": items,
	}


def get_collection_attention_payload(
	company: Optional[str] = None,
	min_unallocated: float = 100.0,
	limit: int = 20,
	territories: Optional[List[str]] = None,
) -> dict[str, Any]:
	if territories is None:
		territories = resolve_territory_scope(company=company, purpose="view", module="receivables")
	return {
		"overdue_customers": get_overdue_customers(company=company, limit=limit, territories=territories),
		"unallocated_payments": get_unallocated_payments(
			company=company, min_unallocated=min_unallocated, limit=limit, territories=territories
		),
	}
