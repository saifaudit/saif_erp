# Copyright (c) 2026, SGA World FZ LLC and contributors
"""SAIF's custom doctypes were filed under the ERPNext 'Accounts' module, so their
list views inherited the Accounts sidebar (Budget Variance, Consolidated Financial
Statements, etc.) — irrelevant and confusing for staff accountants. Refile them
under the 'SAIF ERP' module so the sidebar shows SAIF content instead. Idempotent."""

import frappe

# custom SAIF doctypes to move out of 'Accounts' into 'SAIF ERP'
DOCTYPES = [
	"Job Order",
	"Job Order Contributors",
	"Credential Manager",
	"Physical File Management",
	"AML",
	"Sales Representative",
]


def execute():
	if not frappe.db.exists("Module Def", "SAIF ERP"):
		return
	for dt in DOCTYPES:
		if not frappe.db.exists("DocType", dt):
			continue
		if frappe.db.get_value("DocType", dt, "module") != "SAIF ERP":
			frappe.db.set_value("DocType", dt, "module", "SAIF ERP", update_modified=False)
	frappe.clear_cache()
