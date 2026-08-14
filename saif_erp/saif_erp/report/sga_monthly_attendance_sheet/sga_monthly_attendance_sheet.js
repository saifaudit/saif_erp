// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt

const _SGA_COLORS = {
	P: "#0E7A3B", // present - green
	W: "#1F6FB2", // work from home - blue
	"½": "#0E7A3B",
	A: "#C0392B", // absent - red
	L: "#C0902F", // leave - amber
	S: "#9AA5A0", // week-off - grey
	H: "#7A6BB0", // holiday - purple
};

frappe.query_reports["SGA Monthly Attendance Sheet"] = {
	filters: [
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				{ value: 1, label: __("January") }, { value: 2, label: __("February") },
				{ value: 3, label: __("March") }, { value: 4, label: __("April") },
				{ value: 5, label: __("May") }, { value: 6, label: __("June") },
				{ value: 7, label: __("July") }, { value: 8, label: __("August") },
				{ value: 9, label: __("September") }, { value: 10, label: __("October") },
				{ value: 11, label: __("November") }, { value: 12, label: __("December") },
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
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
	onload(report) {
		report.page.add_inner_button(__("🖨 Printable PDF"), () => {
			const f = report.get_filter_values();
			frappe.call({
				method: "saif_erp.monthly_report_pdf.attendance_sheet_preview",
				args: { month: f.month || "", year: f.year || "", company: f.company || "", employee: f.employee || "" },
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
		if (column.fieldname && column.fieldname.startsWith("d") && _SGA_COLORS[value]) {
			value = `<span style="color:${_SGA_COLORS[value]};font-weight:700">${value}</span>`;
		}
		return value;
	},
};
