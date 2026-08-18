// Copyright (c) 2026, SGA World FZ LLC and contributors
// Desk-load alert for HR/management: expired / expiring / missing employee documents.
// Data comes from boot (saif_erp.boot.boot_session); only sent to eligible roles.
frappe.after_ajax(() => {
	// compliance filing deadlines (VAT / Corporate Tax)
	const cf = frappe.boot && frappe.boot.compliance_alert;
	if (cf) {
		const cparts = [];
		if (cf.overdue) cparts.push(`<b>${cf.overdue}</b> overdue`);
		if (cf.soon) cparts.push(`<b>${cf.soon}</b> due in 30 days`);
		if (cparts.length) {
			const curl = "/app/query-report/Compliance Filings Due";
			const who = cf.self ? "Your filings" : "Filings";
			frappe.show_alert(
				{ message: `📅 ${who}: ${cparts.join(" · ")} — <a href="${curl}">view</a>`, indicator: cf.overdue ? "red" : "orange" },
				20,
			);
		}
	}

	const a = frappe.boot && frappe.boot.doc_expiry_alert;
	if (!a) return;
	const parts = [];
	if (a.expired) parts.push(`<b>${a.expired}</b> expired`);
	if (a.expiring) parts.push(`<b>${a.expiring}</b> expiring in 30 days`);
	if (a.missing) parts.push(`<b>${a.missing}</b> missing passport details`);
	if (!parts.length) return;
	if (a.self) {
		// employee's own documents — the report is scoped to their own record
		const url = "/app/query-report/Employee Document Expiry";
		frappe.show_alert(
			{ message: `⚠️ Your documents: ${parts.join(" · ")} — <a href="${url}">view</a> & inform HR.`, indicator: "red" },
			20,
		);
	} else {
		const url = "/app/query-report/Employee Document Expiry";
		frappe.show_alert(
			{
				message: `🪪 Employee documents: ${parts.join(" · ")} — <a href="${url}">review</a>`,
				indicator: a.expired || a.missing ? "red" : "orange",
			},
			20,
		);
	}
});
