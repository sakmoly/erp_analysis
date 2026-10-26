import frappe
from datetime import date
from typing import Optional
from collections import defaultdict
from erp_analysis.permissions.access_profile import (
    evaluate,
    PermissionDenied,
    resolve_territory_scope,
    si_territory_sql,
    assert_document_territory_allowed,
)
from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int, to_date as _to_date

# -------- 1) Receivables Dashboard (Main table + KPIs + Territory totals) --------

@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_dashboard(company: Optional[str] = None,
                              report_date: Optional[str] = None,
                              old_days: Optional[int] = None,
                              territory: Optional[str] = None,
                              party_csv: Optional[str] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    report_date = _to_date(_get_arg("report_date", report_date))
    age_as_on = min(report_date, frappe.utils.getdate(date.today()))
    old_days = _to_int(_get_arg("old_days", old_days), 400)
    territory = _get_arg("territory", territory)
    party_csv = _get_arg("party_csv", party_csv)

    parties = []
    if party_csv:
        parties = [p.strip() for p in party_csv.split(",") if p and p.strip()]

    # Access Profile territories (profile users only); optional request narrows further
    territory_names = resolve_territory_scope(
        requested=territory, company=company, module="receivables"
    ) or []

    recv_accounts = [r.name for r in frappe.db.sql(
        """
        SELECT a.name
        FROM `tabAccount` a
        WHERE a.company = %s AND a.account_type = 'Receivable'
        """,
        (company,),
        as_dict=True,
    )]

    if not recv_accounts:
        return {
            "kpis": {
                "total_unpaid_invoice": 0.0,
                "total_overdue": 0.0,
                "overdue_gt_old_days": 0.0,
            },
            "buckets_total": {"current": 0.0, "d30": 0.0, "d60": 0.0, "d90": 0.0, "d120p": 0.0, "old_balance": 0.0},
            "rows": [],
            "territory_totals": [],
        }

    ple = frappe.db.sql(
        """
        SELECT
            ple.party, ple.party_type, ple.account,
            ple.voucher_type, ple.voucher_no,
            ple.against_voucher_type, ple.against_voucher_no,
            ple.posting_date, ple.due_date, ple.amount
        FROM `tabPayment Ledger Entry` ple
        WHERE ple.delinked = 0
          AND ple.company = %(company)s
          AND ple.account IN %(recv_accounts)s
          AND ple.party_type = 'Customer'
          AND ple.posting_date <= %(report_date)s
          {party_filter}
        """.format(
            party_filter="AND ple.party IN %(parties)s" if parties else ""
        ),
        {
            "company": company,
            "recv_accounts": tuple(recv_accounts),
            "report_date": report_date,
            "parties": tuple(parties) if parties else (),
        },
        as_dict=True,
    )

    si_meta = frappe.db.sql(
        """
        SELECT
            si.name AS voucher_no,
            si.customer AS party,
            si.status AS status,
            si.posting_date,
            COALESCE(si.due_date, si.posting_date) AS ageing_date
        FROM `tabSales Invoice` si
        WHERE si.company = %(company)s
          AND si.posting_date <= %(report_date)s
        """,
        {"company": company, "report_date": report_date},
        as_dict=True,
    )
    si_by_name = {r.voucher_no: r for r in si_meta}

    cust_rows = frappe.db.sql(
        """
        SELECT c.name AS party, c.customer_name, c.territory
        FROM `tabCustomer` c
        """,
        as_dict=True,
    )
    cust_by_party = {r.party: r for r in cust_rows}

    classified = []
    for p in ple:
        si = si_by_name.get(p.voucher_no) if p.voucher_type == "Sales Invoice" else None
        entry_date = si.ageing_date if si else (p.due_date or p.posting_date)

        invoiced_amt = 0.0
        paid_amt = 0.0
        credit_note_amt = 0.0

        if p.amount > 0 and not (p.voucher_type in ("Journal Entry", "Payment Entry") and p.voucher_no != p.against_voucher_no):
            invoiced_amt = float(p.amount)
        elif p.amount > 0 and p.voucher_type in ("Journal Entry", "Payment Entry") and p.voucher_no != p.against_voucher_no:
            paid_amt = -float(p.amount)
        elif p.amount <= 0 and p.voucher_type not in ("Sales Invoice", "Purchase Invoice"):
            paid_amt = -float(p.amount)
        elif p.amount <= 0 and p.voucher_type in ("Sales Invoice", "Purchase Invoice"):
            credit_note_amt = -float(p.amount)

        classified.append({
            "party": p.party,
            "trx_date": p.posting_date,
            "entry_date": entry_date,
            "invoiced": invoiced_amt,
            "paid": paid_amt,
            "credit_note": credit_note_amt,
        })

    rollup = defaultdict(lambda: {"invoiced": 0.0, "paid": 0.0, "credit_note": 0.0, "trx_date": None, "entry_date": None})
    for r in classified:
        key = (r["party"], r["entry_date"], r["trx_date"])
        v = rollup[key]
        v["invoiced"] += r["invoiced"]
        v["paid"] += r["paid"]
        v["credit_note"] += r["credit_note"]
        v["trx_date"] = v["trx_date"] or r["trx_date"]
        v["entry_date"] = v["entry_date"] or r["entry_date"]

    voucher_aged = []
    for (party, entry_date, trx_date), v in rollup.items():
        outstanding = v["invoiced"] - v["paid"] - v["credit_note"]
        if abs(outstanding) < 0.0001:
            continue
        age_days = max(frappe.utils.date_diff(age_as_on, entry_date), 0)
        old_balance = outstanding if age_days > old_days else 0.0
        bucket_current = outstanding if age_days == 0 else 0.0
        bucket_30 = outstanding if 1 <= age_days <= 30 else 0.0
        bucket_60 = outstanding if 31 <= age_days <= 60 else 0.0
        bucket_90 = outstanding if 61 <= age_days <= 90 else 0.0
        bucket_120p = outstanding if 120 < age_days <= old_days else 0.0

        voucher_aged.append({
            "party": party,
            "trx_date": trx_date,
            "entry_date": entry_date,
            "age_days": age_days,
            "invoiced": v["invoiced"],
            "paid": v["paid"],
            "credit_note": v["credit_note"],
            "outstanding": outstanding,
            "old_balance": old_balance,
            "bucket_current": bucket_current,
            "bucket_30": bucket_30,
            "bucket_60": bucket_60,
            "bucket_90": bucket_90,
            "bucket_120p": bucket_120p,
        })

    party_ledger = {}
    by_party = defaultdict(list)
    for v in voucher_aged:
        by_party[v["party"]].append(v)

    for party, items in by_party.items():
        def s(key): return sum(x[key] for x in items)
        avg_age_days = round(sum(x["age_days"] for x in items) / len(items)) if items else 0
        party_ledger[party] = {
            "invoiced_amount": s("invoiced"),
            "paid_amount": s("paid"),
            "credit_note": s("credit_note"),
            "outstanding_amount": s("outstanding"),
            "old_balance": s("old_balance"),
            "current_bucket": s("bucket_current"),
            "b_30": s("bucket_30"),
            "b_60": s("bucket_60"),
            "b_90": s("bucket_90"),
            "b_120p": s("bucket_120p"),
            "avg_age_days": avg_age_days,
        }

    latest_status = frappe.db.sql(
        """
        SELECT
          s.customer AS party,
          SUBSTRING_INDEX(
            SUBSTRING_INDEX(GROUP_CONCAT(CONCAT(s.posting_date, '||', s.status)
              ORDER BY s.posting_date DESC SEPARATOR ','), ',', 1),
            '||', -1
          ) AS invoice_status
        FROM `tabSales Invoice` s
        WHERE s.company = %s AND s.posting_date <= %s
        GROUP BY s.customer
        """,
        (company, report_date),
        as_dict=True,
    )
    status_by_party = {r.party: (r.invoice_status or "N/A") for r in latest_status}

    advances = frappe.db.sql(
        """
        SELECT pe.party, SUM(pe.unallocated_amount) AS advance_amount
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
          AND pe.company = %s
          AND pe.posting_date <= %s
          AND pe.payment_type = 'Receive'
          AND pe.party_type = 'Customer'
        {party_filter}
        GROUP BY pe.party
        """.format(
            party_filter="AND pe.party IN %(parties)s" if parties else ""
        ),
        (company, report_date) if not parties else {"company": company, "report_date": report_date, "parties": tuple(parties)},
        as_dict=True,
    )
    adv_by_party = {r.party: float(r.advance_amount or 0) for r in advances}

    rows = []
    for party, agg in party_ledger.items():
        c = cust_by_party.get(party)
        terr = (c.territory if c else None) or ""
        if territory and territory_names and terr not in territory_names:
            continue

        row = {
            "party": party,
            "customer_name": (c.customer_name if c else party),
            "territory": terr,
            "advance_amount": round(float(adv_by_party.get(party, 0)), 2),
            "invoiced_amount": round(float(agg["invoiced_amount"]), 2),
            "paid_amount": round(float(agg["paid_amount"]), 2),
            "credit_note": round(float(agg["credit_note"]), 2),
            "outstanding_amount": round(float(agg["outstanding_amount"]), 2),
            "current": round(float(agg["current_bucket"]), 2),
            "d30": round(float(agg["b_30"]), 2),
            "d60": round(float(agg["b_60"]), 2),
            "d90": round(float(agg["b_90"]), 2),
            "d120p": round(float(agg["b_120p"]), 2),
            "old_balance": round(float(agg["old_balance"]), 2),
            "avg_age_days": int(agg["avg_age_days"] or 0),
            "invoice_status": status_by_party.get(party, "N/A"),
        }
        if abs(row["outstanding_amount"]) > 100:
            rows.append(row)

    total_unpaid = sum(r["outstanding_amount"] for r in rows)
    total_overdue = sum(r["d30"] + r["d60"] + r["d90"] + r["d120p"] + r["old_balance"] for r in rows)
    overdue_gt_old_days = sum(r["old_balance"] for r in rows)

    buckets_total = {
        "current": round(sum(r["current"] for r in rows), 2),
        "d30": round(sum(r["d30"] for r in rows), 2),
        "d60": round(sum(r["d60"] for r in rows), 2),
        "d90": round(sum(r["d90"] for r in rows), 2),
        "d120p": round(sum(r["d120p"] for r in rows), 2),
        "old_balance": round(sum(r["old_balance"] for r in rows), 2),
    }

    terr_map = defaultdict(lambda: {"outstanding": 0.0, "current": 0.0, "d30": 0.0, "d60": 0.0, "d90": 0.0, "d120p": 0.0, "old_balance": 0.0})
    for r in rows:
        t = r["territory"] or "Unassigned"
        tm = terr_map[t]
        tm["outstanding"] += r["outstanding_amount"]
        tm["current"] += r["current"]
        tm["d30"] += r["d30"]
        tm["d60"] += r["d60"]
        tm["d90"] += r["d90"]
        tm["d120p"] += r["d120p"]
        tm["old_balance"] += r["old_balance"]

    territory_totals = [
        {
            "territory": t,
            "outstanding": round(v["outstanding"], 2),
            "current": round(v["current"], 2),
            "d30": round(v["d30"], 2),
            "d60": round(v["d60"], 2),
            "d90": round(v["d90"], 2),
            "d120p": round(v["d120p"], 2),
            "old_balance": round(v["old_balance"], 2),
        }
        for t, v in terr_map.items()
    ]
    territory_cards = [
        {
            "territory": row["territory"],
            "label": row["territory"],
            "value": row["outstanding"],
            "totalUnpaid": row["outstanding"],
            "outstanding": row["outstanding"],
        }
        for row in territory_totals
    ]

    return {
        "kpis": {
            "total_unpaid_invoice": round(float(total_unpaid), 2),
            "total_overdue": round(float(total_overdue), 2),
            "overdue_gt_old_days": round(float(overdue_gt_old_days), 2),
        },
        "buckets_total": buckets_total,
        "rows": rows,
        "territory_totals": territory_totals,
        "territory_cards": territory_cards,
        "series": _recv_territory_series(territory_totals),
    }


_RECV_AGING_LABELS = {
    "current": "Current",
    "d30": "1-30 Days",
    "d60": "31-60 Days",
    "d90": "61-90 Days",
    "d120p": "91-120 Days",
    "old_balance": "Over 120 Days",
}


def _recv_chart_point(label: str, value: float) -> dict:
    text = str(label)
    amount = round(float(value or 0), 2)
    return {"label": text, "value": amount, "dimension_value": text}


def _recv_aging_series(buckets_total: dict) -> list[dict]:
    series: list[dict] = []
    total = sum(float(buckets_total.get(key) or 0) for key in _RECV_AGING_LABELS)
    for key in _RECV_AGING_LABELS:
        amount = float(buckets_total.get(key) or 0)
        if amount <= 0:
            continue
        point = _recv_chart_point(_RECV_AGING_LABELS[key], amount)
        if total > 0:
            point["percentage"] = round(amount / total * 100, 1)
            point["pct"] = point["percentage"]
        series.append(point)
    return series


def _recv_territory_series(territory_totals: list) -> list[dict]:
    seen: set[str] = set()
    rows = sorted(
        (r for r in (territory_totals or []) if isinstance(r, dict)),
        key=lambda r: float(r.get("outstanding") or 0),
        reverse=True,
    )
    series: list[dict] = []
    for row in rows:
        territory = str(row.get("territory") or "Unassigned").strip()
        key = territory.lower()
        if key in seen:
            continue
        seen.add(key)
        amount = float(row.get("outstanding") or 0)
        if amount <= 0:
            continue
        series.append(_recv_chart_point(territory, amount))
    return series


def _recv_top_customer_series(rows: list, *, limit: int = 10) -> list[dict]:
    ranked = sorted(
        (r for r in (rows or []) if isinstance(r, dict)),
        key=lambda r: float(r.get("outstanding_amount") or 0),
        reverse=True,
    )
    series: list[dict] = []
    for row in ranked[: int(limit or 10)]:
        amount = float(row.get("outstanding_amount") or 0)
        if amount <= 0:
            continue
        series.append(_recv_chart_point(row.get("customer_name") or row.get("customer") or "Unknown", amount))
    return series


def _recv_overdue_customer_series(rows: list, *, limit: int = 10) -> list[dict]:
    """Legacy PLE bucket overdue — prefer _recv_overdue_customer_series_si for mobile/PWA."""
    ranked: list[tuple[float, dict]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        overdue = sum(float(row.get(field) or 0) for field in ("d30", "d60", "d90", "d120p", "old_balance"))
        if overdue <= 0:
            continue
        ranked.append((overdue, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    out: list[dict] = []
    for amount, row in ranked[: int(limit or 10)]:
        label = row.get("customer_name") or row.get("customer") or "Unknown"
        point = _recv_chart_point(label, amount)
        days = int(row.get("avg_age_days") or 0)
        if days > 0:
            point["days"] = days
            point["days_overdue"] = days
        customer_id = row.get("party") or row.get("customer")
        if customer_id:
            point["customer"] = customer_id
            point["dimension_value"] = customer_id
        out.append(point)
    return out


def _recv_overdue_customer_series_si(
    company: str,
    *,
    limit: int = 10,
    territory: Optional[str] = None,
) -> list[dict]:
    """Top customers by overdue = sum(SI.outstanding) where due_date < today (matches statement / Customer 360)."""
    scope = resolve_territory_scope(requested=territory, company=company, module="receivables") or []
    terr_sql, terr_params = si_territory_sql(scope, field="si.territory")
    today = frappe.utils.nowdate()
    rows = frappe.db.sql(
        f"""
        SELECT
            si.customer AS customer,
            COALESCE(MAX(c.customer_name), si.customer) AS customer_name,
            COALESCE(SUM(si.outstanding_amount), 0) AS outstanding,
            COALESCE(SUM(
                CASE WHEN si.due_date < %s THEN si.outstanding_amount ELSE 0 END
            ), 0) AS overdue,
            MAX(
                CASE WHEN si.due_date < %s AND si.outstanding_amount > 0
                THEN DATEDIFF(%s, si.due_date) END
            ) AS days_overdue
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.company = %s
          AND si.outstanding_amount != 0
          {terr_sql}
        GROUP BY si.customer
        HAVING overdue > 0.01
        ORDER BY overdue DESC
        LIMIT %s
        """,
        tuple([today, today, today, company] + terr_params + [int(limit or 10)]),
        as_dict=True,
    )
    # frappe db.sql with terr_params - fix param passing
    out: list[dict] = []
    for row in rows:
        label = row.customer_name or row.customer or "Unknown"
        amount = round(float(row.overdue or 0), 2)
        point = _recv_chart_point(label, amount)
        point["customer"] = row.customer
        point["dimension_value"] = row.customer
        days = int(row.days_overdue or 0)
        if days > 0:
            point["days"] = days
            point["days_overdue"] = days
        out.append(point)
    return out


def _recv_chart_payload(
    company: Optional[str],
    chart_key: str,
    *,
    limit: int = 10,
    territory: Optional[str] = None,
) -> dict:
    dash = get_receivables_dashboard(company=company, territory=territory)
    if chart_key == "aging":
        series = _recv_aging_series(dash.get("buckets_total") or {})
        dimension = "aging_bucket"
    elif chart_key == "territory":
        series = _recv_territory_series(dash.get("territory_totals") or [])
        dimension = "territory"
    elif chart_key == "top_customers":
        series = _recv_top_customer_series(dash.get("rows") or [], limit=limit)
        dimension = "customer"
    elif chart_key == "overdue_customers":
        series = _recv_overdue_customer_series_si(company, limit=limit, territory=territory)
        dimension = "customer"
    else:
        frappe.throw(f"Unsupported receivables chart: {chart_key}")

    return {
        "series": series,
        "meta": {
            "schema_version": 1,
            "chart_key": chart_key,
            "dimension": dimension,
            "count": len(series),
        },
    }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_aging_chart(company: Optional[str] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    return _recv_chart_payload(company, "aging")


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_territory_chart(company: Optional[str] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    return _recv_chart_payload(company, "territory")


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_top_customers_chart(company: Optional[str] = None, limit: Optional[int] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    limit = _to_int(_get_arg("limit", limit), 10)
    return _recv_chart_payload(company, "top_customers", limit=limit)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_overdue_customers_chart(
    company: Optional[str] = None,
    limit: Optional[int] = None,
    territory: Optional[str] = None,
):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    limit = _to_int(_get_arg("limit", limit), 10)
    territory = _get_arg("territory", territory)
    return _recv_chart_payload(company, "overdue_customers", limit=limit, territory=territory)


def _recv_overdue_trend_series(company: Optional[str], months: int = 6) -> list[dict]:
    scope = resolve_territory_scope(company=company, module="receivables")
    terr_sql, terr_params = si_territory_sql(scope, field="territory")

    current_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(due_date, '%%b') AS month_label,
               YEAR(due_date) AS yr,
               MONTH(due_date) AS mo,
               SUM(outstanding_amount) AS overdue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
          AND due_date < CURDATE()
          AND due_date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
          AND company = %s
          {terr_sql}
        GROUP BY YEAR(due_date), MONTH(due_date)
        ORDER BY YEAR(due_date), MONTH(due_date)
        """,
        (months, company) + tuple(terr_params),
        as_dict=True,
    )
    ly_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(due_date, '%%b') AS month_label,
               YEAR(due_date) AS yr,
               MONTH(due_date) AS mo,
               SUM(outstanding_amount) AS overdue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
          AND due_date < DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
          AND due_date >= DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL %s MONTH)
          AND company = %s
          {terr_sql}
        GROUP BY YEAR(due_date), MONTH(due_date)
        ORDER BY YEAR(due_date), MONTH(due_date)
        """,
        (months, company) + tuple(terr_params),
        as_dict=True,
    )
    ly_map = {r.month_label: float(r.overdue or 0) for r in ly_rows}
    series: list[dict] = []
    for row in current_rows:
        label = row.month_label
        value = float(row.overdue or 0)
        point = {"label": label, "value": round(value, 2), "dimension_value": label, "period": label}
        ly_val = ly_map.get(label)
        if ly_val is not None:
            point["value_ly"] = round(ly_val, 2)
        series.append(point)
    return series


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_overdue_trend_chart(company: Optional[str] = None, months: Optional[int] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    months = _to_int(_get_arg("months", months), 6)
    series = _recv_overdue_trend_series(company, months=months)
    return {
        "series": series,
        "meta": {
            "schema_version": 1,
            "chart_key": "receivables_overdue_trend",
            "dimension": "month",
            "compare": "ly",
            "count": len(series),
        },
    }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_attention(company: Optional[str] = None, limit: Optional[int] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    limit = _to_int(_get_arg("limit", limit), 10)
    from erp_analysis.services.receivables_attention import get_receivables_attention_items

    return get_receivables_attention_items(company=company, limit=limit)


# -------- 2) Receivables Snapshot (KPIs only) --------

@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_snapshot(company: Optional[str] = None, territory: Optional[str] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    territory = _get_arg("territory", territory)
    scope = resolve_territory_scope(requested=territory, company=company, module="receivables")
    terr_sql, terr_params = si_territory_sql(scope, field="territory")
    si_terr_sql, si_terr_params = si_territory_sql(scope, field="si.territory")

    # ---------- helpers ----------
    def _sum(q: str, params: tuple) -> float:
        return float(frappe.db.sql(q, params)[0][0] or 0)

    base = (company,) + tuple(terr_params)
    si_base = (company,) + tuple(si_terr_params)

    # ---------- totals ----------
    total_unpaid = _sum(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    total_overdue = _sum(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND due_date < CURDATE()
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    # ---------- age buckets (overdue only) ----------
    overdue_1_30 = _sum(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND due_date < CURDATE()
          AND DATEDIFF(CURDATE(), due_date) BETWEEN 1 AND 30
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    overdue_31_60 = _sum(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND due_date < CURDATE()
          AND DATEDIFF(CURDATE(), due_date) BETWEEN 31 AND 60
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    overdue_61_90 = _sum(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND due_date < CURDATE()
          AND DATEDIFF(CURDATE(), due_date) BETWEEN 61 AND 90
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    overdue_over_90 = _sum(
        f"""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND due_date < CURDATE()
          AND DATEDIFF(CURDATE(), due_date) > 90
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    # ---------- DSO (last 30 days) ----------
    dso = _sum(
        f"""
        SELECT COALESCE(
          CASE WHEN SUM(base_grand_total) > 0
               THEN (SUM(outstanding_amount) / SUM(base_grand_total)) * 30
               ELSE 0 END, 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
          AND company = %s
          {terr_sql}
        """,
        base,
    )

    # ---------- Average Collection Period (last 90 days) ----------
    # Use allocated_amount from Payment Entry Reference, and invoice posting_date as the start.
    avg_collection_period = _sum(
        f"""
        SELECT COALESCE(AVG(DATEDIFF(pe.clearance_date, si.posting_date)), 0)
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        INNER JOIN `tabSales Invoice` si ON si.name = per.reference_name
        WHERE per.reference_doctype = 'Sales Invoice'
          AND per.allocated_amount > 0
          AND pe.docstatus = 1
          AND pe.company = %s
          AND pe.clearance_date IS NOT NULL
          AND pe.clearance_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
          {si_terr_sql}
        """,
        si_base,
    )

    overdue_percentage = (total_overdue / total_unpaid * 100.0) if total_unpaid else 0.0

    return {
        "totalUnpaid": float(total_unpaid),
        "totalOverdue": float(total_overdue),
        "overdue_0_30": float(overdue_1_30),   # keeping your response keys as-is
        "overdue_31_60": float(overdue_31_60),
        "overdue_61_90": float(overdue_61_90),
        "overdue_over_90": float(overdue_over_90),
        "overduePercentage": round(overdue_percentage, 1),
        "dso": int(dso),
        "averageCollectionPeriod": int(avg_collection_period),
    }

# -------- 3) Receivables Performance --------

from typing import Optional

@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_performance(
    company: Optional[str] = None,
    territory: Optional[str] = None,
    limit: Optional[int] = None
):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    limit = _to_int(_get_arg("limit", limit), 10)
    territory = _get_arg("territory", territory)

    scope = resolve_territory_scope(requested=territory, company=company, module="receivables")
    terr_clause, terr_params = si_territory_sql(scope, field="si.territory")
    terr_args: tuple = tuple(terr_params)

    # ---------- Top overdue customers ----------
    sql_customers = (
        "SELECT si.customer_name AS name, si.customer, SUM(si.outstanding_amount) AS amount "
        "FROM `tabSales Invoice` si "
        "WHERE si.docstatus = 1 "
        "  AND si.outstanding_amount > 0 "
        "  AND si.due_date < CURDATE() "
        "  AND si.company = %s"
        + terr_clause +
        " GROUP BY si.customer, si.customer_name "
        "ORDER BY amount DESC "
        "LIMIT %s"
    )
    params_customers = (company,) + terr_args + (limit,)
    top_overdue_customers = frappe.db.sql(sql_customers, params_customers, as_dict=True)

    # ---------- Top overdue invoices ----------
    sql_invoices = (
        "SELECT si.name AS invoice, "
        "       si.customer_name AS customer, "
        "       si.outstanding_amount AS amount, "
        "       DATEDIFF(CURDATE(), si.due_date) AS days "
        "FROM `tabSales Invoice` si "
        "WHERE si.docstatus = 1 "
        "  AND si.outstanding_amount > 0 "
        "  AND si.due_date < CURDATE() "
        "  AND si.company = %s"
        + terr_clause +
        " ORDER BY si.outstanding_amount DESC "
        "LIMIT %s"
    )
    params_invoices = (company,) + terr_args + (limit,)
    top_overdue_invoices = frappe.db.sql(sql_invoices, params_invoices, as_dict=True)

    # ---------- Aging breakdown: >120 days rolled into 'Old Balance' ----------
    sql_aging = (
        "WITH base AS ( "
        "  SELECT si.outstanding_amount, si.due_date "
        "  FROM `tabSales Invoice` si "
        "  WHERE si.docstatus = 1 "
        "    AND si.company = %s "
        "    AND si.outstanding_amount > 0"
        + terr_clause +
        ") "
        "SELECT period, amount FROM ( "
        "  SELECT 'Current' AS period, COALESCE(SUM(outstanding_amount), 0) AS amount "
        "  FROM base "
        "  WHERE due_date IS NULL OR due_date >= CURDATE() "
        "  UNION ALL "
        "  SELECT '1-30 Days', COALESCE(SUM(outstanding_amount), 0) "
        "  FROM base "
        "  WHERE due_date < CURDATE() AND DATEDIFF(CURDATE(), due_date) BETWEEN 1 AND 30 "
        "  UNION ALL "
        "  SELECT '31-60 Days', COALESCE(SUM(outstanding_amount), 0) "
        "  FROM base "
        "  WHERE due_date < CURDATE() AND DATEDIFF(CURDATE(), due_date) BETWEEN 31 AND 60 "
        "  UNION ALL "
        "  SELECT '61-90 Days', COALESCE(SUM(outstanding_amount), 0) "
        "  FROM base "
        "  WHERE due_date < CURDATE() AND DATEDIFF(CURDATE(), due_date) BETWEEN 61 AND 90 "
        "  UNION ALL "
        "  SELECT '91-120 Days', COALESCE(SUM(outstanding_amount), 0) "
        "  FROM base "
        "  WHERE due_date < CURDATE() AND DATEDIFF(CURDATE(), due_date) BETWEEN 91 AND 120 "
        "  UNION ALL "
        "  SELECT 'Old Balance', COALESCE(SUM(outstanding_amount), 0) "
        "  FROM base "
        "  WHERE due_date < CURDATE() AND DATEDIFF(CURDATE(), due_date) > 120 "
        ") z "
        "WHERE amount > 0 "
        "ORDER BY FIELD(period, 'Current','1-30 Days','31-60 Days','61-90 Days','91-120 Days','Old Balance')"
    )
    params_aging = (company,) + terr_args
    aging_breakdown = frappe.db.sql(sql_aging, params_aging, as_dict=True)

    # ---------- Collection efficiency (invoice-level, last 90 days) ----------
    sql_eff = (
        "WITH paid AS ( "
        "  SELECT si.name AS invoice, si.due_date AS si_due_date, MIN(pe.clearance_date) AS first_clearance "
        "  FROM `tabSales Invoice` si "
        "  JOIN `tabPayment Entry Reference` per "
        "    ON per.reference_doctype = 'Sales Invoice' "
        "   AND per.reference_name = si.name "
        "   AND per.allocated_amount > 0 "
        "  JOIN `tabPayment Entry` pe "
        "    ON pe.name = per.parent "
        "   AND pe.docstatus = 1 "
        "   AND pe.company = %s "
        "   AND pe.clearance_date IS NOT NULL "
        "   AND pe.clearance_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) "
        "  WHERE si.docstatus = 1 "
        "    AND si.company = %s "
        "  GROUP BY si.name, si.due_date "
        ") "
        "SELECT COALESCE( "
        "  (SUM(CASE WHEN DATEDIFF(first_clearance, si_due_date) <= 0 THEN 1 ELSE 0 END) "
        "   / NULLIF(COUNT(*), 0)) * 100, 0)"
        " FROM paid"
    )
    collection_efficiency = float(
        frappe.db.sql(sql_eff, (company, company))[0][0] or 0.0
    )

    return {
        "topOverdueCustomers": [
            {"name": r.name, "customer": r.customer, "amount": float(r.amount or 0)}
            for r in top_overdue_customers
        ],
        "topOverdueInvoices": [
            {
                "invoice": r.invoice,
                "customer": r.customer,
                "amount": float(r.amount or 0),
                "days": int(r.days or 0),
            }
            for r in top_overdue_invoices
        ],
        "agingBreakdown": [
            {"period": r.period, "amount": float(r.amount or 0)} for r in aging_breakdown
        ],
        "collectionEfficiency": float(collection_efficiency),
    }


    # ----- collection efficiency (last 90 days), invoice-level -----
    # % of invoices whose FIRST clearance date <= invoice due_date
    collection_efficiency = float(frappe.db.sql(
        """
        WITH paid AS (
          SELECT
            si.name AS invoice,
            si.due_date AS si_due_date,
            MIN(pe.clearance_date) AS first_clearance
          FROM `tabSales Invoice` si
          JOIN `tabPayment Entry Reference` per
            ON per.reference_doctype = 'Sales Invoice'
           AND per.reference_name = si.name
           AND per.allocated_amount > 0
          JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
           AND pe.docstatus = 1
           AND pe.company = %s
           AND pe.clearance_date IS NOT NULL
           AND pe.clearance_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
          WHERE si.docstatus = 1
            AND si.company = %s
          GROUP BY si.name, si.due_date
        )
        SELECT COALESCE(
          (SUM(CASE WHEN DATEDIFF(first_clearance, si_due_date) <= 0 THEN 1 ELSE 0 END)
           / NULLIF(COUNT(*), 0)) * 100, 0)
        FROM paid
        """,
        (company, company),
    )[0][0] or 0.0)

    # ----- shape the response (NO placeholders) -----
    return {
        "topOverdueCustomers": [
            {"name": r.name, "customer": r.customer, "amount": float(r.amount or 0)}
            for r in top_overdue_customers
        ],
        "topOverdueInvoices": [
            {
                "invoice": r.invoice,
                "customer": r.customer,
                "amount": float(r.amount or 0),
                "days": int(r.days or 0),
            }
            for r in top_overdue_invoices
        ],
        "agingBreakdown": [
            {"period": r.period, "amount": float(r.amount or 0)}
            for r in aging_breakdown
        ],
        "collectionEfficiency": float(collection_efficiency),
    }

# -------- 4) Receivables Trends --------

@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_receivables_trends(company: Optional[str] = None,
                           territory: Optional[str] = None,
                           months: Optional[int] = None):
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    months = _to_int(_get_arg("months", months), 11)
    territory = _get_arg("territory", territory)
    scope = resolve_territory_scope(requested=territory, company=company, module="receivables")
    terr_sql, terr_params = si_territory_sql(scope, field="territory")
    si_terr_sql, si_terr_params = si_territory_sql(scope, field="si.territory")
    c_terr_sql, c_terr_params = si_territory_sql(scope, field="c.territory")

    ar_trend = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(posting_date, '%%b %%Y') AS month, SUM(outstanding_amount) AS amount
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND posting_date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
          AND company = %s
          {terr_sql}
        GROUP BY YEAR(posting_date), MONTH(posting_date)
        ORDER BY YEAR(posting_date), MONTH(posting_date)
        """,
        (months, company) + tuple(terr_params),
        as_dict=True,
    )

    receivable_by_territory = frappe.db.sql(
        f"""
        SELECT c.territory, SUM(si.outstanding_amount) AS amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.company = %s AND c.territory IS NOT NULL
          {c_terr_sql}
        GROUP BY c.territory
        ORDER BY amount DESC
        """,
        (company,) + tuple(c_terr_params),
        as_dict=True,
    )

    overdue_by_territory = frappe.db.sql(
        f"""
        SELECT c.territory, SUM(si.outstanding_amount) AS overdue
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0
          AND si.due_date < CURDATE() AND si.company = %s AND c.territory IS NOT NULL
          {c_terr_sql}
        GROUP BY c.territory
        ORDER BY overdue DESC
        """,
        (company,) + tuple(c_terr_params),
        as_dict=True,
    )

    monthly_overdue_trend = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(due_date, '%%b') AS month, SUM(outstanding_amount) AS overdue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
          AND due_date < CURDATE() AND due_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
          AND company = %s
          {terr_sql}
        GROUP BY YEAR(due_date), MONTH(due_date)
        ORDER BY YEAR(due_date), MONTH(due_date)
        LIMIT 6
        """,
        (company,) + tuple(terr_params),
        as_dict=True,
    )
    
    monthly_sales_vs_collection = frappe.db.sql(
    f"""
    SELECT DATE_FORMAT(si.posting_date, '%%b') AS month,
           SUM(si.base_grand_total) AS sales,
           COALESCE(SUM(per.allocated_amount), 0) AS collection
    FROM `tabSales Invoice` si
    LEFT JOIN `tabPayment Entry Reference` per ON per.reference_name = si.name
    LEFT JOIN `tabPayment Entry` pe ON pe.name = per.parent
    WHERE si.docstatus = 1
      AND YEAR(si.posting_date) = YEAR(CURDATE())                -- YTD from Jan 1
      AND si.company = %s
      AND (pe.docstatus = 1 OR pe.docstatus IS NULL)
      {si_terr_sql}
    GROUP BY YEAR(si.posting_date), MONTH(si.posting_date)
    ORDER BY YEAR(si.posting_date), MONTH(si.posting_date)
    """,
    (company,) + tuple(si_terr_params),
    as_dict=True,
  )

    total_receivable = sum((r.amount or 0) for r in receivable_by_territory)
    receivable_by_territory_with_pct = [
        {
            "territory": r.territory,
            "amount": float(r.amount or 0),
            "percentage": round(((r.amount or 0) / total_receivable * 100), 1) if total_receivable else 0.0,
        }
        for r in receivable_by_territory
    ]

    return {
        "arTrend": [{"month": r.month, "amount": float(r.amount or 0)} for r in ar_trend],
        "receivableByTerritory": receivable_by_territory_with_pct,
        "overdueByTerritory": [{"territory": r.territory, "overdue": float(r.overdue or 0)} for r in overdue_by_territory],
        "monthlyOverdueTrend": [{"month": r.month, "overdue": float(r.overdue or 0)} for r in monthly_overdue_trend],
        "monthlySalesVsCollection": [
            {"month": r.month, "sales": float(r.sales or 0), "collection": float(r.collection or 0)}
            for r in monthly_sales_vs_collection
        ],
    }

# -------- Territory receivables customer list (mobile drill-down) --------


def _parse_bool_arg(value, default=False):
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() in ("1", "true", "yes", "on")


_TERRITORY_LIST_SUMMARY_CACHE_TTL = 120


def _territory_list_sort_sql(sort: str, as_of_date) -> str:
	sort = (sort or "outstanding_desc").strip().lower()
	age = "COALESCE(si.due_date, si.posting_date)"
	if sort == "overdue_desc":
		return f"""SUM(CASE WHEN {age} < %s THEN si.outstanding_amount ELSE 0 END) DESC,
			customer_name ASC"""
	if sort == "name_asc":
		return "customer_name ASC"
	if sort == "outstanding_asc":
		return "SUM(si.outstanding_amount) ASC, customer_name ASC"
	return "SUM(si.outstanding_amount) DESC, customer_name ASC"


def _territory_list_summary_cache_key(company: str, territory: str, as_of) -> str:
	return f"recv_terr_sum:{company}:{territory}:{as_of}"


def _fetch_territory_receivables_page(
	company: str,
	territory: str,
	*,
	limit: int,
	offset: int,
	sort: str,
	as_of,
	include_summary: bool,
	include_row_detail: bool = False,
):
	"""Single territory open-AR page (Customer.territory + SI outstanding)."""
	age = "COALESCE(si.due_date, si.posting_date)"
	base_from = """
		FROM `tabSales Invoice` si
		INNER JOIN `tabCustomer` c ON c.name = si.customer AND c.territory = %s
		WHERE si.docstatus = 1
		  AND si.company = %s
		  AND si.outstanding_amount != 0
	"""
	base_params = [territory, company]

	agg_from = f"""
		FROM (
			SELECT
				si.customer,
				COALESCE(MAX(c.customer_name), si.customer) AS customer_name,
				c.territory AS territory,
				SUM(si.outstanding_amount) AS outstanding,
				SUM(CASE WHEN {age} < %s THEN si.outstanding_amount ELSE 0 END) AS overdue
			{base_from}
			GROUP BY si.customer, c.territory
			HAVING SUM(si.outstanding_amount) > 0.01
		) agg
	"""

	summary_block = None
	total_customers = 0
	cache_key = _territory_list_summary_cache_key(company, territory, as_of)
	cached = frappe.cache.get_value(cache_key) if include_summary and offset == 0 else None

	if cached and isinstance(cached, dict):
		total_customers = int(cached.get("total_customers") or 0)
		summary_block = cached.get("summary")
	elif include_summary and offset == 0:
		summary_row = frappe.db.sql(
			f"""
			SELECT
				COUNT(*) AS total_customers,
				COALESCE(SUM(outstanding), 0) AS total_outstanding,
				COALESCE(SUM(overdue), 0) AS total_overdue
			{agg_from}
			""",
			tuple([as_of] + base_params),
			as_dict=True,
		)[0]
		total_customers = int(summary_row.total_customers or 0)
		total_out = round(float(summary_row.total_outstanding or 0), 2)
		total_od = round(float(summary_row.total_overdue or 0), 2)
		summary_block = {
			"total_outstanding": total_out,
			"total_overdue": total_od,
			"total_current": round(max(0.0, total_out - total_od), 2),
		}
		frappe.cache.set_value(
			cache_key,
			{"total_customers": total_customers, "summary": summary_block},
			expires_in_sec=_TERRITORY_LIST_SUMMARY_CACHE_TTL,
		)
	elif offset == 0:
		total_customers = int(
			frappe.db.sql(
				f"SELECT COUNT(*) AS n {agg_from}",
				tuple([as_of] + base_params),
				as_dict=True,
			)[0].n
			or 0
		)

	sort_sql = _territory_list_sort_sql(sort, as_of)
	order_params = [as_of] if (sort or "").strip().lower() == "overdue_desc" else []

	detail_select = ""
	detail_params: list = []
	if include_row_detail:
		detail_select = f""",
			MAX(
				CASE
					WHEN {age} < %s AND si.outstanding_amount > 0
					THEN DATEDIFF(%s, {age})
				END
			) AS days_overdue,
			MIN(
				CASE WHEN si.outstanding_amount > 0 THEN {age} END
			) AS oldest_due_date"""
		detail_params = [as_of, as_of]

	customer_rows = frappe.db.sql(
		f"""
		SELECT
			si.customer AS customer_id,
			COALESCE(MAX(c.customer_name), si.customer) AS customer_name,
			c.territory AS territory,
			SUM(si.outstanding_amount) AS outstanding,
			SUM(CASE WHEN {age} < %s THEN si.outstanding_amount ELSE 0 END) AS overdue
			{detail_select}
		{base_from}
		GROUP BY si.customer, c.territory
		HAVING SUM(si.outstanding_amount) > 0.01
		ORDER BY {sort_sql}
		LIMIT %s OFFSET %s
		""",
		tuple([as_of] + detail_params + base_params + order_params + [limit, offset]),
		as_dict=True,
	)

	customers = []
	for row in customer_rows:
		outstanding = round(float(row.outstanding or 0), 2)
		overdue = round(float(row.overdue or 0), 2)
		current = round(max(0.0, outstanding - overdue), 2)
		entry = {
			"customer_id": row.customer_id,
			"customer_name": row.customer_name,
			"customer": row.customer_id,
			"outstanding": outstanding,
			"outstanding_amount": outstanding,
			"overdue": overdue,
			"overdue_amount": overdue,
			"current": current,
			"territory": row.territory,
		}
		if include_row_detail:
			if row.days_overdue is not None:
				entry["days_overdue"] = int(row.days_overdue)
			if row.oldest_due_date:
				entry["oldest_due_date"] = str(row.oldest_due_date)
		customers.append(entry)

	page_len = len(customers)
	if offset > 0 and not include_summary:
		has_more = page_len >= limit
		total_customers = 0
	else:
		has_more = (offset + page_len) < total_customers if total_customers else page_len >= limit

	return {
		"customers": customers,
		"total_customers": total_customers,
		"has_more": has_more,
		"summary": summary_block,
	}


def _legacy_territory_receivables_payload(
	company: str,
	territory: str,
	page: dict,
	*,
	limit: int,
	offset: int,
	sort: str,
):
	"""Map fast list page to legacy get_territory_receivables response shape."""
	summary = page.get("summary") or {}
	total_out = float(summary.get("total_outstanding") or 0)
	total_od = float(summary.get("total_overdue") or 0)
	total_cur = float(summary.get("total_current") or max(0.0, total_out - total_od))
	legacy_customers = []
	for row in page.get("customers") or []:
		cur = float(row.get("current") or 0)
		od = float(row.get("overdue") or 0)
		legacy_customers.append(
			{
				"customer": row["customer_id"],
				"customer_name": row["customer_name"],
				"outstanding_amount": row["outstanding"],
				"aging": {
					"Current": cur,
					"1-30 Days": od,
					"31-60 Days": 0.0,
					"61-90 Days": 0.0,
					"91-120 Days": 0.0,
					"Old Balance": 0.0,
				},
			}
		)
	return {
		"territory": territory,
		"territories": [territory],
		"summary": {
			"totalUnpaid": total_out,
			"totalOverdue": total_od,
			"aging": {
				"Current": total_cur,
				"1-30 Days": total_od,
				"31-60 Days": 0.0,
				"61-90 Days": 0.0,
				"91-120 Days": 0.0,
				"Old Balance": 0.0,
			},
		},
		"customers": legacy_customers,
		"pagination": {
			"total": int(page.get("total_customers") or 0),
			"limit": limit,
			"offset": offset,
		},
		"filters_applied": {"fast_path": True, "sort": sort},
	}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_territory_receivables_list(
	company: Optional[str] = None,
	territory: Optional[str] = None,
	limit: Optional[int] = None,
	offset: Optional[int] = None,
	sort: Optional[str] = None,
	as_of_date: Optional[str] = None,
	include_summary: Optional[bool] = None,
	include_detail: Optional[bool] = None,
):
	"""
	Paginated open-AR customer list for one territory (mobile territory tap).

	Totals use Customer.territory + Sales Invoice outstanding (aligned with receivables dashboard cards).
	"""
	from erp_analysis.services.statement_branding import wrap_mobile_message

	company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
	territory = (_get_arg("territory", territory) or "").strip()
	if not company:
		frappe.throw("Company is required", frappe.ValidationError)
	if not territory:
		frappe.throw("Territory is required", frappe.ValidationError)

	object_key = "erp_analysis.receivables.get_territory_receivables_list"
	try:
		employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	except Exception:
		employee = None
	user_branch = frappe.db.get_value("Employee", employee, "branch") if employee else None

	try:
		decision = evaluate(
			frappe.session.user,
			company or "",
			territory,
			user_branch or None,
			object_key,
		)
		if not decision.get("can_view"):
			raise PermissionDenied
	except PermissionDenied:
		frappe.throw(
			"Access denied: your Access Profile does not allow territory receivables list for this company/territory.",
			frappe.PermissionError,
		)

	resolve_territory_scope(requested=territory, company=company, module="receivables")

	limit = min(100, max(1, _to_int(_get_arg("limit", limit), 50)))
	offset = max(0, _to_int(_get_arg("offset", offset), 0))
	sort = _get_arg("sort", sort) or "outstanding_desc"
	as_of = _to_date(_get_arg("as_of_date", as_of_date)) or frappe.utils.getdate()
	include_summary = _parse_bool_arg(_get_arg("include_summary", include_summary), default=(offset == 0))
	include_row_detail = _parse_bool_arg(_get_arg("include_detail", include_detail), default=False)

	currency = frappe.db.get_value("Company", company, "default_currency") or "SAR"
	page = _fetch_territory_receivables_page(
		company,
		territory,
		limit=limit,
		offset=offset,
		sort=sort,
		as_of=as_of,
		include_summary=include_summary,
		include_row_detail=include_row_detail,
	)

	meta = {
		"company": company,
		"territory": territory,
		"currency": currency,
		"as_of_date": str(as_of),
		"total_customers": page["total_customers"],
		"limit": limit,
		"offset": offset,
		"has_more": page["has_more"],
		"sort": sort,
	}
	if page.get("summary") is not None:
		meta["summary"] = page["summary"]

	payload = {"meta": meta, "customers": page["customers"]}
	return wrap_mobile_message(payload)


# apps/erp_analysis/erp_analysis/receivables.py


@frappe.whitelist()
def get_territory_receivables(
    company=None,
    territory=None,
    limit=50,
    offset=0,
    sort="amount_desc",
    amount_cmp="gt",           # "gt" or "lt"
    amount_threshold=100       # numeric threshold (default 100)
):
    """
    Territory receivables snapshot with KPIs + aging and customer list.

    Notes:
    - Includes returns (credit notes) so they DEDUCT from totals/buckets.
    - Aging uses age_date = COALESCE(due_date, posting_date).
    - Filter customers by net outstanding using amount_cmp ('gt'/'lt') and amount_threshold.
      Comparison is on ABS(net_outstanding) so credits don't get filtered oddly.
    - Sorting: "amount_desc" (default), "amount_asc", "name_asc".
    """

    # ---- Resolve user scope ----
    try:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    except Exception:
        employee = None

    user_branch = frappe.db.get_value("Employee", employee, "branch") if employee else None
    requested_territory = territory or None

    company = company or frappe.defaults.get_user_default("Company")
    object_key = "erp_analysis.receivables.get_territory_receivables"

    # ---- Access control via Access Profile ----
    try:
        decision = evaluate(
            frappe.session.user,
            company or "",
            requested_territory or None,
            user_branch or None,
            object_key,
        )
        if not decision.get("can_view"):
            raise PermissionDenied
    except PermissionDenied:
        frappe.throw("Access denied", frappe.PermissionError)

    # Profile users → Access Profile territories; others unchanged unless territory requested
    scope = resolve_territory_scope(requested=requested_territory, company=company, module="receivables")
    final_territory = scope[0] if scope and len(scope) == 1 else (requested_territory or None)

    # ---- Defaults & sanitation ----
    try:
        limit = int(limit) if limit else 50
        offset = int(offset) if offset else 0
    except Exception:
        limit, offset = 50, 0

    # comparison operator for HAVING
    cmp_op = ">" if (str(amount_cmp or "gt").lower() == "gt") else "<"
    try:
        amount_threshold = float(amount_threshold)
    except Exception:
        amount_threshold = 100.0

    # Fast path: same data as get_territory_receivables_list (mobile / default filters).
    if (
        final_territory
        and str(amount_cmp or "gt").lower() == "gt"
        and float(amount_threshold or 100) <= 100
    ):
        sort_map = {
            "amount_desc": "outstanding_desc",
            "amount_asc": "outstanding_asc",
            "name_asc": "name_asc",
        }
        list_sort = sort_map.get(str(sort or "amount_desc").lower(), "outstanding_desc")
        page = _fetch_territory_receivables_page(
            company,
            final_territory,
            limit=min(100, max(1, limit)),
            offset=max(0, offset),
            sort=list_sort,
            as_of=frappe.utils.getdate(),
            include_summary=(offset == 0),
            include_row_detail=False,
        )
        return _legacy_territory_receivables_payload(
            company,
            final_territory,
            page,
            limit=limit,
            offset=offset,
            sort=str(sort or "amount_desc"),
        )

    # ---- Territory filter on Sales Invoice.territory (Access Profile scope) ----
    territory_join = ""
    territory_filter, territory_params = si_territory_sql(scope, field="si.territory")
    # customer list uses same field without alias in some fragments
    cust_terr_filter, cust_terr_params = si_territory_sql(scope, field="si.territory")

    # ---- KPIs ----
    # total_unpaid: net of invoices and returns (can be negative if overall credit)
    total_unpaid_query = f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) AS total_unpaid
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
          AND si.company = %s
          {territory_filter}
    """

    # total_overdue: only amounts customers OWE (credits should not reduce this KPI)
    total_overdue_query = f"""
        SELECT COALESCE(SUM(GREATEST(si.outstanding_amount, 0)), 0) AS total_overdue
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
          AND COALESCE(si.due_date, si.posting_date) < CURDATE()
          AND si.company = %s
          {territory_filter}
    """

    # aging summary: returns (negative) deduct from buckets
    aging_summary_query = f"""
        SELECT
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) >= CURDATE()
                    THEN si.outstanding_amount ELSE 0
                END) AS current,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 1 AND 30
                    THEN si.outstanding_amount ELSE 0
                END) AS d1_30,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 31 AND 60
                    THEN si.outstanding_amount ELSE 0
                END) AS d31_60,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 61 AND 90
                    THEN si.outstanding_amount ELSE 0
                END) AS d61_90,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 91 AND 120
                    THEN si.outstanding_amount ELSE 0
                END) AS d91_120,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) > 120
                    THEN si.outstanding_amount ELSE 0
                END) AS old_balance
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
          AND si.company = %s
          {territory_filter}
    """

    # ---- Sorting for customers ----
    if str(sort).lower() == "amount_asc":
        sort_clause = "SUM(si.outstanding_amount) ASC"
    elif str(sort).lower() == "name_asc":
        sort_clause = "customer_name ASC"
    else:
        sort_clause = "SUM(si.outstanding_amount) DESC"

    # ---- Customers list (include returns; filter by ABS(net) <> threshold) ----
    customers_query = f"""
        SELECT
            si.customer,
            COALESCE(MAX(c.customer_name), si.customer) AS customer_name,
            SUM(si.outstanding_amount) AS total_outstanding,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) >= CURDATE()
                    THEN si.outstanding_amount ELSE 0
                END) AS current,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 1 AND 30
                    THEN si.outstanding_amount ELSE 0
                END) AS d1_30,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 31 AND 60
                    THEN si.outstanding_amount ELSE 0
                END) AS d31_60,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 61 AND 90
                    THEN si.outstanding_amount ELSE 0
                END) AS d61_90,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) BETWEEN 91 AND 120
                    THEN si.outstanding_amount ELSE 0
                END) AS d91_120,
            SUM(CASE
                    WHEN COALESCE(si.due_date, si.posting_date) < CURDATE()
                     AND DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) > 120
                    THEN si.outstanding_amount ELSE 0
                END) AS old_balance
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.company = %s
          {cust_terr_filter}
        GROUP BY si.customer
        HAVING ABS(ROUND(SUM(si.outstanding_amount), 2)) {cmp_op} %s
        ORDER BY {sort_clause}
        LIMIT %s OFFSET %s
    """

    # ---- Count (match same HAVING) ----
    count_query = f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT si.customer
            FROM `tabSales Invoice` si
            LEFT JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1
              AND si.company = %s
              {cust_terr_filter}
            GROUP BY si.customer
            HAVING ABS(ROUND(SUM(si.outstanding_amount), 2)) {cmp_op} %s
        ) _x
    """

    # ---- Execute ----
    base_params = [company] + territory_params
    total_unpaid = (frappe.db.sql(total_unpaid_query, base_params, as_dict=True)[0] or {}).get("total_unpaid", 0) or 0
    total_overdue = (frappe.db.sql(total_overdue_query, base_params, as_dict=True)[0] or {}).get("total_overdue", 0) or 0
    aging_summary = (frappe.db.sql(aging_summary_query, base_params, as_dict=True)[0]) or {}

    list_params = [company] + cust_terr_params + [amount_threshold, limit, offset]
    customers = frappe.db.sql(customers_query, list_params, as_dict=True) or []

    count_params = [company] + cust_terr_params + [amount_threshold]
    total_count = (frappe.db.sql(count_query, count_params, as_dict=True)[0] or {}).get("total", 0) or 0

    # ---- Shape response ----
    return {
        "territory": final_territory,
        "territories": scope or [],
        "summary": {
            # net of invoices & returns
            "totalUnpaid": float(total_unpaid),
            # only positive overdue
            "totalOverdue": float(total_overdue),
            "aging": {
                "Current":     float(aging_summary.get("current", 0) or 0),
                "1-30 Days":   float(aging_summary.get("d1_30", 0) or 0),
                "31-60 Days":  float(aging_summary.get("d31_60", 0) or 0),
                "61-90 Days":  float(aging_summary.get("d61_90", 0) or 0),
                "91-120 Days": float(aging_summary.get("d91_120", 0) or 0),
                "Old Balance": float(aging_summary.get("old_balance", 0) or 0),
            },
        },
        "customers": [
            {
                "customer": r["customer"],
                "customer_name": r["customer_name"],
                "outstanding_amount": float(r["total_outstanding"] or 0),
                "aging": {
                    "Current":     float(r["current"] or 0),
                    "1-30 Days":   float(r["d1_30"] or 0),
                    "31-60 Days":  float(r["d31_60"] or 0),
                    "61-90 Days":  float(r["d61_90"] or 0),
                    "91-120 Days": float(r["d91_120"] or 0),
                    "Old Balance": float(r["old_balance"] or 0),
                },
            } for r in customers
        ],
        "pagination": {"total": int(total_count), "limit": limit, "offset": offset},
        "filters_applied": {"amount_cmp": cmp_op, "amount_threshold": amount_threshold}
    }

    """
    Territory details: summary KPIs and customers with outstanding and aging breakdown.
    Called via: /api/method/erp_analysis.receivables.get_territory_receivables
    """
    # --- Resolve user territory (optional access control) ---
    try:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    except Exception:
        employee = None

    user_territory = frappe.db.get_value("Employee", employee, "branch") if employee else None

    final_territory = territory or user_territory
    if territory and user_territory and territory != user_territory:
        frappe.throw("Access denied: You don't have permission to view this territory")

    # --- Defaults / pagination ---
    company = company or frappe.defaults.get_user_default("Company")
    try:
        limit = int(limit) if limit else 50
        offset = int(offset) if offset else 0
    except Exception:
        limit, offset = 50, 0

    # --- Territory join/filter (optional) ---
    territory_join = ""
    territory_filter = ""
    territory_params = []
    if final_territory:
        territory_join = "INNER JOIN `tabCustomer` c ON c.name = si.customer"
        territory_filter = "AND c.territory = %s"
        territory_params = [final_territory]

    # --- KPI queries ---
    total_unpaid_query = f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) AS total_unpaid
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.company = %s
          {territory_filter}
    """

    total_overdue_query = f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) AS total_overdue
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date < CURDATE()
          AND si.company = %s
          {territory_filter}
    """

    aging_summary_query = f"""
        SELECT
            SUM(CASE WHEN si.due_date >= CURDATE() THEN si.outstanding_amount ELSE 0 END)                                           AS current,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN  1 AND  30 THEN si.outstanding_amount ELSE 0 END) AS d1_30,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 31 AND  60 THEN si.outstanding_amount ELSE 0 END) AS d31_60,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 61 AND  90 THEN si.outstanding_amount ELSE 0 END) AS d61_90,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 91 AND 120 THEN si.outstanding_amount ELSE 0 END) AS d91_120,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) > 120 THEN si.outstanding_amount ELSE 0 END)              AS old_balance
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.company = %s
          {territory_filter}
    """

    # --- Sort clause for customers list ---
    if sort == "amount_asc":
        sort_clause = "SUM(si.outstanding_amount) ASC"
    elif sort == "name_asc":
        sort_clause = "customer_name ASC"
    else:
        sort_clause = "SUM(si.outstanding_amount) DESC"  # default

    customers_query = f"""
        SELECT
            si.customer,
            COALESCE(MAX(c.customer_name), si.customer) AS customer_name,
            SUM(si.outstanding_amount)                 AS total_outstanding,
            SUM(CASE WHEN si.due_date >= CURDATE() THEN si.outstanding_amount ELSE 0 END)                                           AS current,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN  1 AND  30 THEN si.outstanding_amount ELSE 0 END) AS d1_30,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 31 AND  60 THEN si.outstanding_amount ELSE 0 END) AS d31_60,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 61 AND  90 THEN si.outstanding_amount ELSE 0 END) AS d61_90,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 91 AND 120 THEN si.outstanding_amount ELSE 0 END) AS d91_120,
            SUM(CASE WHEN si.due_date <  CURDATE() AND DATEDIFF(CURDATE(), si.due_date) > 120 THEN si.outstanding_amount ELSE 0 END)              AS old_balance
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.company = %s
          {('AND c.territory = %s' if final_territory else '')}
        GROUP BY si.customer
        ORDER BY {sort_clause}
        LIMIT %s OFFSET %s
    """

    count_query = f"""
        SELECT COUNT(DISTINCT si.customer) AS total
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.company = %s
          {('AND c.territory = %s' if final_territory else '')}
    """

    # --- Execute safely with positional params ---
    base_params = [company] + territory_params
    total_unpaid   = (frappe.db.sql(total_unpaid_query,   base_params, as_dict=True)[0] or {}).get("total_unpaid", 0) or 0
    total_overdue  = (frappe.db.sql(total_overdue_query,  base_params, as_dict=True)[0] or {}).get("total_overdue", 0) or 0
    aging_summary  = (frappe.db.sql(aging_summary_query,  base_params, as_dict=True)[0]) or {}

    list_params = [company] + ([final_territory] if final_territory else []) + [limit, offset]
    customers   = frappe.db.sql(customers_query, list_params, as_dict=True) or []

    count_params = [company] + ([final_territory] if final_territory else [])
    total_count  = (frappe.db.sql(count_query, count_params, as_dict=True)[0] or {}).get("total", 0) or 0

    return {
        "territory": final_territory,
        "summary": {
            "totalUnpaid": float(total_unpaid),
            "totalOverdue": float(total_overdue),
            "aging": {
                "Current":    float(aging_summary.get("current", 0) or 0),
                "1-30 Days":  float(aging_summary.get("d1_30", 0) or 0),
                "31-60 Days": float(aging_summary.get("d31_60", 0) or 0),
                "61-90 Days": float(aging_summary.get("d61_90", 0) or 0),
                "91-120 Days":float(aging_summary.get("d91_120", 0) or 0),
                "Old Balance":float(aging_summary.get("old_balance", 0) or 0),
            },
        },
        "customers": [
            {
                "customer": r["customer"],
                "customer_name": r["customer_name"],
                "outstanding_amount": float(r["total_outstanding"] or 0),
                "aging": {
                    "Current":    float(r["current"] or 0),
                    "1-30 Days":  float(r["d1_30"] or 0),
                    "31-60 Days": float(r["d31_60"] or 0),
                    "61-90 Days": float(r["d61_90"] or 0),
                    "91-120 Days":float(r["d91_120"] or 0),
                    "Old Balance":float(r["old_balance"] or 0),
                },
            } for r in customers
        ],
        "pagination": {"total": int(total_count), "limit": limit, "offset": offset},
    }

    """
    Territory details: summary KPIs and customers with outstanding and aging breakdown
    """
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    user_territory = frappe.db.get_value("Employee", employee, "branch") if employee else None

    if territory and user_territory and territory != user_territory:
        frappe.throw("Access denied: You don't have permission to view this territory")

    company = company or frappe.defaults.get_user_default("Company")
    limit = int(limit) or 50
    offset = int(offset) or 0

    territory_join = ""
    territory_filter = ""
    territory_params = []
    final_territory = territory or user_territory
    if final_territory:
        territory_join = """
        INNER JOIN `tabCustomer` c ON c.name = si.customer
        """
        territory_filter = """
        AND c.territory = %s
        """
        territory_params = [final_territory]

    total_unpaid_query = f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) as total_unpaid
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
        AND si.outstanding_amount > 0
        AND si.company = %s
        {territory_filter}
    """

    total_overdue_query = f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) as total_overdue
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
        AND si.outstanding_amount > 0
        AND si.due_date < CURDATE()
        AND si.company = %s
        {territory_filter}
    """

    aging_summary_query = f"""
        SELECT
            SUM(CASE WHEN si.due_date >= CURDATE() THEN si.outstanding_amount ELSE 0 END) as current,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 1 AND 30 THEN si.outstanding_amount ELSE 0 END) as d1_30,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 31 AND 60 THEN si.outstanding_amount ELSE 0 END) as d31_60,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 61 AND 90 THEN si.outstanding_amount ELSE 0 END) as d61_90,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 91 AND 120 THEN si.outstanding_amount ELSE 0 END) as d91_120,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) > 120 THEN si.outstanding_amount ELSE 0 END) as old_balance
        FROM `tabSales Invoice` si
        {territory_join}
        WHERE si.docstatus = 1
        AND si.outstanding_amount > 0
        AND si.company = %s
        {territory_filter}
    """

    sort_clause = "SUM(si.outstanding_amount) DESC" if sort == "amount_desc" else (
        "SUM(si.outstanding_amount) ASC" if sort == "amount_asc" else "c.customer_name ASC"
    )

    customers_query = f"""
        SELECT
            si.customer,
            COALESCE(MAX(c.customer_name), si.customer) as customer_name,
            SUM(si.outstanding_amount) as total_outstanding,
            SUM(CASE WHEN si.due_date >= CURDATE() THEN si.outstanding_amount ELSE 0 END) as current,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 1 AND 30 THEN si.outstanding_amount ELSE 0 END) as d1_30,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 31 AND 60 THEN si.outstanding_amount ELSE 0 END) as d31_60,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 61 AND 90 THEN si.outstanding_amount ELSE 0 END) as d61_90,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) BETWEEN 91 AND 120 THEN si.outstanding_amount ELSE 0 END) as d91_120,
            SUM(CASE WHEN si.due_date < CURDATE() AND DATEDIFF(CURDATE(), si.due_date) > 120 THEN si.outstanding_amount ELSE 0 END) as old_balance
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
        AND si.outstanding_amount > 0
        AND si.company = %s
        {('AND c.territory = %s' if final_territory else '')}
        GROUP BY si.customer
        ORDER BY {sort_clause}
        LIMIT %s OFFSET %s
    """

    count_query = f"""
        SELECT COUNT(DISTINCT si.customer) as total
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
        AND si.outstanding_amount > 0
        AND si.company = %s
        {('AND c.territory = %s' if final_territory else '')}
    """

    base_params = [company] + territory_params
    total_unpaid = frappe.db.sql(total_unpaid_query, base_params, as_dict=True)[0].total_unpaid
    total_overdue = frappe.db.sql(total_overdue_query, base_params, as_dict=True)[0].total_overdue
    aging_summary = frappe.db.sql(aging_summary_query, base_params, as_dict=True)[0]

    list_params = [company] + ([final_territory] if final_territory else []) + [limit, offset]
    customers = frappe.db.sql(customers_query, list_params, as_dict=True)
    total_count = frappe.db.sql(count_query, [company] + ([final_territory] if final_territory else []), as_dict=True)[0].total

    return {
        "territory": final_territory,
        "summary": {
            "totalUnpaid": float(total_unpaid) if total_unpaid else 0.0,
            "totalOverdue": float(total_overdue) if total_overdue else 0.0,
            "aging": {
                "Current": float(aging_summary.current or 0),
                "1-30 Days": float(aging_summary.d1_30 or 0),
                "31-60 Days": float(aging_summary.d31_60 or 0),
                "61-90 Days": float(aging_summary.d61_90 or 0),
                "91-120 Days": float(aging_summary.d91_120 or 0),
                "Old Balance": float(aging_summary.old_balance or 0),
            },
        },
        "customers": [
            {
                "customer": row.customer,
                "customer_name": row.customer_name,
                "outstanding_amount": float(row.total_outstanding or 0),
                "aging": {
                    "Current": float(row.current or 0),
                    "1-30 Days": float(row.d1_30 or 0),
                    "31-60 Days": float(row.d31_60 or 0),
                    "61-90 Days": float(row.d61_90 or 0),
                    "91-120 Days": float(row.d91_120 or 0),
                    "Old Balance": float(row.old_balance or 0),
                },
            }
            for row in customers
        ],
        "pagination": {"total": int(total_count or 0), "limit": limit, "offset": offset},
    }
    
    
@frappe.whitelist()
def get_customer_statement(company=None, customer=None, from_date=None, to_date=None):
    """
    Build a lightweight customer statement preview (HTML + items) to show in mobile app
    """
    if not customer:
        frappe.throw("Customer is required")

    company = company or frappe.defaults.get_user_default("Company")

    # Profile users: only customers in allowed territories
    cust_territory = frappe.db.get_value("Customer", customer, "territory")
    from erp_analysis.permissions.access_profile import bypass_view_territories
    if not bypass_view_territories("receivables", company=company):
        assert_document_territory_allowed(cust_territory, company=company, purpose="view")

    # Default date range: last 90 days
    if not to_date:
        to_date = frappe.utils.nowdate()
    if not from_date:
        year = frappe.utils.getdate(to_date).year
        from_date =  f"{year}-01-01"

    # Fetch open invoices in range
    invoices_query = """
        SELECT
            si.name as invoice,
            si.posting_date,
            si.due_date,
            si.base_grand_total,
            si.outstanding_amount
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.customer = %s
          AND si.company = %s
          AND si.posting_date BETWEEN %s AND %s
        ORDER BY si.posting_date ASC
    """

    rows = frappe.db.sql(invoices_query, [customer, company, from_date, to_date], as_dict=True)

    total_invoice = sum((r.base_grand_total or 0) for r in rows)
    total_outstanding = sum((r.outstanding_amount or 0) for r in rows)

    def fmt(n):
        return frappe.utils.fmt_money(n or 0, currency=frappe.db.get_value("Company", company, "default_currency"))

    html_parts = [
        "<div style='font-family:Inter, Arial; padding:12px'>",
        (
            "<h3 style='margin:0 0 8px 0'>Statement of Account</h3>"
            f"<div style='color:#6b7280;font-size:13px'>Customer: <b>{frappe.utils.escape_html(customer)}</b></div>"
            f"<div style='color:#6b7280;font-size:13px'>Period: {from_date} to {to_date}</div>"
        ),
        f"<div style='margin-top:12px;padding:12px;background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px'>"
        f"<div style='display:flex;justify-content:space-between'><div>Total Invoiced</div><b>{fmt(total_invoice)}</b></div>"
        f"<div style='display:flex;justify-content:space-between;margin-top:6px'><div>Total Outstanding</div><b>{fmt(total_outstanding)}</b></div>"
        f"</div>",
        "<table style='width:100%;margin-top:12px;border-collapse:collapse'>",
        "<thead><tr style='background:#F3F4F6'>"
        "<th style='text-align:left;padding:8px;font-size:12px;color:#6b7280'>Invoice</th>"
        "<th style='text-align:left;padding:8px;font-size:12px;color:#6b7280'>Posting</th>"
        "<th style='text-align:left;padding:8px;font-size:12px;color:#6b7280'>Due</th>"
        "<th style='text-align:right;padding:8px;font-size:12px;color:#6b7280'>Amount</th>"
        "<th style='text-align:right;padding:8px;font-size:12px;color:#6b7280'>Outstanding</th>"
        "</tr></thead><tbody>",
    ]

    for r in rows:
        html_parts.append(
            """
            <tr style='border-bottom:1px solid #E5E7EB'>
              <td style='padding:8px'>%s</td>
              <td style='padding:8px'>%s</td>
              <td style='padding:8px'>%s</td>
              <td style='padding:8px;text-align:right'>%s</td>
              <td style='padding:8px;text-align:right'>%s</td>
            </tr>
            """
            % (
                frappe.utils.escape_html(r.invoice),
                frappe.utils.formatdate(r.posting_date),
                frappe.utils.formatdate(r.due_date),
                fmt(r.base_grand_total),
                fmt(r.outstanding_amount),
            )
        )

    html_parts.append("</tbody></table></div>")

    from erp_analysis.services.statement_branding import build_statement_branding, wrap_mobile_message

    branding = build_statement_branding(company, customer)
    payload = {
        "customer": customer,
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "total_invoiced": float(total_invoice or 0),
        "total_outstanding": float(total_outstanding or 0),
        "items": [
            {
                "invoice": r.invoice,
                "posting_date": str(r.posting_date),
                "due_date": str(r.due_date),
                "amount": float(r.base_grand_total or 0),
                "outstanding": float(r.outstanding_amount or 0),
            }
            for r in rows
        ],
        "html": "".join(html_parts),
        "branding": branding,
        **branding,
    }
    return wrap_mobile_message(payload)


@frappe.whitelist(allow_guest=False, methods=["GET", "POST"])
def get_statement_branding(company=None, customer=None, customer_name=None, **kwargs):
    """Alias for mobile — same branding as ``customer_notifications.get_statement_branding``."""
    from erp_analysis.services.statement_branding import build_statement_branding, wrap_mobile_message

    customer = customer or customer_name or _get_arg("customer") or _get_arg("customer_name")
    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    if customer:
        cust_territory = frappe.db.get_value("Customer", customer, "territory")
        from erp_analysis.permissions.access_profile import bypass_view_territories

        if not bypass_view_territories("receivables", company=company):
            assert_document_territory_allowed(cust_territory, company=company, purpose="view")
    return wrap_mobile_message(build_statement_branding(company, customer))