#!/usr/bin/env bash
# =============================================================================
# fix_cmd_kwargs.sh
#
# Fixes: TypeError: <method>() got an unexpected keyword argument 'cmd'
#
# Cause: Frappe passes form_dict (including "cmd") into **kwargs. Wrappers that
# forward **kwargs to printechs_utility must strip those keys first.
#
# Also fixes a bad generated call pattern:
#   return _impl("get_inventory_snapshot")(**kwargs)
# → return _impl(**kwargs)
#
# Run on the bench server:
#   export BENCH_PATH="$HOME/frappe-bench"
#   export MIGRATE_FROM_PRINTECHS=1   # keep calling printechs_utility (default)
#   chmod +x fix_cmd_kwargs.sh
#   ./fix_cmd_kwargs.sh
# =============================================================================
set -euo pipefail

BENCH_PATH="${BENCH_PATH:-$HOME/frappe-bench}"
MIGRATE_FROM_PRINTECHS="${MIGRATE_FROM_PRINTECHS:-1}"
PKG="${BENCH_PATH}/apps/erp_analysis/erp_analysis"

if [[ ! -d "$PKG" ]]; then
  echo "ERROR: Package not found: $PKG"
  echo "  export BENCH_PATH=/path/to/frappe-bench"
  exit 1
fi

echo "==> Rewriting wrappers under $PKG (MIGRATE_FROM_PRINTECHS=$MIGRATE_FROM_PRINTECHS)"

write_mod() {
  local file="$1"
  local old_mod="$2"
  shift 2
  local funcs=("$@")

  {
    echo 'import frappe'
    echo ''
    echo ''
    echo 'def _clean_kwargs(kwargs):'
    echo '    """Remove Frappe RPC form_dict noise before forwarding."""'
    echo '    for _k in ("cmd", "method", "csrf_token", "args", "kwargs"):'
    echo '        kwargs.pop(_k, None)'
    echo '    return kwargs'
    echo ''

    for func in "${funcs[@]}"; do
      echo ''
      echo ''
      echo "@frappe.whitelist()"
      echo "def ${func}(**kwargs):"
      if [[ "$MIGRATE_FROM_PRINTECHS" == "1" ]]; then
        cat <<EOF
    """Proxy to ${old_mod}.${func} while migrating."""
    kwargs = _clean_kwargs(kwargs)
    try:
        mod = frappe.get_module("${old_mod}")
        _impl = getattr(mod, "${func}")
        return _impl(**kwargs)
    except Exception:
        frappe.log_error(title="erp_analysis.${func}", message=frappe.get_traceback())
        raise
EOF
      else
        cat <<EOF
    """Stub until real BA logic is ported."""
    kwargs = _clean_kwargs(kwargs)
    return {"ok": True, "stub": True, "method": "erp_analysis.${func}", "kwargs": kwargs}
EOF
      fi
    done
  } > "$PKG/$file"

  echo "  wrote $file (${#funcs[@]} methods)"
}

write_mod inventory.py printechs_utility.inventory \
  get_inventory_snapshot get_inventory_performance get_inventory_trends \
  get_inventory_risk get_inventory_hierarchy

write_mod receivables.py printechs_utility.receivables \
  get_receivables_snapshot get_receivables_performance get_receivables_trends \
  get_receivables_dashboard get_territory_receivables get_customer_statement

write_mod employee.py printechs_utility.employee \
  get_complete_employees_data get_employee_profile get_employees

write_mod dashboard.py printechs_utility.dashboard \
  get_complete_dashboard_data

write_mod sales_kpis.py printechs_utility.sales_kpis \
  get_dashboard_kpis get_sales_dashboard

write_mod approvals.py printechs_utility.approvals \
  get_all_approvals approve_document reject_document inbox apply

write_mod catalogue.py printechs_utility.catalogue \
  get_catalogues_list get_catalogue_pages get_catalogue_flip_url

write_mod customer_notifications.py printechs_utility.customer_notifications \
  send_statement_pdf get_statement_pdf get_statement_branding

# api.py access helpers — keep health/config; fix get_my_access forwarding
cat > "$PKG/api.py" <<'EOF'
import frappe

APP_VERSION = "1.0.0"


def _clean_kwargs(kwargs):
    for _k in ("cmd", "method", "csrf_token", "args", "kwargs"):
        kwargs.pop(_k, None)
    return kwargs


@frappe.whitelist(allow_guest=True)
def health():
    return {
        "ok": True,
        "status": "ok",
        "version": APP_VERSION,
        "message": "erp_analysis is available",
    }


@frappe.whitelist()
def get_mobile_config(**kwargs):
    _clean_kwargs(kwargs)
    return {
        "app": "erp_analysis",
        "version": APP_VERSION,
        "modules": {
            "sales": True,
            "receivables": True,
            "inventory": True,
            "approvals": True,
            "catalogue": False,
            "push": False,
            "settings": True,
        },
        "dashboards": [
            {
                "id": "home",
                "title": "Dashboard",
                "module": "sales",
                "widgets": [
                    {"id": "sales_card", "type": "expandable", "title": "Sales Performance"},
                    {"id": "receivables_card", "type": "expandable", "title": "Receivables"},
                    {"id": "inventory_card", "type": "expandable", "title": "Inventory"},
                ],
            }
        ],
    }


@frappe.whitelist()
def get_my_access(**kwargs):
    kwargs = _clean_kwargs(kwargs)
    try:
        from printechs_utility.api import get_my_access as _impl
        return _impl(**kwargs)
    except Exception:
        return {"scope": kwargs, "profiles": []}


@frappe.whitelist()
def clear_my_access_cache(user=None, **kwargs):
    _clean_kwargs(kwargs)
    try:
        from printechs_utility.api import clear_my_access_cache as _impl
        return _impl(user=user)
    except Exception:
        return {"ok": True}


@frappe.whitelist()
def store_push_token(**kwargs):
    _clean_kwargs(kwargs)
    return {"ok": True, "stored": False, "phase": 2}
EOF
echo "  wrote api.py"

echo ""
echo "==> Clearing cache & restarting"
cd "$BENCH_PATH"
bench clear-cache || true
bench restart || true

echo ""
echo "Done. Retry inventory / receivables / profile from the mobile app."
echo "If errors persist, confirm printechs_utility methods accept the remaining kwargs."
