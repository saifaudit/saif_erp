// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Job Order Aging"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "accountant", label: __("Accountant"), fieldtype: "Link", options: "User" },
		{
			fieldname: "bucket", label: __("Age bucket"), fieldtype: "Select",
			options: ["", "≤ 10 days", "11 – 20 days", "21 – 30 days", "31 – 45 days", "46 – 90 days", "90+ days"],
		},
	],

	// colour by aging severity: Bucket = filled pill, Age = bold coloured number
	formatter(value, row, column, data, default_formatter) {
		const colors = {
			"≤ 10 days": "#22a06b", "11 – 20 days": "#4a9de0", "21 – 30 days": "#7c6ee6",
			"31 – 45 days": "#e6a817", "46 – 90 days": "#e8804d", "90+ days": "#e0533d",
		};
		const c = (data && colors[data.bucket]) || "#888";
		if (data && column.fieldname === "bucket") {
			return `<span style="color:#fff;background:${c};padding:2px 9px;border-radius:11px;font-weight:600;white-space:nowrap">${frappe.utils.escape_html(data.bucket || "")}</span>`;
		}
		if (data && column.fieldname === "age_days") {
			return `<span style="color:${c};font-weight:700">${data.age_days}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
};
