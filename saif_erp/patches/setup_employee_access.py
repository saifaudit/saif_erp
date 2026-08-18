# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Employee access model:
- Admin Support (and top management) can view/edit Employee records EXCEPT salary,
  bank and contract details.
- Those sensitive fields move to permlevel 1; only HR + super-admin roles get level 1.
- Adds an 'Employment Contract' upload (Attach) at permlevel 1 for onboarding.
Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property

# salary / bank / contract fields -> permlevel 1 (hidden from Admin Support & staff)
LEVEL1_FIELDS = [
	"salary_information", "ctc", "salary_currency", "salary_mode",
	"bank_details_section", "bank_name", "bank_ac_no", "iban",
	"contract_end_date",
]

# permlevel 0 (all non-sensitive fields): can read+write+create Employee
EDIT_ROLES = ["Job Order Admin Support", "System Manager", "Job Order Admin", "Job Order Partner"]
# permlevel 1 (salary/bank/contract): HR + super-admin only
SENSITIVE_ROLES = ["HR Manager", "HR User", "System Manager", "Job Order Admin", "Job Order Partner"]


def execute():
	# 1) restrict sensitive fields to permlevel 1
	for fieldname in LEVEL1_FIELDS:
		if frappe.db.exists("DocField", {"parent": "Employee", "fieldname": fieldname}):
			make_property_setter("Employee", fieldname, "permlevel", 1, "Int",
			                     validate_fields_for_doctype=False)

	# 2) contract upload field (permlevel 1) for onboarding
	create_custom_fields({
		"Employee": [
			{"fieldname": "custom_contract_document", "label": "Employment Contract",
			 "fieldtype": "Attach", "insert_after": "contract_end_date", "permlevel": 1},
		]
	}, ignore_validate=True)

	# 3) permlevel-0 edit access (everything except the sensitive fields)
	for role in EDIT_ROLES:
		add_permission("Employee", role, 0)
		for ptype in ("read", "write", "create"):
			update_permission_property("Employee", role, 0, ptype, 1, validate=False)

	# 4) permlevel-1 access to the sensitive fields (HR + super-admin)
	for role in SENSITIVE_ROLES:
		add_permission("Employee", role, 1)
		for ptype in ("read", "write"):
			update_permission_property("Employee", role, 1, ptype, 1, validate=False)

	# 5) Admin Support must manage ALL employees. They carry a blanket "Employee = own"
	# User Permission (apply-to-all) that blocks opening other employees and scopes the
	# document report. Replace it with targeted restrictions so salary/payroll stay
	# scoped to their own, while the Employee doctype + report open up.
	_free_admin_support_employee_access()

	frappe.clear_cache(doctype="Employee")


# payroll doctypes to keep scoped to the user's own record (Employee.ctc itself is
# already hidden by permlevel 1 above).
SCOPED_PAYROLL_DOCTYPES = ["Salary Slip", "Salary Structure Assignment"]


def _free_admin_support_employee_access():
	# management roles that must be able to manage all employees
	roles = ["Job Order Admin Support", "Job Order Admin", "Job Order Partner"]
	users = set(frappe.get_all("Has Role",
	                           {"role": ["in", roles], "parenttype": "User"}, pluck="parent"))
	for user in users:
		emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
		if not emp:
			continue
		# drop the blanket apply-to-all Employee restriction
		for up in frappe.get_all("User Permission",
		                         {"user": user, "allow": "Employee", "apply_to_all_doctypes": 1}, pluck="name"):
			frappe.delete_doc("User Permission", up, ignore_permissions=True, force=True)
		# keep payroll scoped to their own employee
		for dt in SCOPED_PAYROLL_DOCTYPES:
			if not frappe.db.exists("User Permission",
			                        {"user": user, "allow": "Employee", "for_value": emp, "applicable_for": dt}):
				frappe.get_doc({
					"doctype": "User Permission", "user": user, "allow": "Employee",
					"for_value": emp, "apply_to_all_doctypes": 0, "applicable_for": dt,
				}).insert(ignore_permissions=True)
