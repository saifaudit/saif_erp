# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from saif_erp.compliance import compute_due_date


class ComplianceRegister(Document):
	def validate(self):
		for p in self.periods:
			if p.period_end_date:
				p.due_date = compute_due_date(self.service, p.period_end_date)
				if not p.period_label:
					p.period_label = str(getdate(p.period_end_date))
