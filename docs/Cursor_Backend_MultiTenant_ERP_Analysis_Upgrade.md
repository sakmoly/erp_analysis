# Cursor AI Implementation Guide — ERP Analysis Backend
## Multi-Customer, Multi-Industry, Configuration-Driven Architecture + Security Hardening

**Project:** `erp_analysis`  
**Framework:** Frappe / ERPNext v15  
**Objective:** Upgrade the existing backend in-place. Do **not** rewrite the application.

---

# 1. Mission

Modify the existing `erp_analysis` application so it can safely support the same mobile application for multiple customer/business types:

- B2B / distribution / industrial companies such as Printechs
- General retail / supermarket
- Fashion retail
- Modern POS → ERPNext customers
- Future business types without customer-specific mobile code

The backend must become:

1. Secure by default.
2. Configuration-driven.
3. Module-driven.
4. Metadata/dimension-driven.
5. Compatible with ERPNext standard fields **and custom fields**.
6. Backward compatible with the existing Printechs mobile application while the mobile changes are rolled out.
7. Controlled by the existing `Access Profile` permission architecture.
8. Free of customer-name-specific logic.

Do not create code such as:

```python
if customer == "Printechs":
    ...
elif customer == "ShoeArena":
    ...
```

Use business profiles, modules, features, dimensions and field mappings instead.

---

# 2. Existing Architecture — Preserve It

The project already contains useful building blocks. Reuse and extend them.

Important existing components include:

- `ERP Analysis`
- `Access Profile`
- `Access Profile Line`
- `Access Profile Territory`
- `Access Object Registry`
- `Mobile App Settings`
- existing analytics/service modules
- existing mobile APIs
- territory/view/approval separation
- company/branch scope
- sales/stock/receivable view overrides
- OAuth support
- push token support

Do **not** replace `Access Profile` with a second permission system.

Use `Access Profile` for user authorization and create/extend mobile configuration for **feature availability and presentation**.

Authorization and configuration are different concerns:

- **Access Profile** = what the logged-in user is allowed to access.
- **Mobile App Profile** = what the customer/business installation supports and how the app should be composed.

The final effective capability must be the intersection of both.

Example:

```text
Mobile App Profile enables Receivables
AND
Access Profile grants user permission to Receivables
=
Receivables shown and callable
```

---

# 3. Mandatory Safety Rules for Cursor

Before changing code:

1. Create a new Git branch:

```bash
git checkout -b feature/multi-tenant-mobile-platform
```

2. Record the current commit:

```bash
git rev-parse HEAD
```

3. Do not modify Frappe/ERPNext core source files.
4. Do not delete existing APIs that the current app uses.
5. Do not rename existing API methods during the first implementation.
6. Do not use `ignore_permissions=True` unless:
   - it is strictly required,
   - the user scope is independently enforced first,
   - the code contains a comment explaining why it is safe,
   - and a permission/security test is added.
7. Do not introduce dynamic SQL identifiers directly from mobile request parameters.
8. Never trust a fieldname, DocType, table name, metric, dimension, sort expression or SQL fragment supplied by the client.
9. All configurable fields must be resolved from server-side configuration and validated using Frappe metadata.
10. Guest endpoints must be reviewed explicitly.
11. Never expose credentials, API secrets, OAuth secrets or full configuration to the mobile client.
12. Preserve current Printechs behavior until the dynamic mobile app consumes the new bootstrap API.

---

# 4. PHASE A — Security Hardening First

Complete this phase before implementing new dynamic analytics.

## A1. Remove Guest Access from Sensitive APIs

Review all:

```python
@frappe.whitelist(allow_guest=True)
```

Current sensitive findings include at least:

### `erp_analysis/employee.py`

Current:

```python
@frappe.whitelist(allow_guest=True)
@frappe.read_only()
def get_employees(...):
```

Change to authenticated only:

```python
@frappe.whitelist()
@frappe.read_only()
def get_employees(...):
```

Then enforce:

- logged-in user must not be `Guest`
- required mobile object/module access
- company scope
- territory/branch scope where relevant
- return only necessary fields
- do not expose private employee information unless required and authorized

Do not return unnecessary address, phone or personal data merely because it exists in Employee.

### `erp_analysis/sales_kpis.py`

Current sensitive methods include:

```python
@frappe.whitelist(allow_guest=True)
@frappe.whitelist()
@frappe.read_only()
def get_dashboard_kpis(...):
```

and:

```python
@frappe.whitelist(allow_guest=True)
def get_today_sales_kpis(...):
```

Remove `allow_guest=True`.

Financial, sales, stock, profitability, receivable, payable, purchase, customer and employee analytics must require authentication.

Also remove duplicate whitelist decorators where present.

## A2. Keep Only Deliberately Public Endpoints

The following may remain public **only after explicit review**:

### Health

```python
erp_analysis.api.health
```

Keep response minimal. It must not expose:

- version details that are unnecessary
- file paths
- stack traces
- database names
- installed apps
- server secrets

### OAuth Client ID Discovery

```python
erp_analysis.config.get_client_id
```

An OAuth **client ID** can be public.

Never return:

- client secret
- API secret
- refresh token
- access token
- administrator credential

### Catalogue Public Link

```python
erp_analysis.catalogue.get_catalogue_flip_url
```

If public catalogue access is intentional, validate that:

- only published/public catalogues can be returned,
- unpublished catalogues cannot be enumerated,
- no internal filesystem paths are exposed,
- no permission bypass can reveal private catalogue records.

If catalogue is not intended to be public, remove guest access.

## A3. Add a Central Authentication Guard

Create a reusable helper, for example:

```text
erp_analysis/security.py
```

with functions such as:

```python
def require_authenticated_user() -> str:
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)
    return user
```

Do not depend only on the absence of `allow_guest=True`.

Use this guard for sensitive analytics APIs.

## A4. Review Global Frappe Method Overrides

Current `hooks.py` globally overrides:

```python
override_whitelisted_methods = {
    "frappe.client.get_list": "erp_analysis.permissions.mobile_client.client_get_list",
    "frappe.client.get": "erp_analysis.permissions.mobile_client.client_get",
    "frappe.desk.reportview.get": "erp_analysis.permissions.mobile_client.reportview_get",
}
```

This is high risk because it can affect Frappe Desk as well as mobile.

Do not remove it blindly because existing behavior may depend on it.

Perform the following:

1. Document exactly why each override exists.
2. Confirm normal Desk users preserve standard ERPNext/Frappe permission behavior.
3. Restrict custom bypass behavior to users/calls that actually require the mobile access model.
4. Prefer dedicated `erp_analysis` mobile APIs for new functionality rather than increasing reliance on global Frappe overrides.
5. Review every `ignore_permissions=True` path in `permissions/mobile_client.py`.
6. Add tests proving:
   - unauthorized users cannot access records outside scope,
   - Desk users retain expected User Permission filtering,
   - territory scope cannot be bypassed via filters,
   - a caller cannot inject another territory/company,
   - direct `frappe.client.get_list` calls do not leak restricted data.

Long-term direction: new mobile functionality should use explicit `erp_analysis.*` APIs, not generic Frappe CRUD endpoints.

## A5. Error Handling

Sensitive API responses must not return:

- Python tracebacks
- SQL text
- internal paths
- secrets

Log detailed exceptions server-side and return safe API errors.

---

# 5. PHASE B — Add Multi-Customer Mobile Configuration

The project already has `Mobile App Settings`.

Do not delete it.

Introduce a reusable profile architecture.

## B1. New DocType: `Mobile App Profile`

Create a non-single DocType:

```text
Mobile App Profile
```

Suggested fields:

```text
profile_name                Data / required / unique
business_type               Select
enabled                     Check
company                     Link -> Company (optional if profile can be global)
default_dashboard           Data/Select
app_title                   Data
app_subtitle                Data
logo                        Attach Image (optional)
primary_locale              Data/Select
currency_source             Select
settings_json               Long Text / Code (advanced only)
```

Suggested `business_type` options:

```text
B2B
GENERAL_RETAIL
FASHION_RETAIL
SUPERMARKET
POS_RETAIL
HYBRID
```

Do not make business type determine permissions. It is a default template/category only.

## B2. Profile Assignment

Support profile resolution by:

1. user-specific assignment if needed,
2. company assignment,
3. site/default profile fallback.

Preferred initial design:

- add optional `mobile_app_profile` Link field to `Access Profile`,
- optionally support a default profile in `Mobile App Settings`.

The user must not be able to select another customer's profile from a request parameter.

Server resolves the profile from authenticated context.

## B3. New Child DocType: `Mobile App Module`

Suggested fields:

```text
module_key                  Data / required
label                       Data
enabled                     Check
sort_order                  Int
icon_key                    Data
route_key                   Data
feature_key                 Data
```

Module keys must be logical stable identifiers, for example:

```text
executive
sales
collection
sales_performance
sales_orders
receivables
customer_360
inventory
inventory_health
purchase
payables
profitability
exceptions
approvals
approval_analytics
catalogue
retail
fashion
pos_analysis
```

Never store React Native component filenames in ERPNext.

Use logical route/module keys.

## B4. New Child DocType: `Mobile Analysis Dimension`

This is critical for customer-specific custom fields.

Suggested fields:

```text
dimension_key               Data / required
label                       Data / required
enabled                     Check
source_doctype              Link -> DocType
source_field                Data
source_mode                 Select
join_path_json              Code/Long Text
data_type_override          Select
allow_filter                Check
allow_group_by              Check
allow_sort                  Check
sort_order                  Int
value_api_key               Data
```

Suggested `source_mode`:

```text
FIELD
STANDARD
DERIVED
RELATION
```

Examples:

Printechs:

```text
dimension_key: territory
source_doctype: Customer
source_field: territory
```

Fashion customer A:

```text
dimension_key: brand
source_doctype: Item
source_field: custom_brand
```

Fashion customer B:

```text
dimension_key: brand
source_doctype: Item
source_field: brand
```

Fashion customer C:

```text
dimension_key: season
source_doctype: Item
source_field: custom_season_code
```

The mobile application must use `dimension_key`, never assume the physical fieldname.

## B5. Validate Dynamic Fields

Create a service such as:

```text
erp_analysis/services/mobile_dimensions.py
```

Implement functions conceptually like:

```python
def get_profile_dimensions(profile_name):
    ...

def validate_dimension_definition(row):
    ...

def resolve_dimension(profile, dimension_key):
    ...

def get_dimension_values(profile, dimension_key, search=None, limit=50):
    ...
```

Validation requirements:

```python
meta = frappe.get_meta(source_doctype)
df = meta.get_field(source_field)
```

Reject invalid or unsafe fields.

Do not allow fields such as:

- Password
- Attach unless intentionally supported
- private/internal fields
- fields from forbidden DocTypes
- child-table fields unless an explicitly supported relation is configured

Maintain a server-side allowlist of permitted analytical source DocTypes, for example initially:

```text
Item
Customer
Supplier
Sales Invoice
Sales Invoice Item
Delivery Note
Delivery Note Item
Sales Order
Sales Order Item
Warehouse
Territory
Brand
Item Group
Customer Group
Branch
Cost Center
Employee
Sales Person
```

Expand intentionally.

## B6. New Child DocType: `Mobile Dashboard Widget`

Suggested fields:

```text
widget_key                  Data
label                       Data
widget_type                 Select
metric_key                  Data
module_key                  Data
dimension_key               Data
secondary_dimension_key     Data
enabled                     Check
sort_order                  Int
size                        Select
config_json                 Code
```

Suggested `widget_type`:

```text
KPI
BAR
LINE
PIE
DONUT
TABLE
RANKING
MATRIX
LIST
```

The client receives logical widget metadata.

Never send SQL or Python expressions to the mobile client.

---

# 6. PHASE C — Bootstrap API

Create one authenticated bootstrap endpoint.

Preferred method:

```text
erp_analysis.api.get_mobile_bootstrap
```

Signature should require no customer/company/profile ID from the client unless the user's Access Profile legitimately supports company switching.

Conceptual result:

```json
{
  "schema_version": 1,
  "user": {
    "email": "user@example.com",
    "full_name": "User Name"
  },
  "context": {
    "company": "Example Company",
    "profile": "FASHION-DEFAULT",
    "business_type": "FASHION_RETAIL"
  },
  "branding": {
    "app_title": "Business Insight"
  },
  "modules": [
    {
      "key": "sales",
      "label": "Sales",
      "enabled": true,
      "route_key": "sales"
    },
    {
      "key": "fashion",
      "label": "Fashion",
      "enabled": true,
      "route_key": "fashion"
    }
  ],
  "dimensions": [
    {
      "key": "brand",
      "label": "Brand",
      "data_type": "Link",
      "filterable": true,
      "groupable": true
    },
    {
      "key": "season",
      "label": "Season",
      "data_type": "Select",
      "filterable": true,
      "groupable": true
    }
  ],
  "dashboard": [],
  "permissions": {},
  "capabilities": {}
}
```

Important:

- Do **not** return physical custom field names to the client unless there is a compelling debugging/admin reason.
- Do not return DocType SQL names.
- Do not return secrets.
- Include `schema_version`.
- Return only modules allowed by both Mobile App Profile and Access Profile.
- Preserve the existing `get_mobile_config` endpoint for backward compatibility.
- New mobile versions should prefer `get_mobile_bootstrap`.

---

# 7. PHASE D — Generic Dimension APIs

Add generic APIs instead of adding one endpoint per custom field.

## D1. Dimension Metadata

Example:

```text
erp_analysis.analytics.get_dimensions
```

The server returns authorized configured dimensions.

## D2. Dimension Values

Example:

```text
erp_analysis.analytics.get_dimension_values
```

Input:

```json
{
  "dimension": "season",
  "search": "2026",
  "limit": 50
}
```

Server flow:

1. authenticate,
2. resolve user's Mobile App Profile,
3. verify dimension is enabled,
4. verify user has module/object access,
5. map logical dimension to server field,
6. validate metadata,
7. query values under company/access scope,
8. return normalized label/value objects.

Do not accept arbitrary `source_doctype` or `source_field` from the caller.

## D3. Generic Sales Analysis

Add a reusable method such as:

```text
erp_analysis.analytics.get_sales_analysis
```

Inputs may include:

```text
from_date
to_date
dimension
secondary_dimension (optional)
metric
filters
limit
order
```

`dimension` and `metric` must be logical allowlisted keys.

Example metrics:

```text
net_sales
gross_sales
sales_qty
gross_profit
gross_profit_percent
transactions
average_transaction
stock_qty
stock_value
sell_through
```

Do not implement all metrics in the first commit if not currently supported.

Start with stable existing sales metrics and add others incrementally.

## D4. Dynamic Filter Format

Use logical filters:

```json
{
  "filters": {
    "brand": ["NIKE", "ADIDAS"],
    "season": ["SS26"],
    "region": ["WEST"]
  }
}
```

Backend maps those logical dimensions to physical fields.

All filters must be validated against enabled dimensions.

Unknown dimensions must fail safely with HTTP/Frappe validation errors, not be silently injected into SQL.

---

# 8. PHASE E — Fashion Support

Add a new reusable backend module only where generic analytics is insufficient.

Suggested namespace:

```text
erp_analysis.fashion
erp_analysis.services.fashion
```

Initial reusable analyses:

```text
sales by style
sales by color
sales by size
sales by season
sales by brand
stock by style
stock by color
stock by size
style-color-size matrix
slow moving by fashion dimension
sell-through
```

All physical fields must come from `Mobile Analysis Dimension`.

Do not assume:

```text
custom_style
custom_color
custom_size
custom_season
```

A profile might map:

```text
style -> custom_article
color -> custom_colour_code
size -> custom_size_name
season -> custom_season_code
```

The analysis service must use logical keys.

---

# 9. PHASE F — Retail / Supermarket Support

Add reusable logical dimensions such as:

```text
region
store
department
category
subcategory
brand
supplier
cashier
hour
promotion
```

Do not require every site to implement every dimension.

Only enabled, valid dimensions should appear in bootstrap.

Potential modules:

```text
store performance
hourly sales
cashier performance
category performance
promotion performance
basket metrics
stock availability
```

Implement modules independently from customer names.

---

# 10. PHASE G — Access Profile Integration

The existing `Access Profile` remains the authorization authority.

Create central helpers, for example:

```text
erp_analysis/access_context.py
```

Conceptual methods:

```python
get_authenticated_access_context()
get_mobile_profile_for_user()
is_module_enabled()
require_module_access()
require_object_access()
get_effective_company()
get_effective_view_territories()
get_effective_approve_territories()
```

Avoid repeating slightly different permission logic in every API.

Effective access must consider:

- authenticated user
- enabled Access Profile
- company
- view territories
- approve territories
- branch
- allow_view_all_sales
- allow_view_all_stock
- allow_all_receivable
- Access Profile Lines / object rules
- enabled Mobile App Profile modules

For Administrator/System Manager, do not accidentally bypass tenant/company boundaries if the site later supports multiple operational companies.

---

# 11. PHASE H — API Contract and Compatibility

Do not break the existing mobile endpoints.

Current application already calls many methods through `src/api/endpoints.ts`.

Keep existing methods working while new generic APIs are introduced.

Add:

```text
schema_version
api_version
```

to the bootstrap response.

Create:

```text
docs/MOBILE_PLATFORM_API_V2.md
```

Document:

- authentication
- bootstrap
- modules
- dimensions
- dashboard widgets
- generic analytics
- errors
- pagination
- date format
- currency/number conventions
- permission behavior

Standard response shape for new APIs should be consistent.

Example:

```json
{
  "data": {},
  "meta": {
    "schema_version": 1
  }
}
```

Do not refactor all legacy responses in the same change. Keep compatibility.

---

# 12. PHASE I — Tests

Security tests are mandatory.

Add automated tests covering at minimum:

## Authentication

- Guest cannot call employee API.
- Guest cannot call sales KPI API.
- Guest cannot call receivable/payable/profit APIs.
- authenticated authorized user can call permitted APIs.

## Profile

- correct Mobile App Profile resolves for user.
- disabled profile is rejected/falls back safely.
- user cannot request another profile by passing a profile name.

## Dynamic Fields

- standard Item field works.
- custom Item field works.
- missing custom field is excluded or gives a controlled validation error.
- invalid fieldname cannot be injected.
- forbidden field is rejected.
- disabled dimension cannot be queried.

## Scope

- territory-restricted user cannot access another territory.
- company-restricted user cannot access another company.
- view-all-sales only affects intended modules.
- view-all-stock only affects stock modules.
- allow-all-receivable only affects receivable modules.
- approve territory remains separate from view territory.

## Global Override Regression

- normal Desk get_list behavior still respects ERPNext permission behavior.
- mobile special path cannot bypass security with crafted filters.

## Bootstrap

Test at least these profiles:

```text
B2B
FASHION_RETAIL
SUPERMARKET
```

Verify different module/dimension lists are returned without changing Python code.

---

# 13. PHASE J — Migration / Setup

Create patches/fixtures needed for:

- new DocTypes
- fields added to Access Profile
- default Mobile App Profile for existing Printechs installation
- default module rows matching current enabled behavior
- default dimensions matching current Printechs analysis

Existing Printechs users must continue to work after migration.

Create a default profile similar to:

```text
Profile: PRINTECHS-B2B
Business Type: B2B
```

Enable existing modules currently used by Printechs.

Map existing dimensions such as:

```text
company
territory
warehouse
brand
division
department
cost_center
branch
customer
customer_group
salesperson
item_group
```

Only add mappings that are valid in the current site.

---

# 14. Security Review Checklist Before Completion

Search the repository for:

```bash
rg "allow_guest=True|allow_guest\s*=\s*True" erp_analysis
rg "ignore_permissions=True|ignore_permissions\s*=\s*True" erp_analysis
rg "frappe\.db\.sql" erp_analysis
rg "eval\(|exec\(" erp_analysis
rg "api_secret|client_secret|password|token" erp_analysis
```

For every match:

- classify as safe/required or fix,
- document unusual permission bypasses,
- ensure no secret is returned in an API.

Run Python compilation/tests.

Example:

```bash
python -m compileall erp_analysis
```

Then run relevant Frappe tests on a development site.

---

# 15. Implementation Order / Commits

Use small commits.

Suggested sequence:

```text
1. security: remove guest access from sensitive analytics
2. security: add central auth/access guards
3. test: add API authentication and scope tests
4. feat: add Mobile App Profile DocTypes
5. feat: resolve effective mobile profile from Access Profile
6. feat: add bootstrap API
7. feat: add metadata-driven dimensions
8. feat: add generic dimension-value API
9. feat: add generic sales analysis
10. feat: add fashion analytics foundation
11. docs: add API v2 contract
12. chore: migration/default Printechs profile
```

After each commit run tests.

Do not combine security, permission refactors and large analytics rewrites into one commit.

---

# 16. Definition of Done

Backend work is complete only when:

- existing Printechs mobile APIs still work,
- no sensitive analytics endpoint permits Guest access,
- employee listing is authenticated and scoped,
- financial KPIs are authenticated and scoped,
- OAuth login still works,
- public catalogue behavior still works if intentionally public,
- Mobile App Profile exists,
- profile is resolved server-side,
- bootstrap API works,
- modules are configuration-driven,
- custom dimensions are metadata-driven,
- standard/custom ERPNext fields can be mapped per profile,
- mobile never needs to know the physical custom fieldname,
- crafted dimension/field input cannot cause arbitrary SQL access,
- Access Profile is enforced,
- B2B/Fashion/Supermarket sample profiles produce different capabilities,
- tests pass,
- no Frappe/ERPNext core files were modified.

---

# 17. Final Cursor Instruction

First inspect the current code and produce a concise implementation report showing:

1. exact files to modify,
2. exact new files/DocTypes to create,
3. current guest endpoints,
4. current `ignore_permissions=True` paths,
5. current Access Profile helper functions that can be reused,
6. backward-compatibility risks.

Then implement the phases in order.

Do not rewrite working modules unnecessarily.

When an architectural decision is uncertain, prefer:

```text
security
backward compatibility
server-side validation
logical keys
configuration
reusable modules
```

over customer-specific conditions or hard-coded ERPNext custom field names.
