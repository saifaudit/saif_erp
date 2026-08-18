// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Employee Document Expiry"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{
			fieldname: "document", label: __("Document"), fieldtype: "Select",
			options: ["", "Passport", "Residence Visa", "Emirates ID", "Labour Card", "Health Insurance"],
		},
		{
			fieldname: "band", label: __("Status"), fieldtype: "Select",
			options: ["", "Expired", "≤ 30 days", "31 – 60 days", "61 – 90 days", "> 90 days"],
		},
		{ fieldname: "only_expiring", label: __("Only expiring (≤ 90 days)"), fieldtype: "Check", default: 0 },
	],

	// colour Days Left (bold number) + Status (filled pill) by urgency
	formatter(value, row, column, data, default_formatter) {
		const colors = {
			"Expired": "#8b1a1a", "≤ 30 days": "#e0533d", "31 – 60 days": "#e8804d",
			"61 – 90 days": "#e6a817", "> 90 days": "#22a06b",
		};
		const c = (data && colors[data.band]) || "#888";
		if (data && column.fieldname === "band") {
			return `<span style="color:#fff;background:${c};padding:2px 9px;border-radius:11px;font-weight:600;white-space:nowrap">${frappe.utils.escape_html(data.band || "")}</span>`;
		}
		if (data && column.fieldname === "days_left") {
			return `<span style="color:${c};font-weight:700">${data.days_left}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
};
