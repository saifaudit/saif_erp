// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Compliance Filings Due"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "accountant", label: __("Accountant"), fieldtype: "Link", options: "User" },
		{
			fieldname: "service", label: __("Service"), fieldtype: "Select",
			options: ["", "VAT Returns", "Corporate Tax Return"],
		},
		{
			fieldname: "band", label: __("Urgency"), fieldtype: "Select",
			options: ["", "Overdue", "≤ 30 days", "31 – 60 days", "61 – 90 days", "> 90 days"],
		},
	],

	// colour Days Left (bold) + Status (filled pill) by urgency
	formatter(value, row, column, data, default_formatter) {
		const colors = {
			"Overdue": "#8b1a1a", "≤ 30 days": "#e0533d", "31 – 60 days": "#e8804d",
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
