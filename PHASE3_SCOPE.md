# Phase 3 — Scope adjustments

**Decision date:** 2026-08-05

The following items from the Phase 3 Business Analytics instructions are **out of scope for now**. Do not design, implement, or require backend APIs for them until explicitly reopened.

## Deferred (ignore for now)

| Area | Original phases | Notes |
| ---- | --------------- | ----- |
| **Sales Targets & Achievement** | 3B (targets KPIs, remaining target, daily run rate) | No target DocType / APIs yet |
| **Salesperson Target ranking** (target columns) | Part of 3B | Salesperson **performance without targets** may still be considered later under sales/collection |
| **Collection Target / Achievement %** | Part of 3D | Collection **actuals** (today/MTD/YTD, by territory/customer) remain in scope |
| **Cash Position & Management Cash Flow** | 3L | Bank / cash balances and net position forecasts |
| **Daily Brief cash/bank lines** | Part of later brief | Omit bank/cash until 3L is reopened |

## Still in scope (revised Phase 3)

Keep building in order (adjust labels as needed):

| Order | Module | Notes |
| ----- | ------ | ----- |
| 3A | Executive Dashboard 2.0 | **Omit** target-based KPIs and bank/cash. Open SO/PO/payables sections optional/null until those APIs exist |
| 3B′ | Salesperson & Product performance | **Without** target/achievement fields |
| 3C | Customer 360 | Unchanged |
| 3D | Collection Performance + Attention | Actuals only; **no** collection target % |
| 3E | Sales Order / Order Book | Unchanged |
| 3F | Payables Dashboard + Payment Planning | Unchanged |
| 3G | Purchase Performance | Unchanged |
| 3H | Inventory Health / Stock Cover / Dead Stock | Unchanged |
| 3I | Profitability (Gross Profit) | Unchanged |
| 3J | Management Exceptions | Unchanged (no target-miss exceptions until targets return) |
| 3K | Approval Analytics | Unchanged |
| — | Cash Flow (3L) | **Deferred** |
| — | Sales Targets (original 3B) | **Deferred** |

## Config / permissions

Do **not** add these `get_mobile_config` module flags yet:

- `sales_target`
- `cash_flow`

Do **not** add menu permission keys for Targets or Cash Flow until those modules are scheduled.

## Backend APIs — do not create yet

- `get_sales_target_dashboard`
- Target fields on salesperson/collection payloads
- `get_cash_flow_dashboard`
- Bank balance / cash balance aggregations

## Executive Dashboard 3A — KPI set (revised)

Include when data exists:

- Sales (Today / MTD / YTD + LY compare)
- Gross Profit (MTD / YTD / GP %)
- Collection (Today / MTD / YTD) — actuals only
- Receivables (Total / Overdue / Overdue %)
- Inventory (Value / Low stock / Non-moving if available)
- Orders (Open SO / Pending delivery) — when SO API ready
- Purchasing (Open PO / Pending receipt) — when PO API ready
- Payables (Total / Overdue) — when payables API ready
- Approvals (Pending count)

**Exclude for now:**

- Sales / collection target & achievement
- Bank balance, cash balance, expected net cash position
