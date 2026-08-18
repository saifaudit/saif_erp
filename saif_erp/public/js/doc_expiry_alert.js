// Copyright (c) 2026, SGA World FZ LLC and contributors
// Desk-load alert for HR/management: expired / expiring / missing employee documents.
// Data comes from boot (saif_erp.boot.boot_session); only sent to eligible roles.
frappe.after_ajax(() => {
	const a = frappe.boot && frappe.boot.doc_expiry_alert;
	if (!a) return;
	const parts = [];
	if (a.expired) parts.push(`<b>${a.expired}</b> expired`);
	if (a.expiring) parts.push(`<b>${a.expiring}</b> expiring in 30 days`);
	if (a.missing) parts.push(`<b>${a.missing}</b> missing passport details`);
	if (!parts.length) return;
	const url = "/app/query-report/Employee Document Expiry";
	frappe.show_alert(
		{
			message: `🪪 Employee documents: ${parts.join(" · ")} — <a href="${url}">review</a>`,
			indicator: a.expired || a.missing ? "red" : "orange",
		},
		20,
	);
});
