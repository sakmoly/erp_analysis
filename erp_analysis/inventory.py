import frappe
from frappe import _
import json
from functools import lru_cache

from erp_analysis.permissions.access_profile import (
    resolve_warehouse_scope,
    warehouse_sql,
)
from erp_analysis.services.inventory_hierarchy_territory import (
    get_territory_hierarchy,
    is_territory_path,
)


def _inv_warehouse_scope(company=None, warehouse=None):
    """Access Profile warehouse scope (None = no restriction)."""
    return resolve_warehouse_scope(requested=warehouse, company=company)


def _inv_cache_key(prefix, company, warehouse, *extra):
    user = frappe.session.user or "Guest"
    parts = [prefix, user, company or "", warehouse or ""] + [str(x) for x in extra]
    return "_".join(parts)


@frappe.whitelist()
def get_inventory_snapshot(company=None, warehouse=None, fast: bool = True):
    """
    Fast inventory snapshot with KPIs.
    - Uses tabBin for current value.
    - Computes last movement only for (item, warehouse) present in tabBin.
    - Reuses the derived last-movement table for aging & avg days.
    - Set fast=False to also compute turnover & avg days (heavier).
    - Cached for 5 minutes to improve performance.
    """
    
    company = company or frappe.defaults.get_user_default("Company")
    wh_scope = _inv_warehouse_scope(company, warehouse)
    
    # Generate cache key (includes user so profile scope is not shared)
    cache_key = _inv_cache_key("inventory_snapshot", company, warehouse)
    
    # Check cache
    cached = frappe.cache().get(cache_key)
    if cached:
        try:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
        except Exception:
            pass

    # Common WHERE fragments / params
    bin_where = ["w.company = %s"]
    bin_params = [company]
    wh_sql, wh_params = warehouse_sql(wh_scope, field="b.warehouse")
    if wh_sql:
        # warehouse_sql returns " AND field = %s " — strip leading AND for join into AND-list
        bin_where.append(wh_sql.replace(" AND ", "", 1).strip())
        bin_params.extend(wh_params)
    bin_where_sql = " AND ".join(bin_where)

    # Warehouses in company (used by SLE restriction via Bin)
    # Current value (snapshot) from Bin
    total_value_sql = f"""
        SELECT COALESCE(SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)), 0) AS total_value
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE {bin_where_sql}
    """

    # Aging breakdown - OPTIMIZED: Compute in one query instead of nested subqueries
    sle_wh_sql, sle_wh_params = warehouse_sql(wh_scope, field="s.warehouse")
    aging_sql = f"""
        SELECT
            CASE
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 0 AND 30   THEN '0-30 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 31 AND 60  THEN '31-60 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 61 AND 90  THEN '61-90 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 91 AND 180 THEN '91-180 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 181 AND 365 THEN '181-365 Days'
                ELSE 'Over 365 Days'
            END AS period,
            COALESCE(SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)), 0) AS value
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        LEFT JOIN (
            SELECT 
                s.item_code,
                s.warehouse,
                MAX(s.posting_date) AS last_movement
            FROM `tabStock Ledger Entry` s
            INNER JOIN `tabWarehouse` sw ON sw.name = s.warehouse
            WHERE sw.company = %s
            {sle_wh_sql}
            GROUP BY s.item_code, s.warehouse
        ) lm ON lm.item_code = b.item_code AND lm.warehouse = b.warehouse
        WHERE {bin_where_sql}
        GROUP BY period
    """
    aging_params = [company] + sle_wh_params + bin_params

    # Category split — use Item.category only if that custom column exists
    if frappe.db.has_column("Item", "category"):
        category_expr = "COALESCE(NULLIF(i.category, ''), i.item_group, 'Uncategorized')"
    else:
        category_expr = "COALESCE(i.item_group, 'Uncategorized')"

    category_sql = f"""
        SELECT
            {category_expr} AS category,
            COALESCE(SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)), 0) AS value
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        INNER JOIN `tabItem` i ON i.name = b.item_code
        WHERE {bin_where_sql}
        GROUP BY category
    """

    total_value = frappe.db.sql(total_value_sql, bin_params, as_dict=True)[0].total_value or 0
    aging_rows  = frappe.db.sql(aging_sql, aging_params, as_dict=True)
    category_rows = frappe.db.sql(category_sql, bin_params, as_dict=True)

    # Percentages
    total_aging = sum(float(r.value or 0) for r in aging_rows) or 0.0
    aging_with_pct = [
        {"period": r.period,
         "value": float(r.value or 0),
         "percentage": round((float(r.value or 0) / total_aging * 100.0), 1) if total_aging > 0 else 0.0}
        for r in aging_rows
    ]

    total_cat = sum(float(r.value or 0) for r in category_rows) or 0.0
    category_with_pct = [
        {"category": r.category,
         "value": float(r.value or 0),
         "percentage": round((float(r.value or 0) / total_cat * 100.0), 1) if total_cat > 0 else 0.0}
        for r in category_rows
    ]

    result = {
        "totalInventoryValue": float(total_value),
        "inventoryTurnoverRatio": 0.0,
        "averageDaysInInventory": 0,
        "agingBreakdown": aging_with_pct,
        "inventoryByCategory": category_with_pct,
    }

    # Always calculate turnover ratio and average days
    # Formula: Inventory Turnover Ratio = Cost of Goods Sold (COGS) / Average Inventory
    # Average Inventory = (Opening Inventory + Closing Inventory) / 2
    # COGS = Total value of stock sold/issued in last 12 months (outgoing stock movements)
    
    # Calculate COGS: Sum of stock value differences for outgoing stock (actual_qty < 0)
    # This represents the cost of inventory that was sold/consumed
    cogs_sql = f"""
        SELECT 
            COALESCE(SUM(CASE WHEN s.actual_qty < 0 THEN ABS(s.stock_value_difference) ELSE 0 END), 0) AS cogs_12m,
            COALESCE(SUM(s.stock_value_difference), 0) AS net_change_12m
        FROM `tabStock Ledger Entry` s
        INNER JOIN `tabWarehouse` w ON w.name = s.warehouse
        WHERE w.company = %s
          AND s.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
          {sle_wh_sql}
    """
    cogs_params = [company] + sle_wh_params
    cogs_row = frappe.db.sql(cogs_sql, cogs_params, as_dict=True)[0]
    cogs_12m = float(cogs_row.cogs_12m or 0)
    net_change_12m = float(cogs_row.net_change_12m or 0)
    
    # Calculate opening inventory: Current value minus net change in last 12 months
    opening_value = max(float(total_value) - net_change_12m, 0.0)
    
    # Calculate average inventory: (Opening + Closing) / 2
    avg_inventory = (opening_value + float(total_value)) / 2.0
    
    # Calculate turnover ratio: COGS / Average Inventory
    # If avg_inventory is 0 or very small, ratio will be 0 or undefined
    if avg_inventory > 0.01:  # Avoid division by very small numbers
        result["inventoryTurnoverRatio"] = round(cogs_12m / avg_inventory, 2)
    else:
        result["inventoryTurnoverRatio"] = 0.0

    sle2_wh_sql, sle2_wh_params = warehouse_sql(wh_scope, field="sle.warehouse")
    avg_days_query = f"""
        SELECT 
            COALESCE(AVG(DATEDIFF(CURDATE(), latest.last_movement)), 0) as avg_days
        FROM (
            SELECT 
                sle.item_code, 
                sle.warehouse, 
                MAX(sle.posting_date) as last_movement
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabWarehouse` w ON w.name = sle.warehouse
            WHERE w.company = %s
              {sle2_wh_sql}
              AND sle.posting_date IS NOT NULL
            GROUP BY sle.item_code, sle.warehouse
        ) latest
        WHERE latest.last_movement IS NOT NULL
    """
    avg_days_params = [company] + sle2_wh_params
    avg_days_result = frappe.db.sql(avg_days_query, avg_days_params, as_dict=True)
    if avg_days_result and len(avg_days_result) > 0:
        result["averageDaysInInventory"] = int(avg_days_result[0].avg_days or 0)

    # Cache result for 5 minutes (300 seconds)
    try:
        frappe.cache().setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass
    
    return result

@frappe.whitelist()
def get_inventory_performance(company=None, warehouse=None, limit=10):
    """
    Get inventory performance data with movement analysis
    Cached for 5 minutes to improve performance.
    """
    import json
    
    company = company or frappe.defaults.get_user_default("Company")
    limit = int(limit) or 10
    wh_scope = _inv_warehouse_scope(company, warehouse)
    
    # Check cache
    cache_key = _inv_cache_key("inventory_perf", company, warehouse, limit)
    cached = frappe.cache().get(cache_key)
    if cached:
        try:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
        except Exception:
            pass

    # Build warehouse filter with proper parameterization
    warehouse_filter, warehouse_params = warehouse_sql(wh_scope, field="sle.warehouse")

    # Fast Moving Items (top items by quantity issued in last 30 days)
    fast_moving_query = f"""
        SELECT
            sle.item_code,
            i.item_name,
            ABS(SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END)) as quantity,
            ABS(SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.stock_value_difference) ELSE 0 END)) as value
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabItem` i ON i.name = sle.item_code
        WHERE sle.company = %s
        {warehouse_filter}
        AND sle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY sle.item_code, i.item_name
        ORDER BY quantity DESC
        LIMIT %s
    """

    # Slow Moving Items (low movement in last 90 days) - optimized with date filter
    slow_moving_query = f"""
        SELECT
            sle.item_code,
            i.item_name,
            ABS(SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END)) as quantity,
            ABS(SUM(CASE WHEN sle.actual_qty > 0 THEN sle.stock_value_difference ELSE 0 END)) as value,
            MAX(DATEDIFF(CURDATE(), sle.posting_date)) as days_since_last_movement
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabItem` i ON i.name = sle.item_code
        WHERE sle.company = %s
        {warehouse_filter}
        AND sle.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
        GROUP BY sle.item_code, i.item_name
        HAVING quantity > 0 AND days_since_last_movement > 60
        ORDER BY days_since_last_movement DESC, quantity ASC
        LIMIT %s
    """

    # Note: Reorder and Overstock alerts removed as reorder_level is not in Bin table
    # These features would require custom fields or Item Warehouse child table
    
    params = [company]
    fast_moving = frappe.db.sql(fast_moving_query, params + warehouse_params + [limit], as_dict=True)
    slow_moving = frappe.db.sql(slow_moving_query, params + warehouse_params + [limit], as_dict=True)
    reorder_alerts = []  # Not available in current schema
    overstock_alerts = []  # Not available in current schema

    return {
        "fastMovingItems": [
            {
                "itemCode": row.item_code,
                "itemName": row.item_name,
                "quantity": float(row.quantity) if row.quantity else 0.0,
                "value": float(row.value) if row.value else 0.0
            }
            for row in fast_moving
        ],
        "slowMovingItems": [
            {
                "itemCode": row.item_code,
                "itemName": row.item_name,
                "quantity": float(row.quantity) if row.quantity else 0.0,
                "value": float(row.value) if row.value else 0.0,
                "daysSinceLastMovement": int(row.days_since_last_movement) if row.days_since_last_movement else 0
            }
            for row in slow_moving
        ],
        "reorderAlerts": [
            {
                "itemCode": row.item_code,
                "itemName": row.item_name,
                "currentStock": float(row.current_stock) if row.current_stock else 0.0,
                "reorderLevel": float(row.reorder_level) if row.reorder_level else 0.0,
                "shortage": float(row.shortage) if row.shortage else 0.0
            }
            for row in reorder_alerts
        ],
        "overstockAlerts": [
            {
                "itemCode": row.item_code,
                "itemName": row.item_name,
                "currentStock": float(row.current_stock) if row.current_stock else 0.0,
                "maxStockLevel": float(row.max_stock_level) if row.max_stock_level else 0.0,
                "excess": float(row.excess) if row.excess else 0.0
            }
            for row in overstock_alerts
        ]
    }
    
    # Cache result
    try:
        frappe.cache().setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass
    
    return result

@frappe.whitelist()
def get_inventory_trends(company=None, warehouse=None, months=6):
    """
    Get inventory trend data
    Cached for 5 minutes to improve performance.
    """
    import json
    
    company = company or frappe.defaults.get_user_default("Company")
    months = int(months) or 6
    wh_scope = _inv_warehouse_scope(company, warehouse)
    
    # Check cache
    cache_key = _inv_cache_key("inventory_trends", company, warehouse, months)
    cached = frappe.cache().get(cache_key)
    if cached:
        try:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
        except Exception:
            pass

    # Build warehouse filter with proper parameterization
    warehouse_filter, warehouse_params = warehouse_sql(wh_scope, field="sle.warehouse")

    # Movement In vs Out
    movement_query = f"""
        SELECT
            DATE_FORMAT(sle.posting_date, '%%b') as month,
            SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) as in_quantity,
            SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) as out_quantity,
            SUM(CASE WHEN sle.actual_qty > 0 THEN sle.stock_value_difference ELSE 0 END) as in_value,
            SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.stock_value_difference) ELSE 0 END) as out_value
        FROM `tabStock Ledger Entry` sle
        WHERE sle.company = %s
        {warehouse_filter}
        AND sle.posting_date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
        GROUP BY YEAR(sle.posting_date), MONTH(sle.posting_date)
        ORDER BY YEAR(sle.posting_date), MONTH(sle.posting_date)
    """

    # Inventory Value Trend - FIXED: Removed expensive subquery, simplified to use monthly totals
    value_trend_query = f"""
        SELECT
            DATE_FORMAT(sle.posting_date, '%%b') as month,
            SUM(ABS(sle.stock_value_difference)) as value
        FROM `tabStock Ledger Entry` sle
        WHERE sle.company = %s
        {warehouse_filter}
        AND sle.posting_date >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
        GROUP BY YEAR(sle.posting_date), MONTH(sle.posting_date)
        ORDER BY YEAR(sle.posting_date), MONTH(sle.posting_date)
    """

    # Stock by Warehouse - FIXED: Use current Bin data instead of expensive latest SLE query
    bin_warehouse_filter, bin_warehouse_params = warehouse_sql(wh_scope, field="b.warehouse")
    
    warehouse_query = f"""
        SELECT
            b.warehouse,
            SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) as value
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE w.company = %s
        {bin_warehouse_filter}
        GROUP BY b.warehouse
        ORDER BY value DESC
    """

    params = [company]
    movement_data = frappe.db.sql(movement_query, params + warehouse_params + [months], as_dict=True)
    value_trend_data = frappe.db.sql(value_trend_query, params + warehouse_params + [months], as_dict=True)
    warehouse_data = frappe.db.sql(warehouse_query, params + bin_warehouse_params, as_dict=True)

    # Calculate percentages for warehouses
    total_warehouse_value = sum(row.value for row in warehouse_data)
    warehouse_with_pct = []
    for row in warehouse_data:
        percentage = (row.value / total_warehouse_value * 100) if total_warehouse_value > 0 else 0
        warehouse_with_pct.append({
            "warehouse": row.warehouse,
            "value": float(row.value) if row.value else 0.0,
            "percentage": round(percentage, 1)
        })

    return {
        "movementInOut": [
            {
                "month": row.month,
                "inQuantity": float(row.in_quantity) if row.in_quantity else 0.0,
                "outQuantity": float(row.out_quantity) if row.out_quantity else 0.0,
                "inValue": float(row.in_value) if row.in_value else 0.0,
                "outValue": float(row.out_value) if row.out_value else 0.0
            }
            for row in movement_data
        ],
        "inventoryValueTrend": [
            {
                "month": row.month,
                "value": float(row.value) if row.value else 0.0
            }
            for row in value_trend_data
        ],
        "stockByWarehouse": warehouse_with_pct,
        "agingTrend": []  # Can be implemented similarly to other trending queries
    }
    
    # Cache result
    try:
        frappe.cache().setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass
    
    return result

@frappe.whitelist()
def get_non_moving_items(company=None, warehouse=None, agingBucket=None, limit=20):
    """
    Get non-moving inventory items with aging breakdown
    Cached for 5 minutes to improve performance.
    """
    import json
    
    company = company or frappe.defaults.get_user_default("Company")
    limit = int(limit) or 20
    wh_scope = _inv_warehouse_scope(company, warehouse)
    
    # Check cache
    cache_key = _inv_cache_key("inventory_non_moving", company, warehouse, limit)
    cached = frappe.cache().get(cache_key)
    if cached:
        try:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
        except Exception:
            pass

    # Build warehouse filter with proper parameterization
    warehouse_filter, warehouse_params = warehouse_sql(wh_scope, field="b.warehouse")

    # Non-moving items - FIXED: Use Bin with last movement from Bin instead of expensive SLE latest query
    non_moving_query = f"""
        SELECT
            b.item_code,
            i.item_name,
            b.warehouse,
            b.actual_qty as quantity,
            (b.actual_qty * COALESCE(b.valuation_rate, 0)) as value,
            MAX(DATEDIFF(CURDATE(), sle.posting_date)) as days_since_last_movement,
            MAX(sle.posting_date) as last_movement_date
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        LEFT JOIN `tabItem` i ON i.name = b.item_code
        LEFT JOIN `tabStock Ledger Entry` sle ON sle.item_code = b.item_code AND sle.warehouse = b.warehouse
        WHERE w.company = %s
        {warehouse_filter}
        AND b.actual_qty > 0
        GROUP BY b.item_code, i.item_name, b.warehouse, b.actual_qty, b.valuation_rate
        HAVING days_since_last_movement > 30
        ORDER BY days_since_last_movement DESC
        LIMIT %s
    """

    # Aging Summary by Bucket - FIXED: Use current Bin + limited SLE for aging calculation
    bin_warehouse_filter, bin_warehouse_params = warehouse_sql(wh_scope, field="b.warehouse")
    
    aging_summary_query = f"""
        SELECT
            CASE
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 0 AND 30 THEN '0-30 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 31 AND 60 THEN '31-60 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 61 AND 90 THEN '61-90 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 91 AND 180 THEN '91-180 Days'
                WHEN DATEDIFF(CURDATE(), COALESCE(lm.last_movement, CURDATE())) BETWEEN 181 AND 365 THEN '181-365 Days'
                ELSE 'Over 365 Days'
            END as bucket,
            COUNT(DISTINCT b.item_code) as item_count,
            SUM(b.actual_qty * COALESCE(b.valuation_rate, 0)) as total_value
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        LEFT JOIN (
            SELECT item_code, warehouse, MAX(posting_date) as last_movement
            FROM `tabStock Ledger Entry`
            WHERE company = %s
            GROUP BY item_code, warehouse
        ) lm ON lm.item_code = b.item_code AND lm.warehouse = b.warehouse
        WHERE w.company = %s
        {bin_warehouse_filter}
        AND b.actual_qty > 0
        GROUP BY bucket
        ORDER BY
            CASE bucket
                WHEN '0-30 Days' THEN 1
                WHEN '31-60 Days' THEN 2
                WHEN '61-90 Days' THEN 3
                WHEN '91-180 Days' THEN 4
                WHEN '181-365 Days' THEN 5
                ELSE 6
            END
    """

    params = [company]
    non_moving = frappe.db.sql(non_moving_query, params + bin_warehouse_params + [limit], as_dict=True)
    aging_summary = frappe.db.sql(aging_summary_query, [company] + params + bin_warehouse_params, as_dict=True)

    return {
        "nonMovingItems": [
            {
                "itemCode": row.item_code,
                "itemName": row.item_name,
                "warehouse": row.warehouse,
                "quantity": float(row.quantity) if row.quantity else 0.0,
                "value": float(row.value) if row.value else 0.0,
                "daysSinceLastMovement": int(row.days_since_last_movement) if row.days_since_last_movement else 0,
                "lastMovementDate": str(row.last_movement_date) if row.last_movement_date else ""
            }
            for row in non_moving
        ],
        "agingSummary": [
            {
                "bucket": row.bucket,
                "itemCount": int(row.item_count) if row.item_count else 0,
                "totalValue": float(row.total_value) if row.total_value else 0.0
            }
            for row in aging_summary
        ]
    }
    
    # Cache result
    try:
        frappe.cache().setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass
    
    return result

@frappe.whitelist()
def get_inventory_risk(company=None, warehouse=None):
    """
    Get inventory risk data including non-moving items, aging summary, critical shortage, and overstock
    Returns: nonMovingItems, agingSummary, criticalShortage, overstock
    """
    import json
    
    company = company or frappe.defaults.get_user_default("Company")
    wh_scope = _inv_warehouse_scope(company, warehouse)
    
    # Check cache
    cache_key = _inv_cache_key("inventory_risk", company, warehouse)
    cached = frappe.cache().get(cache_key)
    if cached:
        try:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
        except Exception:
            pass
    
    # Build warehouse filter
    warehouse_filter, warehouse_params = warehouse_sql(wh_scope, field="b.warehouse")
    
    # Get current stock balances - using Bin table for accurate current stock
    # FIX: tabBin doesn't have company column, join with tabWarehouse
    current_stock_query = f"""
        SELECT 
            b.item_code,
            i.item_name,
            b.warehouse,
            b.actual_qty as qty,
            b.stock_value as stock_value,
            (SELECT MAX(posting_date) FROM `tabStock Ledger Entry` 
             WHERE item_code = b.item_code 
             AND warehouse = b.warehouse 
             AND company = %s) as last_movement_date
        FROM `tabBin` b
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        INNER JOIN `tabItem` i ON i.name = b.item_code
        WHERE w.company = %s
        {warehouse_filter}
        AND b.actual_qty > 0
    """
    
    stock_params = [company, company] + warehouse_params
    current_stock = frappe.db.sql(current_stock_query, stock_params, as_dict=True)
    
    # Non-Moving Items: No movement in last 30+ days but have stock
    non_moving_items = []
    aging_summary_dict = {}
    
    from datetime import date
    
    for stock in current_stock:
        if stock.last_movement_date:
            today = date.today()
            last_date = frappe.utils.getdate(stock.last_movement_date)
            days_since = (today - last_date).days
            
            # Add to non-moving if > 30 days
            if days_since > 30:
                non_moving_items.append({
                    "itemCode": stock.item_code,
                    "itemName": stock.item_name or stock.item_code,
                    "warehouse": stock.warehouse,
                    "quantity": float(stock.qty) if stock.qty else 0.0,
                    "value": float(stock.stock_value) if stock.stock_value else 0.0,
                    "daysSinceLastMovement": days_since,
                    "lastMovementDate": str(stock.last_movement_date) if stock.last_movement_date else ""
                })
            
            # Categorize by aging bucket for summary
            if days_since <= 30:
                bucket = "0-30 Days"
            elif days_since <= 60:
                bucket = "31-60 Days"
            elif days_since <= 90:
                bucket = "61-90 Days"
            elif days_since <= 180:
                bucket = "91-180 Days"
            elif days_since <= 365:
                bucket = "181-365 Days"
            else:
                bucket = "Over 365 Days"
            
            if bucket not in aging_summary_dict:
                aging_summary_dict[bucket] = {
                    "bucket": bucket,
                    "itemCount": 0,
                    "totalValue": 0.0
                }
            
            aging_summary_dict[bucket]["itemCount"] += 1
            aging_summary_dict[bucket]["totalValue"] += float(stock.stock_value) if stock.stock_value else 0.0
    
    # Sort non-moving by days descending
    non_moving_items = sorted(non_moving_items, key=lambda x: x["daysSinceLastMovement"], reverse=True)
    
    # Convert aging summary to list and sort
    aging_summary = list(aging_summary_dict.values())
    bucket_order = {
        "0-30 Days": 1,
        "31-60 Days": 2,
        "61-90 Days": 3,
        "91-180 Days": 4,
        "181-365 Days": 5,
        "Over 365 Days": 6
    }
    aging_summary = sorted(aging_summary, key=lambda x: bucket_order.get(x["bucket"], 99))
    
    # Critical Shortage: Items below safety stock
    # FIX: Join with Warehouse for company filter, only safety_stock available
    critical_shortage_query = f"""
        SELECT 
            i.name as item_code,
            i.item_name,
            i.safety_stock,
            COALESCE(SUM(b.actual_qty), 0) as current_stock
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON b.item_code = i.name
        LEFT JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE w.company = %s
            AND i.disabled = 0
            AND i.safety_stock > 0
            {warehouse_filter}
        GROUP BY i.name, i.item_name, i.safety_stock
        HAVING COALESCE(SUM(b.actual_qty), 0) < i.safety_stock
        ORDER BY (i.safety_stock - COALESCE(SUM(b.actual_qty), 0)) DESC
        LIMIT 20
    """
    
    critical_params = [company] + warehouse_params
    critical_shortage_raw = frappe.db.sql(critical_shortage_query, critical_params, as_dict=True)
    
    critical_shortage = [
        {
            "itemName": row.item_name or row.item_code,
            "itemCode": row.item_code,
            "currentStock": float(row.current_stock) if row.current_stock else 0.0,
            "safetyStock": float(row.safety_stock) if row.safety_stock else 0.0,
            "reorderLevel": 0.0  # Not available in schema
        }
        for row in critical_shortage_raw
    ]
    
    # Overstock: Not available - no max_stock_level in tabItem
    overstock = []
    
    result = {
        "nonMovingItems": non_moving_items[:20],  # Limit to top 20
        "agingSummary": aging_summary,
        "criticalShortage": critical_shortage,
        "overstock": overstock
    }
    
    # Cache result for 5 minutes
    try:
        frappe.cache().setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass
    
    return result


def _normalize_hierarchy_params(level, category, item_group, brand, item_code):
    """Map legacy mobile drill order (category→item_group→brand) to current API."""
    level = (level or "category").strip().lower()
    legacy = {"brand_rows_for_item_group": False, "item_group_rows_for_brand": False}

    # Legacy level 2: item_group under category → brands under category
    if level == "item_group" and category and not item_group and not brand:
        level = "brand"
        legacy["item_group_rows_for_brand"] = True

    # Legacy level 3: brand under item_group → item_group under brand
    elif level == "brand" and item_group and not category and not brand:
        brand = item_group
        item_group = None
        level = "item_group"
        legacy["brand_rows_for_item_group"] = True

    # Legacy level 4: mobile may send item_group instead of brand
    elif level == "item" and not brand and item_group:
        brand = item_group
        item_group = None
    elif level == "item" and brand and item_group and brand == item_group:
        # Duplicate breadcrumb from legacy alias (AVERY BERKEL > AVERY BERKEL)
        item_group = None

    return level, category, item_group, brand, item_code, legacy


def _apply_hierarchy_display_aliases(level, rows, legacy=None):
    """Duplicate labels under field names the mobile app reads at each drill level."""
    legacy = legacy or {}
    for row in rows:
        if level == "category":
            label = row.get("category") or "Uncategorized"
            row.setdefault("name", label)
            row.setdefault("item_group", label)
        elif level == "brand":
            label = row.get("brand") or "Unknown Brand"
            row.setdefault("name", label)
            # Legacy mobile level 2 requests item_group but receives brand rows.
            if legacy.get("item_group_rows_for_brand") or not row.get("item_group"):
                row["item_group"] = label
        elif level == "item_group":
            label = row.get("item_group") or "Unknown Item Group"
            row.setdefault("name", label)
            row.setdefault("item_type_name", label)
            parent_brand = row.get("brand")
            if legacy.get("brand_rows_for_item_group"):
                # Legacy mobile level 3 requests brand but receives item_group rows.
                row["parent_brand"] = parent_brand
                row["brand"] = label
        elif level == "item":
            label = row.get("item_name") or row.get("item_code") or "Unknown Item"
            row.setdefault("name", label)
            row.setdefault("value", row.get("total_value"))
            row.setdefault("quantity", row.get("total_quantity"))
        elif level in ("warehouse", "territory"):
            label = row.get(level) or row.get("warehouse") or "Unknown"
            row.setdefault("name", label)
    return rows


@frappe.whitelist()
def get_inventory_hierarchy(
    company=None,
    warehouse=None,
    level="category",
    category=None,      # parent Item Group node for level>=2
    item_group=None,    # child Item Group node for level>=3
    brand=None,
    item_code=None,
    territory=None,
    territories=None,
    limit=100,
):
    """
    Inventory hierarchy — two independent cards:

    A) Territory path (NEW, Bin valuation = snapshot):
       level: territory → warehouse → brand → item_group → item
       Parents: territory (+ warehouse / brand / item_group as you drill)
       Response: { level, rows, meta }
       WH→territory: warehouse name/parent contains territory name; unmapped omitted.

    B) Category path (existing, ViewItemCurrentStock — unchanged shapes):
       level: category → brand → item_group → item → warehouse|territory (leaf under item)
       Response: bare array of rows

    Shared level names are disambiguated by parents:
      - Territory path if `territory` is set (and no `category`), or level=territory without item_code
      - Category leaf warehouse/territory if `item_code` is set
      - Category path if `category` is set / default level=category
    """

    level, category, item_group, brand, item_code, legacy = _normalize_hierarchy_params(
        level, category, item_group, brand, item_code
    )

    try:
        valid_levels = ["category", "item_group", "brand", "item", "warehouse", "territory"]
        
        if level not in valid_levels:
            frappe.throw(f"Invalid level. Must be one of: {valid_levels}")
        
        company = company or frappe.defaults.get_user_default("Company")
        
        if not company:
            frappe.throw("Company not found")

        # --- Territory card (new) ---
        if is_territory_path(
            level, territory=territory, category=category, item_code=item_code
        ):
            return get_territory_hierarchy(
                company=company,
                level=level,
                territory=territory,
                territories=territories,
                warehouse=warehouse,
                brand=brand,
                item_group=item_group,
                limit=limit,
            )

        # --- Category card (existing) + Access Profile warehouse scope ---
        # Base WHERE clause conditions
        base_conditions = ["actual_qty > 0"]
        params = []

        # Optional exact warehouse filter (Category path)
        wh_scope = _inv_warehouse_scope(company, warehouse)
        wh_sql, wh_params = warehouse_sql(wh_scope, field="warehouse")
        if wh_sql:
            base_conditions.append(wh_sql.replace(" AND ", "", 1).strip())
            params.extend(wh_params)
        elif warehouse:
            base_conditions.append("warehouse = %s")
            params.append(warehouse)
        
        # Combine base conditions
        where_clause = " AND ".join(base_conditions)
        
        # -------------------
        # Level 1: Categories - Industrial. Retail, Software.
        # -------------------
        if level == "category":
            query = f"""
                SELECT
                    Category AS category,
                    SUM(stock_value) AS value,
                    SUM(actual_qty) AS quantity
                FROM `ViewItemCurrentStock`
                WHERE {where_clause}
                GROUP BY Category
                ORDER BY value DESC
            """
            
            result = frappe.db.sql(query, params, as_dict=True)
            
            total_value = sum(float(r.value or 0) for r in result) if result else 0
            
            for r in result:
                v = float(r.value or 0)
                q = float(r.quantity or 0)
                r.percentage = round((v / total_value * 100) if total_value > 0 else 0, 1)
                r.value = v
                r.quantity = q
            
            return _apply_hierarchy_display_aliases("category", result, legacy)
        
        # -------------------------
        # Level 2: Brands under a Category - Hitachi, Datalogic, etc.
        # -------------------------
        elif level == "brand":
            if not category:
                frappe.throw("Category parameter is required for brand level")
            
            where_clause += " AND Category COLLATE utf8mb4_unicode_ci = %s"
            params.append(category)
            
            query = f"""
                SELECT
                    Brand AS brand,
                    Category,
                    SUM(stock_value) AS value,
                    SUM(actual_qty) AS quantity
                FROM `ViewItemCurrentStock`
                WHERE {where_clause}
                GROUP BY Brand, Category
                ORDER BY value DESC
            """
            
            result = frappe.db.sql(query, params, as_dict=True)
            
            total_value = sum(float(r.value or 0) for r in result) if result else 0
            
            for r in result:
                v = float(r.value or 0)
                q = float(r.quantity or 0)
                r.percentage = round((v / total_value * 100) if total_value > 0 else 0, 1)
                r.value = v
                r.quantity = q
            
            return _apply_hierarchy_display_aliases("brand", result, legacy)
        
        # -------------------
        # Level 3: Item Groups under a Brand - Systems, Consumable, etc.
        # -------------------
        elif level == "item_group":
            if not brand:
                frappe.throw("Brand parameter is required for item_group level")
            
            where_clause += " AND Brand COLLATE utf8mb4_unicode_ci = %s"
            params.append(brand)
            
            query = f"""
                SELECT
                    Brand AS brand,
                    Item_type_name AS item_group,
                    SUM(stock_value) AS value,
                    SUM(actual_qty) AS quantity
                FROM `ViewItemCurrentStock`
                WHERE {where_clause}
                GROUP BY Brand, Item_type_name
                ORDER BY value DESC
            """
            
            result = frappe.db.sql(query, params, as_dict=True)
            
            total_value = sum(float(r.value or 0) for r in result) if result else 0
            
            for r in result:
                v = float(r.value or 0)
                q = float(r.quantity or 0)
                r.percentage = round((v / total_value * 100) if total_value > 0 else 0, 1)
                r.value = v
                r.quantity = q
            
            return _apply_hierarchy_display_aliases("item_group", result, legacy)
        
        # -------------------
        # Level 4: Items for a Brand
        # -------------------
        elif level == "item":
            if not brand:
                frappe.throw("Brand parameter is required for item level")

            where_clause += " AND Brand COLLATE utf8mb4_unicode_ci = %s"
            params.append(brand)
            if item_group:
                where_clause += " AND Item_type_name COLLATE utf8mb4_unicode_ci = %s"
                params.append(item_group)
            
            query = f"""
                SELECT
                    item_code,
                    item_name AS item_name,
                    SUM(stock_value) AS total_value,
                    SUM(actual_qty) AS total_quantity
                FROM `ViewItemCurrentStock`
                WHERE {where_clause}
                GROUP BY item_code, item_name
                ORDER BY total_value DESC
                LIMIT 100
            """
            
            result = frappe.db.sql(query, params, as_dict=True)
            
            for r in result:
                r.total_value = float(r.total_value or 0)
                r.total_quantity = float(r.total_quantity or 0)
            
            return _apply_hierarchy_display_aliases("item", result, legacy)
        
        # -------------------
        # Level 5A: Warehouse split for an Item
        # -------------------
        elif level == "warehouse":
            if not item_code:
                frappe.throw("Item Code parameter is required for warehouse level")
            
            where_clause += " AND item_code COLLATE utf8mb4_unicode_ci = %s"
            params.append(item_code)
            
            query = f"""
                SELECT
                    warehouse,
                    actual_qty AS quantity,
                    stock_value AS value
                FROM `ViewItemCurrentStock`
                WHERE {where_clause}
                ORDER BY stock_value DESC
            """
            
            result = frappe.db.sql(query, params, as_dict=True)
            
            for r in result:
                r.quantity = float(r.quantity or 0)
                r.value = float(r.value or 0)
            
            return _apply_hierarchy_display_aliases("warehouse", result, legacy)
        
        # -------------------
        # Level 5B: Territory split for an Item (via Warehouse)
        # -------------------
        elif level == "territory":
            if not item_code:
                frappe.throw("Item Code parameter is required for territory level")
            
            territory_field = _get_warehouse_territory_field()
            if not territory_field:
                frappe.throw(
                    "Warehouse doctype is missing a Territory field. "
                    "Please add a Link field to Territory or update the configuration."
                )
            
            where_clause += " AND item_code COLLATE utf8mb4_unicode_ci = %s"
            params.append(item_code)
            
            territory_column = f"`w`.`{territory_field}`"
            query = f"""
                SELECT
                    COALESCE({territory_column}, 'Unassigned') AS territory,
                    SUM(actual_qty) AS quantity,
                    SUM(stock_value) AS value
                FROM `ViewItemCurrentStock`
                LEFT JOIN `tabWarehouse` w ON w.name = `ViewItemCurrentStock`.`warehouse`
                WHERE {where_clause}
                GROUP BY COALESCE({territory_column}, 'Unassigned')
                ORDER BY value DESC
            """
            
            result = frappe.db.sql(query, params, as_dict=True)
            
            for r in result:
                r.quantity = float(r.quantity or 0)
                r.value = float(r.value or 0)
            
            return _apply_hierarchy_display_aliases("territory", result, legacy)
        
        else:
            frappe.throw(f"Invalid level parameter: {level}")
            
    except (frappe.ValidationError, frappe.PermissionError):
        raise
    except Exception as e:
        frappe.log_error(
            message=f"Inventory Hierarchy Error: {str(e)}\nTraceback:\n{frappe.get_traceback()}",
            title="Inventory Hierarchy API Error"
        )
        frappe.throw(f"Error fetching inventory hierarchy: {str(e)}")


@frappe.whitelist()
def get_inventory_items(
    company=None,
    warehouse=None,
    category=None,
    item_group=None,
    brand=None,
    **kwargs,
):
    """Mobile Items screen — alias for hierarchy level=item."""
    return get_inventory_hierarchy(
        company=company,
        warehouse=warehouse,
        level="item",
        category=category,
        item_group=item_group,
        brand=brand,
    )


@lru_cache(maxsize=1)
def _get_warehouse_territory_field() -> str | None:
    """Return the Warehouse column that stores territory, if any."""
    try:
        columns = frappe.db.sql("SHOW COLUMNS FROM `tabWarehouse`", as_dict=True)
    except Exception:
        return None
    
    candidates = ("territory", "territory_name", "territory_code")
    for candidate in candidates:
        for col in columns:
            if col.get("Field", "").lower() == candidate:
                return col["Field"]
    return None


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_stock_cover(
    company=None,
    warehouse=None,
    lookback_days=None,
    low_cover_threshold=None,
    limit=None,
):
    """Stock cover — days of supply from recent sales velocity."""
    from erp_analysis.services.stock_cover import get_stock_cover_payload
    from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int

    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    warehouse = _get_arg("warehouse", warehouse)
    lookback_days = _to_int(_get_arg("lookback_days", lookback_days), 90)
    low_cover_threshold = float(_get_arg("low_cover_threshold", low_cover_threshold) or 7)
    limit = _to_int(_get_arg("limit", limit), 20)

    try:
        return get_stock_cover_payload(
            company=company,
            warehouse=warehouse,
            lookback_days=lookback_days,
            low_cover_threshold=low_cover_threshold,
            limit=limit,
        )
    except Exception:
        frappe.log_error(title="inventory.get_stock_cover", message=frappe.get_traceback())
        return {
            "lookback_days": lookback_days,
            "low_cover_threshold": low_cover_threshold,
            "kpis": {"avg_cover_days": 0, "low_cover_count": 0, "excess_cover_count": 0},
            "low_cover_items": [],
        }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_inventory_health(company=None, warehouse=None):
    """Inventory health summary — mobile alias combining snapshot KPIs and risk counts."""
    company = company or frappe.defaults.get_user_default("Company")
    try:
        snapshot = get_inventory_snapshot(company=company, warehouse=warehouse)
        risk = get_inventory_risk(company=company, warehouse=warehouse)
    except Exception:
        frappe.log_error(title="inventory.get_inventory_health", message=frappe.get_traceback())
        snapshot, risk = {}, {}

    kpis = snapshot.get("kpis") or snapshot.get("KPIs") or {}
    non_moving = risk.get("nonMovingItems") or []
    critical = risk.get("criticalShortage") or []
    aging = risk.get("agingSummary") or []

    return {
        "company": company,
        "warehouse": warehouse,
        "kpis": {
            "total_value": float(kpis.get("totalValue") or kpis.get("total_value") or 0),
            "total_items": int(kpis.get("totalItems") or kpis.get("total_items") or 0),
            "non_moving_count": len(non_moving),
            "non_moving_value": sum(float(i.get("value") or 0) for i in non_moving),
            "critical_shortage_count": len(critical),
            "overstock_count": len(risk.get("overstock") or []),
        },
        "aging_summary": aging,
        "critical_shortage": critical[:20],
        "non_moving_items": non_moving[:20],
    }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_dead_stock(company=None, warehouse=None, min_days=None, limit=None):
    """Dead / non-moving stock list for mobile inventory health screen."""
    from erp_analysis.utils.rpc import get_arg as _get_arg, to_int as _to_int

    company = _get_arg("company", company) or frappe.defaults.get_user_default("Company")
    warehouse = _get_arg("warehouse", warehouse)
    min_days = _to_int(_get_arg("min_days", min_days), 90)
    limit = _to_int(_get_arg("limit", limit), 50)

    try:
        risk = get_inventory_risk(company=company, warehouse=warehouse)
        items = [
            row
            for row in (risk.get("nonMovingItems") or [])
            if int(row.get("daysSinceLastMovement") or 0) >= min_days
        ]
    except Exception:
        frappe.log_error(title="inventory.get_dead_stock", message=frappe.get_traceback())
        items = []

    items = sorted(items, key=lambda r: int(r.get("daysSinceLastMovement") or 0), reverse=True)[:limit]
    total_value = sum(float(i.get("value") or 0) for i in items)

    return {
        "company": company,
        "warehouse": warehouse,
        "min_days": min_days,
        "summary": {"count": len(items), "total_value": total_value},
        "items": items,
    }
