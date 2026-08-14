# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Disable (not delete) the three legacy monthly reports now merged into
'SGA Monthly Job Order Report'. Idempotent and reversible."""

import frappe

OLD = [
	"My Contributor Job Orders",
	"Employee Work Flow Report",
	"Monthly Job Order Report – Staff",
]


def execute():
	for name in OLD:
		if frappe.db.exists("Report", name):
			frappe.db.set_value("Report", name, "disabled", 1)
