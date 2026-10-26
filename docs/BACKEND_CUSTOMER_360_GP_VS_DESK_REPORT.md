# Customer 360 GP vs desk Printechs Gross Profit

## Expected alignment

| Customer 360 | Desk report |
|--------------|-------------|
| `sales.ytd`, `sales.mtd`, `sales.today` | Sum of **Net Amount** for the customer (same company + dates) |
| `sales.gp`, `sales.gp_pct` | YTD **Net − Cost** and **GP %** from the same grain as **Printechs Gross Profit** |
| Source | **`tabSalesDashBoard`** (materialized from `ViewSalesGrossProfit`) when rows exist |

Mobile should treat **`message.sales`** as authoritative when `ytd`, `mtd`, and `gp_pct` are present.

## Customer filter (link vs label)

- **Sales Invoice** and mobile Customer 360 use the Customer **link** (`Customer.name`), e.g. `USG Middle East Ltd.`
- **`ViewSalesGrossProfit.customer`** and **`tabSalesDashBoard.Customer`** store **`customer_name`** (label), e.g. `Factory of USG Middle East LTD. CO`

Filtering SDB with `Customer = <link>` returns **no rows** → API fell back to SI net + Stock Ledger COGS → **GP % could show 100%** while the desk report (after invoice subquery fix) shows ~57%.

**Fix (erp_analysis):** scope SDB by  
`Invoice_No IN (SELECT name FROM tabSales Invoice WHERE customer = %s AND docstatus = 1)`  
(same idea as **Printechs Gross Profit** header customer filter in erpnext).

## Verify on site

```python
# Desk total (Invoice Item, customer filter)
from erpnext.accounts.report.printechs_gross_profit.printechs_gross_profit import get_item_data, get_item_columns
filters = {"company": "...", "from_date": "2026-01-01", "to_date": "...", "_customer": "USG Middle East Ltd."}
total = get_item_data(filters, get_item_columns())[-1]  # net, cost, gp%

# Mobile API
from erp_analysis.services.customer_360 import get_customer_sales_block
get_customer_sales_block(company="...", customer="USG Middle East Ltd.", as_of="...")
```

` sales.ytd` should match desk total **Net Amount**; `sales.gp_pct` should match desk **Gross Profit %** (within rounding).

## Not used for `sales.*`

- `get_customer_statement` (open AR / period statement preview)
- `receivables.*` (outstanding balances)
