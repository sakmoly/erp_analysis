# Collection payment entries (mobile drill)

## Method

`erp_analysis.collection.get_collection_payments`  
Whitelisted · GET/POST · requires Access Profile `can_view` on this object.

## Params

| Param | Required | Example | Notes |
|--------|----------|---------|--------|
| `company` | Yes | Printechs Advanced Printing Trading Co. | From Access Profile |
| `from_date` | No* | `2026-01-01` | With `to_date` or use `period` |
| `to_date` | No* | `2026-10-26` | |
| `period` | No | `ytd`, `mtd`, `qtd`, `today` | Default `ytd` when dates omitted |
| `breakdown_type` | Yes** | `territory`, `salesperson`, `customer` | Drill dimension |
| `breakdown_id` | Yes** | `Jeddah`, customer id, sales person name | Slice key |
| `payment_entry` | No | `ACC-PAY-2026-00421` | Detail: single PE (+ allocations) |
| `limit` | No | `500` | Max 2000 |

\* Provide both dates or `period`.  
\** Not required when `payment_entry` is set (detail view).

## Data source

- `tabPayment Entry`, `payment_type = Receive`, `docstatus = 1`
- Scoped by company, posting date range, user territory view scope
- Breakdown filters:
  - **territory** — customer territory **or** mode-of-payment branch suffix (e.g. `Cash Collection - Jeddah`); rows whose MoP suffix is another branch (e.g. `- Dammam`) are **excluded** even if the customer is in the drill territory. Response `meta.territory_drill_filter.payments_hidden_other_branch` counts excluded rows.
  - **customer** — `pe.party`
  - **salesperson** — PE has allocation to Sales Invoice with matching `Sales Team.sales_person`

## Response (Frappe `message`)

See sample in mobile spec: `meta`, `summary`, `items[]` with `allocated_invoices[]`.

Amounts use **`currency_integer`**: full company currency with **no** K/M compaction and **no** decimals. Prefer `paid_amount_display` / `summary.collected_display` for UI; `paid_amount` remains a float for sorting/math. `meta.amount_format` is `currency_integer`.

**Totals:** `summary.collected` / `summary.net` use **`gl_net`**: General Ledger **debit − credit** on each Mode of Payment default account for the period (matches GL report “Total” net for that account). Branch MoPs (e.g. `Cash Collection - Dammam`) include journal credits on the same account. Shared MoPs in a territory drill (e.g. `Wire Transfer`) use summed **Payment Entry paid** in that drill only. Each MoP row includes `debit`, `credit`, `net`, `amount_basis`. Payment line items still show individual `paid_amount`.

Each item includes:

| Field | Source |
|--------|--------|
| `paid_amount_display` | Formatted SAR integer (e.g. Cash Collection rows) |
| `mode_of_payment` | Payment Entry `mode_of_payment` |
| `receipt_number` | Payment Entry `receipt_no`, else `payment_entry` name |
| `receipt_no` | Same as `receipt_number` (alias) |
| `reference_no` | Payment Entry `reference_no` (bank / customer ref) |

## Mobile config

`apis.get_collection_payments` — enabled by default when omitted from Mobile App Settings.

### Native mobile (required UI wiring)

The **Printechs B2B app** must read server-provided display fields (bootstrap `capabilities.collection`):

| Use case | Field |
|----------|--------|
| Territory drill header / net total | `summary.collected_display` or `summary.net_debit_credit` |
| Cash / MoP line (GL net) | `mode_totals[]` / `summary.totals_by_mode_of_payment` → `collected_display` |
| Payment row amount | `paid_amount_display` (not `paid_amount` + local `K` formatter) |

Do **not** sum `items[].paid_amount` for MoP totals — use `mode_totals`. Reload app after deploy; pull-to-refresh on collection drill.
