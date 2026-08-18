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

	frappe.clear_cache(doctype="Employee")
