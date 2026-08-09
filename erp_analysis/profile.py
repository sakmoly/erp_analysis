import frappe
from frappe import _


def _employee_photo_url(employee_doc) -> str:
	photo = getattr(employee_doc, "image", None) or getattr(employee_doc, "photo_url", None)
	return f"{frappe.utils.get_url()}{photo}" if photo else ""


def _user_field(user_doc, fieldname: str, default: str = "") -> str:
	return getattr(user_doc, fieldname, None) or default


def build_user_profile_data(username: str) -> dict:
	"""Build user + employee profile payload for dashboard and profile screens."""
	try:
		user_doc = frappe.get_doc("User", username)

		employee_data = {
			"employee_name": "",
			"company": "",
			"designation": "",
			"branch": "",
			"cell_number": "",
			"company_email": user_doc.email or "",
			"current_address": "",
			"photo_url": "",
			"country": "",
		}

		if user_doc.email:
			employee = frappe.db.get_value("Employee", {"company_email": user_doc.email}, "name")
			if employee:
				employee_doc = frappe.get_doc("Employee", employee)
				employee_data.update(
					{
						"employee_name": employee_doc.employee_name or "",
						"company": employee_doc.company or "",
						"designation": employee_doc.designation or "",
						"branch": employee_doc.branch or "",
						"cell_number": employee_doc.cell_number or "",
						"company_email": employee_doc.company_email or user_doc.email or "",
						"current_address": employee_doc.current_address or "",
						"photo_url": getattr(employee_doc, "image", None)
						or getattr(employee_doc, "photo_url", None)
						or "",
						"country": employee_doc.country or "",
					}
				)

		if employee_data.get("photo_url"):
			image_url = f"{frappe.utils.get_url()}{employee_data['photo_url']}"
		elif user_doc.user_image:
			image_url = f"{frappe.utils.get_url()}{user_doc.user_image}"
		else:
			image_url = f"{frappe.utils.get_url()}/files/Sakeer.png"

		return {
			"image_url": image_url,
			"employee_name": employee_data["employee_name"] or user_doc.full_name,
			"company": employee_data["company"],
			"designation": employee_data["designation"],
			"branch": employee_data["branch"],
			"cell_number": employee_data["cell_number"],
			"company_email": employee_data["company_email"],
			"current_address": employee_data["current_address"],
			"country": employee_data["country"],
		}
	except Exception as e:
		frappe.log_error(f"User Profile Error: {str(e)}")
		return {
			"image_url": f"{frappe.utils.get_url()}/files/Sakeer.png",
			"employee_name": "User",
			"company": "",
			"designation": "",
			"branch": "",
			"cell_number": "",
			"company_email": "",
			"current_address": "",
			"country": "",
		}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=False)
def get_complete_profile_data():
	"""Complete profile payload including vCard QR data."""
	try:
		current_user = frappe.get_user()
		user_doc = frappe.get_doc("User", current_user.name)

		employee_data = None
		employee_doc = None
		if user_doc.email:
			employee = frappe.db.get_value("Employee", {"company_email": user_doc.email}, "name")
			if employee:
				employee_doc = frappe.get_doc("Employee", employee)
				employee_data = {
					"employee_name": employee_doc.employee_name,
					"company_email": employee_doc.company_email,
					"cell_number": employee_doc.cell_number,
					"designation": employee_doc.designation,
					"department": employee_doc.department,
					"company": employee_doc.company,
					"branch": employee_doc.branch,
					"current_address": employee_doc.current_address,
					"photo_url": _employee_photo_url(employee_doc)
					or f"{frappe.utils.get_url()}/files/Sakeer.png",
				}

		user_info = {
			"username": user_doc.username,
			"full_name": user_doc.full_name or user_doc.username,
			"email": user_doc.email,
			"mobile_no": user_doc.mobile_no or "",
			"designation": _user_field(user_doc, "designation"),
			"department": _user_field(user_doc, "department"),
			"company": _user_field(user_doc, "company", "Printechs"),
			"image_url": (
				f"{frappe.utils.get_url()}{user_doc.user_image}"
				if user_doc.user_image
				else f"{frappe.utils.get_url()}/files/Sakeer.png"
			),
		}

		return {
			"user_info": user_info,
			"employee_info": employee_data,
			"qr_data": generate_vcard_data(user_doc, employee_doc),
		}
	except Exception as e:
		frappe.log_error(f"Profile API Error: {str(e)}")
		frappe.throw(_("Error fetching profile data: {0}").format(str(e)))


def generate_vcard_data(user_doc, employee_doc=None) -> str:
	"""Generate vCard data for QR code."""
	try:
		name = employee_doc.employee_name if employee_doc else user_doc.full_name
		email = employee_doc.company_email if employee_doc else user_doc.email
		phone = employee_doc.cell_number if employee_doc else user_doc.mobile_no
		title = employee_doc.designation if employee_doc else _user_field(user_doc, "designation")
		org = employee_doc.company if employee_doc else _user_field(user_doc, "company")
		address = employee_doc.current_address if employee_doc else ""

		vcard = [
			"BEGIN:VCARD",
			"VERSION:3.0",
			f"FN:{name or user_doc.username}",
			f"EMAIL:{email}" if email else "",
			f"TEL:{phone}" if phone else "",
			f"TITLE:{title}" if title else "",
			f"ORG:{org}" if org else "",
			f"ADR:;;{address}" if address else "",
			"END:VCARD",
		]
		return "\n".join(line for line in vcard if line)
	except Exception as e:
		frappe.log_error(f"vCard Generation Error: {str(e)}")
		return "BEGIN:VCARD\nVERSION:3.0\nFN:User\nEND:VCARD"
