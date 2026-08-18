# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Post-login employee experience: land on the SGA Dashboard and hide the ERPNext
modules staff never use from the sidebar. Idempotent; reversible (clear home_page
back to /app, delete the added Has Role rows). DB-only for workspaces so ERPNext's
own workspace files are never touched."""

import frappe

MANAGER_ROLES = ["System Manager", "Administrator", "Job Order Admin", "Job Order Partner",
                 "HR Manager", "Accounts Manager"]
# irrelevant-to-staff public workspaces → restricted to managers only
HIDE = ["HR Setup", "Invoicing", "Tenure", "Recruitment", "Financial Reports", "Expenses",
        "Selling", "Manufacturing", "Subcontracting", "Buying", "Assets", "Performance",
        "Welcome Workspace", "Website", "Tax & Benefits", "Integrations"]


def _ensure_ws_role(ws, role):
	if frappe.db.exists("Has Role", {"parenttype": "Workspace", "parent": ws, "role": role}):
		return
	idx = frappe.db.count("Has Role", {"parenttype": "Workspace", "parent": ws}) + 1
	frappe.db.sql(
		"""insert into `tabHas Role`
		(name, parent, parenttype, parentfield, role, idx, creation, modified, owner, modified_by, docstatus)
		values (%s,%s,'Workspace','roles',%s,%s, now(), now(), 'Administrator','Administrator',0)""",
		(frappe.generate_hash(length=10), ws, role, idx))


def execute():
	# 1) land on the SGA Dashboard after login — the desk home is the
	# `desktop:home_page` default (boot loads it as a Page), NOT the website
	# home_page (which desk users bypass).
	if frappe.db.exists("Page", "sga-dashboard"):
		frappe.db.set_default("desktop:home_page", "sga-dashboard")

	# 1b) clear the per-user `default_workspace` (ERPNext ships it as "Home").
	# It overrides the global desktop:home_page default, so users would land on
	# the Home workspace instead of the SGA Dashboard. Blank it so the global
	# default wins. Only touch the stock "Home" value; leave deliberate choices.
	frappe.db.sql("update `tabUser` set default_workspace='' where default_workspace='Home'")

	# 2) hide irrelevant workspaces from staff (only where not already restricted)
	for name in HIDE:
		if not frappe.db.exists("Workspace", name):
			continue
		if frappe.get_all("Has Role", {"parenttype": "Workspace", "parent": name}, pluck="role"):
			continue
		for r in MANAGER_ROLES:
			_ensure_ws_role(name, r)

	# 2b) the ERPNext 'Home' workspace ships Chart of Accounts / Stock / Item / Settings
	# links and is granted to Employee/Accountant — so on the bare desk staff & Admin
	# Support land on its cluttered sidebar instead of the clean SGA one. Restrict Home
	# to management: replace its roles with MANAGER_ROLES so staff never see it.
	if frappe.db.exists("Workspace", "Home"):
		frappe.db.delete("Has Role", {"parenttype": "Workspace", "parent": "Home"})
		for r in MANAGER_ROLES:
			_ensure_ws_role("Home", r)

	frappe.clear_cache()
