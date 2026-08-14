// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt

frappe.query_reports["SGA Attendance and Leave"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Month"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			// attendance = this date's month; leave balance = this date's year
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			// Managers can pick one; other staff always see only themselves.
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data) {
			if (column.fieldname === "present" && data.present) {
				value = `<span style="color:#0E7A3B;font-weight:600">${value}</span>`;
			}
			if (column.fieldname === "absent" && data.absent) {
				value = `<span style="color:#C0392B;font-weight:700">${value}</span>`;
			}
			// low leave balance (< 1 day) in amber
			if (["annual", "sick", "casual", "earned", "legacy"].includes(column.fieldname) &&
				data[column.fieldname] !== undefined && flt(data[column.fieldname]) <= 0) {
				value = `<span style="color:#C0902F">${value}</span>`;
			}
		}
		return value;
	},
};
