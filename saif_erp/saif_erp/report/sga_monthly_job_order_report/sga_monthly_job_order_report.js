// Copyright (c) 2026, SGA World FZ LLC and contributors
// For license information, please see license.txt

frappe.query_reports["SGA Monthly Job Order Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			// Managers can pick an employee; other staff are always locked to
			// their own jobs regardless of this filter (enforced server-side).
		},
	],
	onload(report) {
		report.page.add_inner_button(__("🖨 Printable PDF"), () => {
			const f = report.get_filter_values();
			frappe.call({
				method: "saif_erp.monthly_report_pdf.preview",
				args: {
					employee: f.employee || "",
					from_date: f.from_date || "",
					to_date: f.to_date || "",
				},
				freeze: true,
				freeze_message: __("Building printable report…"),
				callback(r) {
					if (!r.message) return;
					const w = window.open("", "_blank");
					w.document.write(r.message);
					w.document.close();
					// open the browser's Save-as-PDF dialog straight away
					w.focus();
					setTimeout(() => w.print(), 500);
				},
			});
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "role" && data && data.role === "Contributor") {
			value = `<span style="color:var(--text-muted)">${value}</span>`;
		}
		if (column.fieldname === "carry_forward" && data && data.carry_forward === "Yes") {
			value = `<span style="color:#C0902F;font-weight:600">${value}</span>`;
		}
		return value;
	},
};
