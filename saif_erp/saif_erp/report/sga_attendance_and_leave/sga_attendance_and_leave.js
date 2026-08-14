// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt

frappe.query_reports["SGA Attendance and Leave"] = {
	filters: [
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				{ value: 1, label: __("January") },
				{ value: 2, label: __("February") },
				{ value: 3, label: __("March") },
				{ value: 4, label: __("April") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("June") },
				{ value: 7, label: __("July") },
				{ value: 8, label: __("August") },
				{ value: 9, label: __("September") },
				{ value: 10, label: __("October") },
				{ value: 11, label: __("November") },
				{ value: 12, label: __("December") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Select",
			reqd: 1,
			options: (() => {
				const y = frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear();
				return [y, y - 1, y - 2, y - 3].map(String);
			})(),
			default: String(frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear()),
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
	onload(report) {
		report.page.add_inner_button(__("🖨 Printable PDF"), () => {
			const f = report.get_filter_values();
			frappe.call({
				method: "saif_erp.monthly_report_pdf.attendance_preview",
				args: {
					month: f.month || "",
					year: f.year || "",
					company: f.company || "",
					employee: f.employee || "",
				},
				freeze: true,
				freeze_message: __("Building printable report…"),
				callback(r) {
					if (!r.message) return;
					const w = window.open("", "_blank");
					w.document.write(r.message);
					w.document.close();
					w.focus();
					setTimeout(() => w.print(), 500);
				},
			});
		});
	},
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
