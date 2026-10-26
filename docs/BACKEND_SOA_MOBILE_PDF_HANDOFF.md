# Backend SOA mobile PDF handoff

Mobile WhatsApp **Share statement PDF** must use the **same PDF as desk/email**: Print Format **`Customer Outstanding SOA`**.

## Methods

| Method | Notes |
|--------|--------|
| `erp_analysis.customer_notifications.get_statement_pdf` | Primary |
| `printechs_utility.customer_notifications.get_statement_pdf` | Legacy delegate → erp_analysis |
| `erp_analysis.customer_notifications.send_statement_pdf` | Fallback when `send_email=0` and/or `return_pdf=1` |

All are whitelisted (`allow_guest=False`), **GET + POST**, OAuth Bearer.

## Request

```http
POST /api/method/erp_analysis.customer_notifications.get_statement_pdf
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "customer_name": "USG Middle East Ltd.",
  "customer": "USG Middle East Ltd.",
  "company": "Printechs Advanced Printing Trading Co.",
  "from_date": "2011-01-01",
  "to_date": "2026-10-21",
  "print_format": "Customer Outstanding SOA",
  "send_email": 0,
  "return_pdf": true,
  "return_file_url": true,
  "delivery": "download"
}
```

| Parameter | Required | Notes |
|-----------|----------|--------|
| `customer_name` / `customer` | Yes | Customer **link name** (e.g. `USG Middle East Ltd.`) |
| `company` | No | Defaults to user default Company |
| `from_date`, `to_date` | No | **Metadata only** — does not filter SOA invoice lines |
| `print_format` | No | Default `Customer Outstanding SOA` |
| `send_email` | No | Ignored for generation; must not send mail from `get_statement_pdf` |
| `return_file_url` | No | Default **true** — saves private File, returns `file_url` |
| `return_pdf` | No | Default false — if true, also returns `pdf_base64` |
| `delivery` | No | Ignored (mobile hint) |

RPC noise (`cmd`, `method`, nested `kwargs` JSON) is merged via `expand_rpc_kwargs` to avoid **417** / missing-parameter errors.

### Permissions (do not weaken desk)

| User type | Rules |
|-----------|--------|
| **Access Profile** (mobile) | Must have `get_statement_pdf` on profile + customer in **view territory** scope. Customer ERPNext **print** role not required. During PDF render only, `frappe.get_list` / `get_all` are wrapped with `ignore_permissions=True` so Print Format Jinja can load Sales Invoice rows (global `frappe.flags.ignore_permissions` is **not** enough; otherwise PDF is letterhead-only). |
| **No Access Profile** (desk / legacy) | Unchanged: requires normal Customer **print** permission via `doc.check_permission("print")`. |
| **Email** (`send_statement_pdf` with mail) | Uses `_generate_customer_soa_pdf` without profile bypass — same as before. |

## Response

Frappe wraps with `message`; `wrap_mobile_message` also duplicates top-level keys.

```json
{
  "message": {
    "file_url": "/private/files/Statement_of_Account_usg_middle_east_ltd..pdf",
    "pdf_url": "https://site1.local/private/files/...",
    "print_format": "Customer Outstanding SOA",
    "statement_pdf_scope": "outstanding_invoices",
    "soa_body_present": true,
    "outstanding_invoice_count": 13,
    "customer_name": "USG Middle East Ltd.",
    "company": "Printechs Advanced Printing Trading Co.",
    "from_date": "2011-01-01",
    "to_date": "2026-10-21",
    "footer_lines": [
      "Company :Advanced Printing Trading Co. (PRINTECHS) …",
      "Account :470000010006082000007",
      "Bank :Al Rajhi Bank",
      "IBAN :SA7980000470608012000007"
    ]
  }
}
```

Download private files with Bearer:

`/api/method/frappe.utils.file_manager.download_file?file_url=<encoded file_url>`

## PDF scope

- Generated with `frappe.get_print("Customer", customer_name, print_format=...)`.
- Same as desk **Print → Customer → Customer Outstanding SOA**.
- Open **outstanding** sales invoices (print-format logic), **not** YTD / period-filtered statement preview.

## Branding (`get_statement_branding`)

Used when mobile builds HTML fallback (local PDF disabled in production).

- **`footer_lines`**: Company / Account / Bank / IBAN — **not** postal address.
- **Source order**: bank block parsed from **Print Format HTML** (matches printed desk SOA footer), then Company **default Bank Account** if the format has no block.

Fix desk bank in **Print Format → Customer Outstanding SOA** (or set a valid Company default bank) so API and PDF stay aligned.

## Access

Register in **Access Object Registry** / Mobile Access Profile (same class as `get_customer_statement`):

- `erp_analysis.customer_notifications.get_statement_pdf`
- `printechs_utility.customer_notifications.get_statement_pdf`

Run patch: `erp_analysis.patches.sync_mobile_access_registry`.

## Internal QA (server)

```bash
bench --site site1.local execute erp_analysis.scripts.test_soa_pdf_internal.run
```

Expect `"all_ok": true` for **sakeer@printechs.com** (LANDMARK + USG): `soa_body_present`, PDF text contains **Statement Of Account**.

**Mobile app:** Do **not** scan raw PDF bytes for `"Statement Of Account"` (compressed PDF → false negative → “letterhead only”). Trust API fields **`soa_body_present`** / **`soa_pdf_verified`** from JSON, or run a PDF text extractor on device.

## Manual tests

1. Postman with mobile user token — USG Middle East Ltd.
2. Repeat — Apparel Trading Co. Ltd.
3. Compare PDF to desk print for same customer (As On date, PO column, footer, bank block).
4. Expect **HTTP 200**; if **403** → profile; **417** → kwargs/method; **404** → customer id.

## Deploy

```bash
bench --site site1.local migrate
bench restart
bench --site site1.local clear-cache
```
