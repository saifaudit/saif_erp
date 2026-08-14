# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Disable (not delete) obsolete/broken custom reports now covered by the SGA
report set. Idempotent and reversible (set disabled=0 to bring one back)."""

import frappe

OBSOLETE = [
	"Monthly Job Order Report – Admin",       # -> SGA Monthly Job Order Report
	"Employee Performance Summary",           # -> SGA Monthly Job Order Report + rating
	"Admin Employee Productivity Report",     # -> rating / leaderboard
	"For the month of February",              # obsolete month-specific leftover
	"Admin Attendance Summary – Date Range (IN/OUT)",  # broken; -> SGA attendance reports
]


def execute():
	for name in OBSOLETE:
		if frappe.db.exists("Report", name):
			frappe.db.set_value("Report", name, "disabled", 1)
