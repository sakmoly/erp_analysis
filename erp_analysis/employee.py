import frappe
from frappe import _
from frappe.utils import get_url

from erp_analysis.utils.rpc import absolute_file_url

# In ERPNext, this helper renders the Address nicely (multi-line)
try:
	from erpnext.utilities.doctype.address.address import get_address_display
except Exception:
	def get_address_display(name: str) -> str:
		return name or ""

@frappe.whitelist(methods=["GET", "POST"])
def get_employee_profile(email: str | None = None):
	target_email = (email or frappe.session.user or "").strip()
	if not target_email or target_email.lower() in {"guest"}:
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	# 1) Strong match by company_email first
	emp_name = frappe.db.get_value("Employee", {"company_email": target_email}, "name")

	# 2) Fallback to user_id if no company_email match
	if not emp_name:
		emp_name = frappe.db.get_value("Employee", {"user_id": target_email}, "name")

	# If not found, return minimal profile for the login
	if not emp_name:
		return {
			"user_profile": {
				"image_url": "",
				"employee_name": target_email.split("@")[0],
				"company": "",
				"designation": "",
				"branch": "",
				"territory": "",
				"cell_number": "",
				"company_email": target_email,
				"current_address": "",
				"country": "",
			}
		}

	doc = frappe.get_doc("Employee", emp_name)

	# Safety: reject mismatches (defensive against wrong links in DB)
	if (getattr(doc, "company_email", "") or "").strip().lower() not in {target_email.lower(), ""} \
		and (getattr(doc, "user_id", "") or "").strip().lower() not in {target_email.lower(), ""}:
		return {
			"user_profile": {
				"image_url": "",
				"employee_name": target_email.split("@")[0],
				"company": "",
				"designation": "",
				"branch": "",
				"territory": "",
				"cell_number": "",
				"company_email": target_email,
				"current_address": "",
				"country": "",
			}
		}

	raw_img = getattr(doc, "image_url", None) or getattr(doc, "image", None) or getattr(doc, "photo", None) or ""
	image_url = absolute_file_url(raw_img) or absolute_file_url(
		frappe.db.get_value("User", target_email, "user_image") or ""
	)
	territory = getattr(doc, "territory", None) or getattr(doc, "branch", "") or ""
	country = getattr(doc, "country", "") if hasattr(doc, "country") else ""

	return {
		"user_profile": {
			"image_url": image_url,
			"employee_name": getattr(doc, "employee_name", "") or "",
			"company": getattr(doc, "company", "") or "",
			"designation": getattr(doc, "designation", "") or "",
			"branch": getattr(doc, "branch", "") or "",
			"territory": territory,
			"cell_number": getattr(doc, "cell_number", "") or "",
			"company_email": getattr(doc, "company_email", "") or target_email,
			"current_address": getattr(doc, "current_address", "") or "",
			"country": country,
		}
	}
@frappe.whitelist()
@frappe.read_only()
def get_employees(
    employee: str | None = None,
    company: str | None = None,
    branch: str | None = None,
    designation: str | None = None,
    limit_start: int = 0,
    limit_page_length: int = 50,
):
    """
    Return a paginated list of Employees with key fields and a photo URL.
    All filters are optional. If `employee` is provided, returns that record only.

    Query params (all optional):
      - employee: Employee Name/ID (e.g., EMP-0001)
      - company, branch, designation
      - limit_start (default 0), limit_page_length (default 50)

    Response:
      {
        "data": [
          {
            "name": "EMP-0001",
            "employee_name": "John Doe",
            "designation": "Sales Manager",
            "company": "Printechs",
            "cell_number": "0501234567",
            "company_email": "john@printechs.com",
            "branch": "Dammam",
            "current_address": "ADDR-0005",
            "current_address_display": "John Doe\nStreet...\nCity ...",
            "photo_url": "https://your-site/files/john.jpg"
          },
          ...
        ],
        "pagination": {"limit_start": 0, "limit_page_length": 50, "returned": 12}
      }
    """
    from erp_analysis.security import require_authenticated_user

    require_authenticated_user()

    # Build filters safely
    filters = {}
    if employee:
        filters["name"] = employee
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch
    if designation:
        filters["designation"] = designation

    # Pull core fields from Employee
    fields = [
        "name",
        "employee_name",
        "designation",
        "company",
        "cell_number",
        "company_email",
        "branch",
        "current_address",
        "image",  # Attach Image field on Employee
    ]

    rows = frappe.get_all(
        "Employee",
        filters=filters,
        fields=fields,
        limit_start=frappe.utils.cint(limit_start),
        limit_page_length=frappe.utils.cint(limit_page_length),
        order_by="modified desc",
    )

    data = []
    for r in rows:
        # Resolve image to absolute URL (or None)
        photo_url = get_url(r.image) if r.get("image") else None

        # Expand linked Address into display text (if any)
        addr_name = r.get("current_address")
        addr_display = get_address_display(addr_name) if addr_name else None

        data.append({
            "name": r.name,
            "employee_name": r.employee_name,
            "designation": r.designation,
            "company": r.company,
            "cell_number": r.cell_number,
            "company_email": r.company_email,
            "branch": r.branch,
            "current_address": addr_name,
            "current_address_display": addr_display,
            "photo_url": photo_url,
        })

    return {
        "data": data,
        "pagination": {
            "limit_start": int(limit_start),
            "limit_page_length": int(limit_page_length),
            "returned": len(data),
        },
    }


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_complete_employees_data(
	department=None, designation=None, search=None, limit=50, offset=0, **kwargs
):
	"""Complete employees list with departments and designations for mobile."""
	try:
		search_conditions = ""
		if search:
			search_conditions = f"""
				AND (employee_name LIKE '%{search}%'
				OR employee_id LIKE '%{search}%'
				OR company_email LIKE '%{search}%')
			"""

		employees = frappe.db.sql(
			f"""
			SELECT
				name,
				employee_name,
				designation,
				department,
				company,
				image,
				company_email,
				cell_number,
				branch
			FROM `tabEmployee`
			WHERE status = 'Active'
			{search_conditions}
			ORDER BY employee_name
			LIMIT {int(limit)} OFFSET {int(offset)}
			""",
			as_dict=True,
		)

		total_count = frappe.db.count("Employee", {"status": "Active"})
		departments = frappe.db.sql(
			"""
			SELECT DISTINCT department
			FROM `tabEmployee`
			WHERE status = 'Active' AND department IS NOT NULL
			ORDER BY department
			""",
			as_dict=True,
		)
		designations = frappe.db.sql(
			"""
			SELECT DISTINCT designation
			FROM `tabEmployee`
			WHERE status = 'Active' AND designation IS NOT NULL
			ORDER BY designation
			""",
			as_dict=True,
		)

		processed_employees = []
		for emp in employees:
			photo = getattr(emp, "image", None) or getattr(emp, "photo_url", None)
			processed_employees.append(
				{
					"name": emp.name,
					"employee_name": emp.employee_name,
					"designation": emp.designation or "",
					"department": emp.department or "",
					"company": emp.company or "",
					"photo_url": absolute_file_url(photo) if photo else "",
					"company_email": emp.company_email or "",
					"cell_number": emp.cell_number or "",
					"branch": emp.branch or "",
				}
			)

		return {
			"employees": processed_employees,
			"total_count": total_count,
			"departments": [d.department for d in departments],
			"designations": [d.designation for d in designations],
		}
	except Exception as e:
		frappe.log_error(f"Employees API Error: {str(e)}")
		frappe.throw(_("Error fetching employees data: {0}").format(str(e)))