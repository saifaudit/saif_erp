# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Add UAE document fields to Employee for expiry tracking/alerts (Passport already
exists as passport_number/valid_upto). Idempotent — create_custom_fields skips
existing fields."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({
		"Employee": [
			{"fieldname": "custom_document_expiry_sb", "label": "Document Expiry (UAE)",
			 "fieldtype": "Section Break", "insert_after": "valid_upto", "collapsible": 1},
			{"fieldname": "custom_visa_number", "label": "Residence Visa No",
			 "fieldtype": "Data", "insert_after": "custom_document_expiry_sb"},
			{"fieldname": "custom_visa_expiry", "label": "Visa Expiry",
			 "fieldtype": "Date", "insert_after": "custom_visa_number"},
			{"fieldname": "custom_emirates_id", "label": "Emirates ID",
			 "fieldtype": "Data", "insert_after": "custom_visa_expiry"},
			{"fieldname": "custom_emirates_id_expiry", "label": "Emirates ID Expiry",
			 "fieldtype": "Date", "insert_after": "custom_emirates_id"},
			{"fieldname": "custom_document_expiry_cb", "fieldtype": "Column Break",
			 "insert_after": "custom_emirates_id_expiry"},
			{"fieldname": "custom_labour_card_no", "label": "Labour Card No",
			 "fieldtype": "Data", "insert_after": "custom_document_expiry_cb"},
			{"fieldname": "custom_labour_card_expiry", "label": "Labour Card Expiry",
			 "fieldtype": "Date", "insert_after": "custom_labour_card_no"},
			{"fieldname": "custom_insurance_policy", "label": "Health Insurance Policy",
			 "fieldtype": "Data", "insert_after": "custom_labour_card_expiry"},
			{"fieldname": "custom_insurance_expiry", "label": "Insurance Expiry",
			 "fieldtype": "Date", "insert_after": "custom_insurance_policy"},
		]
	}, ignore_validate=True)
