// Copyright (c) 2026, SGA World FZ LLC and contributors
// Desk-load alert for HR/management: expired / expiring / missing employee documents.
// Data comes from boot (saif_erp.boot.boot_session); only sent to eligible roles.
// The bare desk (/app or /desk) loads a workspace shell with a cluttered sidebar while
// keeping the bare URL. Hard-redirect that URL to the SGA Dashboard page so it loads
// fresh with the clean SGA sidebar (same as typing /app/sga-dashboard).
// Keep staff / Admin Support on the clean SGA Dashboard; super admin (System Manager)
// keeps the FULL desk — Settings, all workspaces, global search.
(function () {
	function isSuperAdmin() {
		var roles = (window.frappe && frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		return roles.indexOf("System Manager") !== -1;
	}
	// (a) full page load on the bare URL -> hard redirect to the dashboard page
	try {
		var p = window.location.pathname.replace(/\/+$/, "");
		if ((p === "/app" || p === "/desk") && !isSuperAdmin()) {
			window.location.replace(window.location.origin + "/app/sga-dashboard");
			return;
		}
	} catch (e) { /* noop */ }
	// (b) in-app navigation to the bare home (e.g. the Home button) -> route to the page
	try {
		frappe.router.on("change", function () {
			try {
				if (isSuperAdmin()) return;
				var r = frappe.get_route() || [];
				var s = r.join("/").toLowerCase();
				var bareHome = r.length === 0 || s === "workspaces" || s.indexOf("workspaces/") === 0 || s === "home";
				if (bareHome && s.indexOf("sga-dashboard") === -1) {
					frappe.set_route("sga-dashboard");
				}
			} catch (e) { /* noop */ }
		});
	} catch (e) { /* noop */ }
})();

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
