"""Mobile dashboard APIs — KPIs, charts, and aggregated home screen data."""

import frappe
from frappe import _
from datetime import datetime, timedelta
import json

from erp_analysis.profile import build_user_profile_data
from erp_analysis.permissions.access_profile import (
	resolve_territory_scope,
	si_territory_sql,
)


def _profile_territory_sql(company=None, field="territory", module="sales"):
	"""SQL fragment + params for Access Profile territory scope (no-op for non-profile users)."""
	scope = resolve_territory_scope(company=company, purpose="view", module=module)
	return si_territory_sql(scope, field=field)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_complete_dashboard_data(company=None, from_date=None, to_date=None):
    """
    Get complete dashboard data in a single API call
    
    Parameters:
    - company: Company filter (optional)
    - from_date: Start date filter (optional)
    - to_date: End date filter (optional)
    
    Returns:
    - Complete dashboard data including KPIs, charts, user profile, and date
    """
    try:
        # Set default date range if not provided
        if not from_date:
            from_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        if not to_date:
            to_date = datetime.now().strftime('%Y-%m-%d')
            
        # Get current user
        current_user = frappe.get_user()
        
        # 1. Get KPIs
        kpis = get_dashboard_kpis(company, from_date, to_date)
        
        # 2. Get Charts data
        charts = get_dashboard_charts(company, from_date, to_date)
        
        # 3. Get User Profile data
        user_profile = get_user_profile_data(current_user.name)
        
        # 4. Get Sales Dashboard data (NEW)
        sales_dashboard = get_sales_dashboard_data(company, from_date, to_date)
        
        # 5. Prepare response
        response = {
            "kpis": kpis,
            "charts": charts,
            "user_profile": user_profile,
            "sales_dashboard": sales_dashboard,  # NEW: Sales Dashboard data
            "date": datetime.now().strftime('%A, %B %d, %Y'),
            "from_date": from_date,
            "to_date": to_date
        }
        
        return response
        
    except Exception as e:
        frappe.log_error(f"Dashboard API Error: {str(e)}")
        frappe.throw(_("Error fetching dashboard data: {0}").format(str(e)))
        
@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_dashboard_kpis(company, from_date, to_date):
    """Get KPI data for dashboard"""
    try:
        # Sales Today
        sales_today = get_sales_today(company=None)
        # Sales MTD
        sales_mtd = get_sales_mtd(company, from_date, to_date)
        
        # Sales YTD  
        sales_ytd = get_sales_ytd(company, from_date, to_date)
        
        # Gross Margin
        gross_margin = get_gross_margin(company, from_date, to_date)
        
        return [
            {
                "id": "sales_today",
                "title": "SALES Today",
                "value": sales_today["amount"],
                "change_percentage": sales_today["change_percentage"],
                "change_direction": "up" if sales_today["change_percentage"] > 0 else "down",
                "currency": "SAR"
            },
            {
                "id": "sales_mtd",
                "title": "SALES MTD",
                "value": sales_mtd["amount"],
                "change_percentage": sales_mtd["change_percentage"],
                "change_direction": "up" if sales_mtd["change_percentage"] > 0 else "down",
                "currency": "SAR"
            },
            {
                "id": "sales_ytd",
                "title": "SALES YTD", 
                "value": sales_ytd["amount"],
                "change_percentage": sales_ytd["change_percentage"],
                "change_direction": "up" if sales_ytd["change_percentage"] > 0 else "down",
                "currency": "SAR"
            },
            {
                "id": "gross_margin",
                "title": "GROSS MARGIN",
                "value": gross_margin["percentage"],
                "change_percentage": gross_margin["change_percentage"],
                "change_direction": "up" if gross_margin["change_percentage"] > 0 else "down",
                "unit": "%"
            }
        ]
    except Exception as e:
        frappe.log_error(f"KPI Error: {str(e)}")
        return []


import frappe
from frappe import _
from frappe.utils import today
from datetime import datetime

@frappe.whitelist()
@frappe.read_only()
def get_sales_today(company=None):
    """
    Calculate today's sales and compare with the same day last year.
    """
    try:
        # Determine today
        day_today = today()

        # Same date last year
        current_dt = datetime.strptime(day_today, "%Y-%m-%d")
        last_year_dt = current_dt.replace(year=current_dt.year - 1)
        day_last_year = last_year_dt.strftime("%Y-%m-%d")

        # Build optional company + Access Profile territory filters
        company_clause = " AND company = %s" if company else ""
        terr_sql, terr_params = _profile_territory_sql(company, field="territory")
        args_today = [day_today, day_today] + ([company] if company else []) + terr_params
        args_last_year = [day_last_year, day_last_year] + ([company] if company else []) + terr_params

        # Base SQL
        sql = f"""
            SELECT COALESCE(SUM(net_total), 0) AS amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1
              AND posting_date >= %s
              AND posting_date <= %s
              {company_clause}
              {terr_sql}
        """

        current_sales = frappe.db.sql(sql, args_today, as_dict=True)[0].amount or 0
        prev_sales = frappe.db.sql(sql, args_last_year, as_dict=True)[0].amount or 0

        change_percentage = ((current_sales - prev_sales) / prev_sales * 100.0) if prev_sales > 0 else 0.0

        return {
            "amount": float(current_sales),
            "change_percentage": round(change_percentage, 1)
        }

    except Exception:
        frappe.log_error(f"Sales Today Error: {frappe.get_traceback()}")
        return {"amount": 0, "change_percentage": 0}


def get_sales_mtd(company, from_date, to_date):
    """Calculate Sales Month to Date"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="territory")
        company_filter = f"AND company = %s" if company else ""
        # Current month sales
        current_month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        args_cur = [current_month_start, to_date] + ([company] if company else []) + terr_params
        current_sales = frappe.db.sql(f"""
            SELECT COALESCE(SUM(net_total), 0) as amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
            AND posting_date >= %s
            AND posting_date <= %s
            {company_filter}
            {terr_sql}
        """, args_cur, as_dict=True)
        
        # Previous month sales for comparison
        prev_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')
        prev_month_end = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
        args_prev = [prev_month_start, prev_month_end] + ([company] if company else []) + terr_params
        
        prev_sales = frappe.db.sql(f"""
            SELECT COALESCE(SUM(net_total), 0) as amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
            AND posting_date >= %s
            AND posting_date <= %s
            {company_filter}
            {terr_sql}
        """, args_prev, as_dict=True)
        
        current_amount = current_sales[0].amount if current_sales else 0
        prev_amount = prev_sales[0].amount if prev_sales else 0
        
        change_percentage = ((current_amount - prev_amount) / prev_amount * 100) if prev_amount > 0 else 0
        
        return {
            "amount": current_amount,
            "change_percentage": round(change_percentage, 1)
        }
        
    except Exception as e:
        frappe.log_error(f"Sales MTD Error: {str(e)}")
        return {"amount": 0, "change_percentage": 0}

def get_sales_ytd(company, from_date, to_date):
    """Calculate Sales Year to Date"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="territory")
        company_filter = "AND company = %s" if company else ""
        # Current year sales
        current_year_start = datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
        args_cur = [current_year_start, to_date] + ([company] if company else []) + terr_params
        current_sales = frappe.db.sql(f"""
            SELECT COALESCE(SUM(net_total), 0) as amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
            AND posting_date >= %s
            AND posting_date <= %s
            {company_filter}
            {terr_sql}
        """, args_cur, as_dict=True)
        
        # Previous year sales for comparison
        prev_year_start = datetime.now().replace(year=datetime.now().year-1, month=1, day=1).strftime('%Y-%m-%d')
        prev_year_end = datetime.now().replace(year=datetime.now().year-1, month=12, day=31).strftime('%Y-%m-%d')
        args_prev = [prev_year_start, prev_year_end] + ([company] if company else []) + terr_params
        
        prev_sales = frappe.db.sql(f"""
            SELECT COALESCE(SUM(net_total), 0) as amount
            FROM `tabSales Invoice`
            WHERE docstatus = 1 
            AND posting_date >= %s
            AND posting_date <= %s
            {company_filter}
            {terr_sql}
        """, args_prev, as_dict=True)
        
        current_amount = current_sales[0].amount if current_sales else 0
        prev_amount = prev_sales[0].amount if prev_sales else 0
        
        change_percentage = ((current_amount - prev_amount) / prev_amount * 100) if prev_amount > 0 else 0
        
        return {
            "amount": current_amount,
            "change_percentage": round(change_percentage, 1)
        }
        
    except Exception as e:
        frappe.log_error(f"Sales YTD Error: {str(e)}")
        return {"amount": 0, "change_percentage": 0}

@frappe.whitelist()
def get_gross_margin(company, from_date, to_date):
    """Calculate Gross Margin"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        # Get sales and cost of goods sold
        sales_data = frappe.db.sql(f"""
            SELECT 
                COALESCE(SUM(net_amount), 0) as total_sales,
                COALESCE(SUM(cogs), 0) as total_cost
            FROM `tabSalesDashBoard`
            WHERE
            Invoice_Date >= %s AND Invoice_Date <= %s
            {terr_sql}
        """, [from_date, to_date] + terr_params, as_dict=True)
        
        if sales_data:
            total_sales = sales_data[0].total_sales
            total_cost = sales_data[0].total_cost
            
            gross_profit = total_sales - total_cost
            gross_margin_percentage = (gross_profit / total_sales * 100) if total_sales > 0 else 0
            
            return {
                "percentage": round(gross_margin_percentage, 1),
                "change_percentage": 2.1  # You can calculate this based on previous period
            }
        
        return {"percentage": 0, "change_percentage": 0}
        
    except Exception as e:
        frappe.log_error(f"Gross Margin Error: {str(e)}")
        return {"percentage": 0, "change_percentage": 0}

@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_dashboard_charts(company, from_date, to_date):
	try:
		return {
			"sales_daily": get_daily_sales_chart(company, from_date, to_date),
			"sales_by_territory": get_sales_by_territory_chart(company, from_date, to_date),
			"sales_by_division": get_sales_by_division_chart(company, from_date, to_date),
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Charts Error")
		return {"sales_daily": [], "sales_by_territory": [], "sales_by_division": []}

@frappe.whitelist()
def get_daily_sales_chart(company, from_date, to_date):
	try:
		params = [from_date, to_date]
		company_sql = ""
		if company:
			company_sql = " AND company = %s"
			params.append(company)
		terr_sql, terr_params = _profile_territory_sql(company, field="territory")
		params.extend(terr_params)

		rows = frappe.db.sql(f"""
			SELECT 
				DATE(posting_date) AS date,
				COALESCE(SUM(net_total), 0) AS value
			FROM `tabSales Invoice`
			WHERE docstatus = 1
			  AND posting_date >= %s
			  AND posting_date <= %s
			  {company_sql}
			  {terr_sql}
			GROUP BY DATE(posting_date)
			ORDER BY date ASC
		""", params, as_dict=True)

		return [
			{
				"date": (r.date.strftime("%Y-%m-%d") if hasattr(r.date, "strftime") else str(r.date)),
				"value": float(r.value or 0),
			}
			for r in rows
		]
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Daily Sales Error")
		return []

@frappe.whitelist()
def get_sales_by_territory_chart(company, from_date, to_date):
    try:
        params, company_sql = [from_date, to_date], ""
        if company:
            company_sql = " AND company = %s"
            params.append(company)
        terr_sql, terr_params = _profile_territory_sql(company, field="territory")
        params.extend(terr_params)

        rows = frappe.db.sql(f"""
            SELECT 
                COALESCE(territory, 'No Territory') AS territory,
                COALESCE(SUM(net_total), 0) AS value
            FROM `tabSales Invoice`
            WHERE docstatus = 1
              AND posting_date >= %s
              AND posting_date <= %s
              {company_sql}
              {terr_sql}
            GROUP BY territory
            ORDER BY value DESC
            LIMIT 10
        """, params, as_dict=True)

        total = sum(float(r.value or 0) for r in rows) or 1
        return [
            {
                "territory": r.territory,
                "value": float(r.value or 0),
                "percentage": round(float(r.value or 0) / total * 100, 1),
            }
            for r in rows
        ]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Territory Chart Error")
        return []

@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_sales_by_division_chart(company, from_date, to_date):
    try:
        # Set to True if Invoice_Date is stored as text like 'YYYY-MM-DD'
        INVOICE_DATE_IS_STRING = True
        DATE_MASK = "%Y-%m-%d"

        date_expr = (
            f"STR_TO_DATE(`Invoice_Date`, '{DATE_MASK}')"
            if INVOICE_DATE_IS_STRING else
            "`Invoice_Date`"
        )

        params = [from_date, to_date]
        company_sql = ""
        if company:
            company_sql = " AND `Company` = %s"   # exact field name on SalesDashBoard
            params.append(company)
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        params.extend(terr_params)

        rows = frappe.db.sql(f"""
            SELECT 
                COALESCE(`Division`, 'No Division') AS division,
                COALESCE(SUM(`Net_Amount`), 0)      AS value
            FROM `tabSalesDashBoard`
            WHERE {date_expr} >= %s
              AND {date_expr} <= %s
              {company_sql}
              {terr_sql}
            GROUP BY COALESCE(`Division`, 'No Division')
            ORDER BY value DESC
            LIMIT 10
        """, params, as_dict=True)

        total = sum(float(r.value or 0) for r in rows) or 1.0
        return [
            {
                "division": r.division,
                "value": float(r.value or 0),
                "percentage": round(float(r.value or 0) / total * 100.0, 1),
            }
            for r in rows
        ]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Division Chart Error")
        return []
@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_user_profile_data(username):
	"""Get complete user & employee profile data for dashboard."""
	return build_user_profile_data(username)


# ========== SALES DASHBOARD API ==========

@frappe.whitelist()
def get_sales_dashboard_data(company, from_date, to_date):
    """
    Get complete sales dashboard data including:
    - Sales metrics (total sales, invoices, avg invoice, COGS, profit, margin)
    - Top 10 Brands
    - Top 10 Customers
    - Monthly sales trend (current year vs previous year)
    - Territory breakdown
    - Division breakdown
    """
    try:
        # 1. Get Sales Metrics
        metrics = get_sales_metrics(company, from_date, to_date)
        
        # 2. Get Top 10 Brands
        top_brands = get_top_brands(company, from_date, to_date)
        
        # 3. Get Top 10 Customers
        top_customers = get_top_customers(company, from_date, to_date)
        
        # 4. Get Monthly Trend
        monthly_trend = get_monthly_sales_trend(company)
        
        # 5. Get Territory Breakdown
        territory = get_territory_breakdown(company, from_date, to_date)
        
        # 6. Get Division Breakdown
        division = get_division_breakdown(company, from_date, to_date)
        
        return {
            "metrics": metrics,
            "top_brands": top_brands,
            "top_customers": top_customers,
            "monthly_trend": monthly_trend,
            "territory": territory,
            "division": division
        }
        
    except Exception as e:
        frappe.log_error(f"Sales Dashboard API Error: {str(e)}")
        return {
            "metrics": None,
            "top_brands": [],
            "top_customers": [],
            "monthly_trend": {},
            "territory": [],
            "division": []
        }

def get_sales_metrics(company, from_date, to_date):
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        metrics_sql = f"""
            SELECT 
                COALESCE(SUM(Net_Amount), 0) AS total_sales,
                COALESCE(SUM(COGS), 0) AS cost_of_goods_sold,
                COALESCE(COUNT(DISTINCT Invoice_No), 0) AS total_invoices
            FROM `tabSalesDashBoard`
            WHERE Invoice_Date >= %s
              AND Invoice_Date <= %s
              {terr_sql}
        """
        sales_data = frappe.db.sql(metrics_sql, [from_date, to_date] + terr_params, as_dict=True)

        if sales_data:
            total_sales = float(sales_data[0].total_sales or 0)
            cogs = float(sales_data[0].cost_of_goods_sold or 0)
            invoices = int(sales_data[0].total_invoices or 0)

            gross_profit = total_sales - cogs
            gross_profit_pct = (gross_profit / total_sales * 100) if total_sales > 0 else 0
            avg_invoice = (total_sales / invoices) if invoices > 0 else 0

            return {
                "totalSales": round(total_sales, 2),
                "totalInvoices": invoices,
                "avgInvoiceValue": round(avg_invoice, 2),
                "costOfGoodsSold": round(cogs, 2),
                "grossProfit": round(gross_profit, 2),
                "grossProfitPercentage": round(gross_profit_pct, 2),
            }
        return None

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Sales Metrics Error")
        return None

def get_monthly_sales_trend(company):
    """Get monthly sales trend for current and previous year"""
    try:
        current_year = datetime.now().year
        previous_year = current_year - 1

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # Invoice_Date is a DATE field, not string - simplified query
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        sql = f"""
            SELECT
                YEAR(Invoice_Date) AS y,
                MONTH(Invoice_Date) AS m,
                COALESCE(SUM(Net_Amount), 0) AS total_sales
            FROM `tabSalesDashBoard`
            WHERE Invoice_Date IS NOT NULL
              AND YEAR(Invoice_Date) IN (%s, %s)
              {terr_sql}
            GROUP BY YEAR(Invoice_Date), MONTH(Invoice_Date)
            ORDER BY y, m
        """

        rows = frappe.db.sql(sql, [previous_year, current_year] + terr_params, as_dict=True)

        current = [0.0] * 12
        previous = [0.0] * 12

        for r in rows:
            if not r.m or r.m < 1 or r.m > 12:
                continue
            value = round(float(r.total_sales or 0), 2)
            if r.y == current_year:
                current[r.m - 1] = value
            elif r.y == previous_year:
                previous[r.m - 1] = value

        return {"labels": months, "current": current, "previous": previous}

    except Exception:
        # Keep title short, dump full traceback in message
        frappe.log_error("Monthly Trend Error", frappe.get_traceback())
        return {
            "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            "current": [0] * 12,
            "previous": [0] * 12,
        }


def get_territory_breakdown(company, from_date, to_date):
    """Get sales breakdown by territory"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        territories = frappe.db.sql(f"""
            SELECT 
                COALESCE(Territory, 'No Territory') as territory,
                COALESCE(SUM(Net_Amount), 0) as total_sales,
                COALESCE(COUNT(DISTINCT Invoice_No), 0) as invoice_count
            FROM `tabSalesDashBoard`
            WHERE Invoice_Date >= %s
              AND Invoice_Date <= %s
              {terr_sql}
            GROUP BY Territory
            ORDER BY total_sales DESC
        """, [from_date, to_date] + terr_params, as_dict=True)
        
        result = []
        for territory in territories:
            result.append({
                "territory": territory.territory,
                "total_sales": round(float(territory.total_sales or 0), 2),
                "invoice_count": int(territory.invoice_count or 0)
            })
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Territory Breakdown Error: {str(e)}")
        return []

def get_division_breakdown(company, from_date, to_date):
    """Get sales breakdown by division"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        divisions = frappe.db.sql(f"""
            SELECT 
                COALESCE(Division, 'No Division') as division,
                COALESCE(SUM(Net_Amount), 0) as total_sales,
                COALESCE(SUM(COGS), 0) as total_cost
            FROM `tabSalesDashBoard`
            WHERE Invoice_Date >= %s
              AND Invoice_Date <= %s
              {terr_sql}
            GROUP BY Division
            ORDER BY total_sales DESC
        """, [from_date, to_date] + terr_params, as_dict=True)
        
        result = []
        for division in divisions:
            total_sales = float(division.total_sales or 0)
            total_cost = float(division.total_cost or 0)
            gross_profit = total_sales - total_cost
            margin_percentage = (gross_profit / total_sales * 100) if total_sales > 0 else 0
            
            result.append({
                "division": division.division,
                "total_sales": round(total_sales, 2),
                "margin_percentage": round(margin_percentage, 2)
            })
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Division Breakdown Error: {str(e)}")
        return []

def get_top_brands(company, from_date, to_date):
    """Get top 10 brands by sales"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        brands = frappe.db.sql(f"""

            SELECT
                COALESCE(Brand, 'No Brand')                            AS brand,
                COALESCE(SUM(Sold_Qty), 0)                              AS sold_qty,
                COALESCE(SUM(Net_Amount), 0)                            AS total_sales,
                COALESCE(SUM(cogs), 0)                            AS total_cost,
                COALESCE(COUNT(DISTINCT Invoice_No), 0)                 AS invoice_count
            FROM `tabSalesDashBoard`
            WHERE Invoice_Date >= %s
              AND Invoice_Date <= %s
              {terr_sql}
            GROUP BY Brand
            ORDER BY total_sales DESC
            LIMIT 10
        """, [from_date, to_date] + terr_params, as_dict=True)
        
        result = []
        for brand in brands:
            result.append({
                "brand": brand.brand,
                "total_sales": round(float(brand.total_sales or 0), 2),
                "total_cost": round(float(brand.total_cost or 0), 2),
                 "sold_qty": int(brand.sold_qty or 0),
                "invoice_count": int(brand.invoice_count or 0)
            })
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Top Brands Error: {str(e)}")
        return []


def get_top_customers(company, from_date, to_date):
    """Get top 10 customers by sales"""
    try:
        terr_sql, terr_params = _profile_territory_sql(company, field="Territory")
        customers = frappe.db.sql(f"""
            SELECT 
                COALESCE(Customer, 'No Customer') as customer,
                COALESCE(SUM(Net_Amount), 0) as total_sales,
                COALESCE(COUNT(DISTINCT Invoice_No), 0) as invoice_count
            FROM `tabSalesDashBoard`
            WHERE Invoice_Date >= %s
              AND Invoice_Date <= %s
              {terr_sql}
            GROUP BY Customer
            ORDER BY total_sales DESC
            LIMIT 10
        """, [from_date, to_date] + terr_params, as_dict=True)
        
        result = []
        for customer in customers:
            result.append({
                "customer": customer.customer,
                "total_sales": round(float(customer.total_sales or 0), 2),
                "invoice_count": int(customer.invoice_count or 0)
            })
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Top Customers Error: {str(e)}")
        return []


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_executive_dashboard(
	company=None,
	from_date=None,
	to_date=None,
	territory=None,
	territories=None,
	branch=None,
	**kwargs,
):
	"""Mobile contract alias for Phase 3 executive dashboard."""
	from erp_analysis.executive import get_executive_dashboard as _impl

	return _impl(
		company=company,
		from_date=from_date,
		to_date=to_date,
		territory=territory,
		territories=territories or kwargs.get("territories"),
		branch=branch,
	)
