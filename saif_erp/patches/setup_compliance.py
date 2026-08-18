# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Compliance Register setup: add the structured 'Period End Date' to Job Order,
backfill it by parsing the existing free-text period, and seed registers from the
existing VAT / Corporate Tax Job Orders. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from saif_erp.compliance import SERVICE_RULES, parse_period_end, seed_from_job_orders


def execute():
	# 1) structured period-end field on Job Order (deadlines can't be computed from the
	# free-text period reliably).
	create_custom_fields({
		"Job Order": [
			{"fieldname": "custom_period_end_date", "label": "Period End Date",
			 "fieldtype": "Date", "insert_after": "period",
			 "description": "Statutory period end — drives the filing deadline (VAT/Corporate Tax)."},
		]
	}, ignore_validate=True)

	# 2) backfill from the free-text period where we can parse it (fast db writes; the
	# register seed below is what actually builds the registers).
	if not frappe.db.has_column("Job Order", "custom_period_end_date"):
		return
	rows = frappe.get_all("Job Order",
	                      filters={"service": ["in", list(SERVICE_RULES)], "docstatus": ["<", 2],
	                               "custom_period_end_date": ["is", "not set"]},
	                      fields=["name", "period"])
	for r in rows:
		pe = parse_period_end(r.period)
		if pe:
			frappe.db.set_value("Job Order", r.name, "custom_period_end_date", pe, update_modified=False)
	frappe.db.commit()

	# 3) build registers from those Job Orders
	made = seed_from_job_orders()
	frappe.logger().info(f"[saif_erp] compliance seed processed {made} job orders")
