// Copyright (c) 2026, SGA World FZ LLC and contributors
// SGA Job Orders — custom management dashboard page.

frappe.pages["sga-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "SGA Dashboard",
		single_column: true,
	});
	inject_styles();
	const $root = $('<div class="sga-dash"></div>').appendTo(page.body);
	$root.html('<div class="sga-loading">Loading dashboard…</div>');

	let period = "year", company = "";
	function setPeriod(p) { period = p; load(); }
	function setCompany(c) { company = c || ""; load(); }
	function load() {
		frappe.call({ method: "saif_erp.api.dashboard_data", args: { period, company: company || undefined } }).then((r) => {
			if (r && r.message) render($root, r.message, { setPeriod, setCompany });
		});
	}
	page.set_secondary_action("Refresh", () => load(), "refresh");
	load();
};

// ---------- helpers ----------
const _int = (n) => (n == null ? "0" : Number(n).toLocaleString("en-US"));
const _m = (n) => "AED " + (Number(n || 0) / 1e6).toFixed(2) + "M";
const _esc = (s) => frappe.utils.escape_html(String(s == null ? "" : s));
const _rel = (dt) => { if (!dt) return ""; try { return $(frappe.datetime.comment_when(dt)).text() || ""; } catch (e) { return frappe.datetime.str_to_user ? frappe.datetime.str_to_user(dt) : String(dt); } };
const _money = (n) => { n = Number(n || 0); return n >= 1e6 ? "AED " + (n / 1e6).toFixed(2) + "M" : "AED " + Math.round(n / 1000) + "K"; };
const _pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
// current filter scope for drill-down links (set per render)
let _company = "", _myuser = "";
function joHref(params) {
	const q = Object.entries(params || {}).filter(([, v]) => v != null && v !== "").map(([k, v]) => k + "=" + encodeURIComponent(v));
	if (_company) q.push("company=" + encodeURIComponent(_company));
	if (_myuser) q.push("accountant=" + encodeURIComponent(_myuser));
	return "/app/job-order/view/list?" + q.join("&");
}
const listHref = (dt, params) => "/app/" + dt + "/view/list" + (params && Object.keys(params).length ? "?" + Object.entries(params).map(([k, v]) => k + "=" + encodeURIComponent(v)).join("&") : "");
const fmtDT = (t) => { if (!t) return ""; try { return moment(t).format("ddd D MMM · h:mm A"); } catch (e) { return _rel(t); } };
const fmtDate = (t) => { if (!t) return ""; try { return moment(t).format("D MMM"); } catch (e) { return String(t); } };

const STATUS_META = {
	Open: { c: "var(--sga-brand-soft)", l: "Open" },
	Progress: { c: "var(--sga-brand)", l: "In Progress" },
	"Under Review": { c: "var(--sga-amber)", l: "Under Review" },
	"Awaiting Client Data": { c: "var(--sga-slate2)", l: "Awaiting Client Data" },
	"Temporarily stopped": { c: "var(--sga-orange)", l: "On Hold" },
	Pending: { c: "var(--sga-slate)", l: "Pending" },
	Finished: { c: "var(--sga-accent)", l: "Finished" },
	"Closed (Failed)": { c: "var(--sga-bad)", l: "Closed (Failed)" },
};
const GROUP_NAME = "SGA World · SAIF Chartered Accountants";
function avatar(g) {
	if (g.image) return `<div class="sga-av"><img src="${_esc(g.image)}" alt=""></div>`;
	const nm = (g.employee_name || g.full_name || "?").trim();
	const ini = nm.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
	return `<div class="sga-av init">${_esc(ini)}</div>`;
}
const PAY_META = [
	["Paid", "var(--sga-good)"],
	["Not Paid", "var(--sga-orange)"],
	["Partial Payment", "var(--sga-amber)"],
	["Hold / Dispute", "var(--sga-bad)"],
	["Not Created", "var(--sga-slate)"],
	["Another Choice", "var(--sga-slate2)"],
];

function render($root, d, actions) {
	actions = actions || {};
	const setPeriod = actions.setPeriod;
	if (!d.manager) return render_limited($root, d);
	const g = d.greeting || {};
	const money = d.money || {};
	const parts = [];
	const period = money.period || "year";
	_company = d.company || ""; _myuser = "";

	// header
	parts.push(`
	<div class="sga-head">
	  <div class="sga-brand">
	    <div class="sga-logo"><img src="${_esc(g.logo || "/files/logoonly200x200.png")}" alt="SGA"></div>
	    <div>
	      <div class="sga-bname">${_esc(GROUP_NAME)}</div>
	      <div class="sga-bsub">Job Order Operations · Group View</div>
	    </div>
	  </div>
	  <div class="sga-greet">
	    <div class="gtext">
	      <div class="g1">${_esc(g.employee_name || g.full_name || "")}</div>
	      <div class="g2">${_esc([g.designation, g.company].filter(Boolean).join(" · "))}</div>
	    </div>
	    ${avatar(g)}
	  </div>
	</div>
	<div class="sga-ctx">
	  ${ctx(d.counts.job_orders, "Job Orders", joHref({}))}
	  ${ctx(d.counts.customers, "Customers", listHref("customer", {}))}
	  ${ctx(d.counts.employees, "Active Staff", listHref("employee", { status: "Active" }))}
	  ${ctx(d.counts.proposals, "Proposals", listHref("quotation", {}))}
	  ${ctx(d.counts.credentials, "Credentials", listHref("credential-manager", {}))}
	</div>`);

	// company filter (group has multiple entities)
	if ((d.companies || []).length > 1) {
		const opts = ['<option value="">All companies</option>'].concat(
			(d.companies || []).map((c) => `<option value="${_esc(c.label)}" ${d.company === c.label ? "selected" : ""}>${_esc(c.label)} · ${_int(c.n)}</option>`)
		).join("");
		parts.push(`<div class="sga-controls"><span class="lbl">Company</span><select class="sga-company">${opts}</select>
		  ${d.company ? `<span class="sga-scope">Showing ${_esc(d.company)} only</span>` : `<span class="sga-scope muted">All group entities</span>`}</div>`);
	}

	// KPI money — with This Year / All Time toggle
	const toggle = `<div class="sga-period">
	  <button data-p="year" class="${period === "year" ? "on" : ""}">This Year</button>
	  <button data-p="all" class="${period === "all" ? "on" : ""}">All Time</button></div>`;
	parts.push(`<div class="sga-sec"><div class="sga-eye"><h2>Financial snapshot · ${_esc(money.period_label || "This year")}</h2><span class="rule"></span>${toggle}</div>
	<div class="sga-grid k4">
	  ${kpi("Invoiced", _m(money.invoiced), `${money.period_label} · submitted job orders`, "var(--sga-brand)", null, joHref({}))}
	  ${kpi("Collected", _m(money.collected), `<span class="sga-chip good">${money.collection_rate}% collection rate</span>`, "var(--sga-good)", money.collection_rate, joHref({ payment_status: "Paid" }))}
	  ${kpi("Outstanding", _m(money.outstanding), `<span class="sga-chip warn">Invoiced minus collected</span>`, "var(--sga-orange)", null, joHref({ payment_status: "Not Paid" }))}
	  ${kpi("Open pipeline", _int(d.active_jobs), `<b>${_int(d.job_status.Finished || 0)}</b> finished all‑time`, "var(--sga-accent)", null, joHref({ job_status: "Progress" }))}
	</div></div>`);

	// Receivables aging
	parts.push(aging_section(d));

	// status tiles
	const order = ["Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending", "Finished", "Closed (Failed)"];
	const tiles = order.filter((s) => d.job_status[s] != null).map((s) => {
		const meta = STATUS_META[s] || { c: "var(--sga-slate)", l: s };
		return `<a class="sga-stat" href="${joHref({ job_status: s })}">
		  <span class="dot" style="background:${meta.c}"></span>
		  <div class="v">${_int(d.job_status[s])}</div><div class="n">${_esc(meta.l)}</div></a>`;
	}).join("");
	parts.push(section("Job status · live", `<div class="sga-stats">${tiles}</div>`));

	// payment donut + services
	parts.push(section("Payments & services", `
	<div class="sga-grid k2">
	  <div class="sga-card">${donut(d.payment_status)}</div>
	  <div class="sga-card">${svc_bars(d.by_service)}</div>
	</div>`, true));

	// compliance & efficiency
	parts.push(compliance_section(d));

	// quick lists (recent job orders) + shortcuts/reports
	parts.push(section("Recent job orders", `
	<div class="sga-grid k3">
	  ${qlist("Open", d.recent.open)}
	  ${qlist("In Progress", d.recent.progress)}
	  ${qlist("Finished", d.recent.finished)}
	</div>`));

	parts.push(section("Quick actions & reports", `
	<div class="sga-grid k2">
	  <div class="sga-card">
	    <div class="sga-links">
	      ${shortcut("Full Job Orders List", `${d.counts.job_orders} total`, "/app/job-order", "list")}
	      ${shortcut("Create Job Order", "New", "/app/job-order/new", "add")}
	      ${shortcut("Credential Manager", `${d.counts.credentials} total`, "/app/credential-manager", "lock")}
	      ${shortcut("Payment Status Report", "", "/app/query-report/Payment Status Report", "small-file")}
	    </div>
	  </div>
	  <div class="sga-card">
	    <div class="sga-rep-title">Reports — Job Order</div>
	    <div class="sga-replist">
	      ${report("Monthly Job Order Report – Staff")}
	      ${report("Employee Work Flow Report")}
	      ${report("My Contributor Job Orders")}
	      ${report("SGA Employee Leave Balance")}
	    </div>
	  </div>
	</div>`));

	// trends: revenue (invoiced vs collected) + throughput (created vs finished)
	parts.push(section("Revenue · invoiced vs collected", `<div class="sga-card">${trend2(d.rev_trend, [
		{ key: "inv", label: "Invoiced", color: "var(--sga-brand)" },
		{ key: "paid", label: "Collected", color: "var(--sga-accent)" }])}</div>`, true));
	parts.push(section("Throughput · created vs finished", `<div class="sga-card">${trend2(d.throughput, [
		{ key: "created", label: "Created", color: "var(--sga-slate2)" },
		{ key: "finished", label: "Finished", color: "var(--sga-good)" }])}</div>`, true));

	// proposals funnel (full width)
	const p = d.proposals || {};
	const conv = p.total ? Math.round((p.converted / p.total) * 100) : 0;
	parts.push(section("Proposals → Job Order funnel", `
	<div class="sga-card"><div class="sga-funnel">
	  ${fstep(p.total, "Total proposals")}
	  ${fstep(p.converted, `<span class="arw">→</span> Converted · <b>${conv}%</b>`)}
	  ${fstep(p.awaiting_acceptance, "Awaiting client acceptance")}
	  ${fstep(p.awaiting_jo, "Accepted · awaiting JO")}
	</div></div>`));

	// team workload + top customers
	parts.push(section("Team & key clients", `
	<div class="sga-grid k2">
	  <div class="sga-card">${hbars(d.by_accountant, "var(--sga-brand)", "Current workload · active jobs, active staff", (r) => joHref({ accountant: r.user }))}
	    ${d.orphan_active ? `<div class="sga-warn">⚠ ${_int(d.orphan_active)} active job orders still assigned to former staff — needs reassignment.</div>` : ""}</div>
	  <div class="sga-card">${hbars((d.top_customers || []).map((c) => ({ label: c.label, value: c.value, cust: c.cust })), "var(--sga-brand)", "Top customers · by job count", (r) => joHref({ customer: r.cust }))}</div>
	</div>`));

	// HR / all-employee overview (only for HR-privileged admins)
	if (d.hr) {
		parts.push(section("Team & HR · all employees", hrSection(d.hr)));
	}

	// non-HR managers: show their own attendance (HR admins get the team table above)
	const mp = d.me_personal || {};
	if (!d.hr && mp.my_attendance && mp.my_attendance.holiday_list) {
		parts.push(section(`My attendance · ${_esc(mp.my_attendance.month || "this month")}`, attCard(mp.my_attendance, mp.my_checkins)));
	}

	parts.push(`<div class="sga-foot">SGA Job Orders dashboard · figures live from this site · financials = ${_esc(money.period_label || "This year")}</div>`);
	$root.html(parts.join(""));
	$root.find(".sga-period button").on("click", function () {
		if (typeof setPeriod === "function") setPeriod($(this).data("p"));
	});
	$root.find(".sga-company").on("change", function () {
		if (typeof actions.setCompany === "function") actions.setCompany($(this).val());
	});
}

function render_limited($root, d) {
	const g = d.greeting || {};
	const mc = d.my_counts || {}, ms = d.my_status || {};
	const parts = [];
	_company = ""; _myuser = g.user || "";

	parts.push(`
	<div class="sga-head"><div class="sga-brand"><div class="sga-logo"><img src="${_esc(g.logo || "/files/logoonly200x200.png")}" alt="SGA"></div>
	  <div><div class="sga-bname">${_esc(GROUP_NAME)}</div><div class="sga-bsub">My Work</div></div></div>
	  <div class="sga-greet"><div class="gtext"><div class="g1">${_esc(g.employee_name || g.full_name || "")}</div>
	  <div class="g2">${_esc([g.designation, g.company].filter(Boolean).join(" · "))}</div></div>${avatar(g)}</div></div>`);

	parts.push(section("My work at a glance", `<div class="sga-grid k4">
	  ${kpi("My active jobs", _int(mc.active), "In progress right now", "var(--sga-brand)", null, joHref({ job_status: "Progress" }))}
	  ${kpi("Open", _int(mc.open), "Not yet started", "var(--sga-brand-soft)", null, joHref({ job_status: "Open" }))}
	  ${kpi("Finished", _int(mc.finished), "Completed by me", "var(--sga-accent)", null, joHref({ job_status: "Finished" }))}
	  ${kpi("Needs attention", _int(mc.attention), `<span class="sga-chip warn">Awaiting data / on hold</span>`, "var(--sga-amber)", null, joHref({ job_status: "Awaiting Client Data" }))}
	</div>`));

	// jobs needing my attention (to-do)
	const action = (d.my_action || []).map((r) =>
		`<a class="sga-qrow" href="/app/job-order/${encodeURIComponent(r.name)}"><span>${_esc(r.name)} · <b>${_esc(r.job_status || "")}</b></span><span class="t">${_esc(_rel(r.modified))}</span></a>`).join("");
	if (action) {
		parts.push(section("Needs my attention", `<div class="sga-card"><div class="sga-qtitle">Awaiting client data · on hold · under review</div><div class="sga-qlist">${action}</div></div>`));
	}

	const order = ["Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending", "Finished", "Closed (Failed)"];
	const tiles = order.filter((s) => ms[s] != null).map((s) => {
		const m = STATUS_META[s] || { c: "var(--sga-slate)", l: s };
		return `<a class="sga-stat" href="${joHref({ job_status: s })}"><span class="dot" style="background:${m.c}"></span><div class="v">${_int(ms[s])}</div><div class="n">${_esc(m.l)}</div></a>`;
	}).join("") || '<div class="sga-empty">No job orders assigned to you yet.</div>';
	parts.push(section("My job status", `<div class="sga-stats">${tiles}</div>`));

	// my throughput trend
	if ((d.my_trend || []).length) {
		parts.push(section("My throughput · created vs finished", `<div class="sga-card">${trend2(d.my_trend, [
			{ key: "created", label: "Created", color: "var(--sga-slate2)" },
			{ key: "finished", label: "Finished", color: "var(--sga-good)" }])}</div>`, true));
	}

	// my work mix + my payment status
	const paytiles = PAY_META.filter(([k]) => (d.my_payment || {})[k]).map(([k, c]) =>
		`<a class="sga-stat" href="${joHref({ payment_status: k })}"><span class="dot" style="background:${c}"></span><div class="v">${_int(d.my_payment[k])}</div><div class="n">${_esc(k)}</div></a>`).join("") || '<div class="sga-empty">None</div>';
	parts.push(section("My work mix", `<div class="sga-grid k2">
	  <div class="sga-card">${hbars(d.my_by_service, "var(--sga-brand)", "My jobs by service")}</div>
	  <div class="sga-card"><div class="sga-qtitle">My jobs by payment status</div><div class="sga-stats sga-stats-sm">${paytiles}</div></div>
	</div>`));

	// recent jobs + leave
	const rows = (d.recent_mine || []).map((r) =>
		`<a class="sga-qrow" href="/app/job-order/${encodeURIComponent(r.name)}"><span>${_esc(r.name)} · ${_esc(r.job_status || "")}</span><span class="t">${_esc(_rel(r.modified))}</span></a>`).join("") || '<div class="sga-empty">None</div>';
	parts.push(section("My recent jobs & leave", `<div class="sga-grid k2">
	  <div class="sga-card"><div class="sga-qtitle">Recent job orders</div><div class="sga-qlist">${rows}</div></div>
	  <div class="sga-card">${myleave(d.my_leave)}</div>
	</div>`));

	// my attendance this month (Sundays + public holidays excluded) + recent check-ins
	const att = d.my_attendance || {};
	parts.push(section(`My attendance · ${_esc(att.month || "this month")}`, attCard(att, d.my_checkins)));

	// quick actions
	parts.push(section("Quick actions", `<div class="sga-card"><div class="sga-links">
	  ${shortcut("Create Job Order", "New", "/app/job-order/new", "add")}
	  ${shortcut("My Job Orders", "", "/app/job-order?accountant=" + encodeURIComponent(g.user || ""), "list")}
	  ${shortcut("Apply for Leave", "", "/app/leave-application/new", "calendar")}
	  ${shortcut("My Leave Balance", "", "/app/query-report/SGA Employee Leave Balance", "small-file")}
	</div></div>`));

	parts.push(`<div class="sga-foot">Your personal view · figures cover only your own job orders</div>`);
	$root.html(parts.join(""));
}

function myleave(rows) {
	rows = rows || [];
	if (!rows.length) return `<div class="sga-qtitle">My leave balance</div><div class="sga-empty">No leave allocation found.</div>`;
	const body = rows.map((r) => {
		const bal = Number(r.balance || 0), alloc = Number(r.allocated || 0);
		const pct = alloc > 0 ? Math.max(0, Math.min(100, (bal / alloc) * 100)) : 0;
		return `<div class="hbar"><div class="top"><span class="lab">${_esc(r.leave_type)}</span>
		  <span class="val">${bal.toFixed(1)} <span style="color:var(--sga-muted);font-weight:500">/ ${alloc.toFixed(0)} left</span></span></div>
		  <div class="track"><i style="width:${pct}%;background:var(--sga-good)"></i></div></div>`;
	}).join("");
	return `<div class="sga-qtitle">My leave balance</div><div class="sga-hbars">${body}</div>`;
}

// ---------- fragment builders ----------
const ctx = (n, l, href) => {
	const inner = `<span class="n">${_int(n)}</span><span class="l">${_esc(l)}</span>`;
	return href ? `<a class="c lnk" href="${href}">${inner}</a>` : `<div class="c">${inner}</div>`;
};
function section(title, body, tight) {
	return `<div class="sga-sec"><div class="sga-eye"><h2>${_esc(title)}</h2><span class="rule"></span></div>${body}</div>`;
}
function kpi(cap, big, sub, color, rate, href) {
	const bar = rate != null ? `<div class="sga-mini"><i style="width:${rate}%;background:${color}"></i></div>` : "";
	const inner = `<span class="stripe" style="background:${color}"></span>
	  <div class="cap">${_esc(cap)}</div><div class="big">${big}</div><div class="sub">${sub}</div>${bar}`;
	return href ? `<a class="sga-card kpi lnk" href="${href}">${inner}</a>` : `<div class="sga-card kpi">${inner}</div>`;
}
function donut(pay) {
	const total = Object.values(pay || {}).reduce((a, b) => a + b, 0) || 1;
	let acc = 0, stops = [], legend = [];
	PAY_META.forEach(([k, c]) => {
		const v = pay[k] || 0;
		if (!v && k !== "Paid") return;
		const from = (acc / total) * 100, to = ((acc + v) / total) * 100;
		acc += v;
		stops.push(`${c} ${from}% ${to}%`);
		legend.push(`<a class="li lnk" href="${joHref({ payment_status: k })}"><span class="sw" style="background:${c}"></span><span class="lab">${_esc(k)}</span><span class="val">${_int(v)}</span><span class="pct">${((v / total) * 100).toFixed(1)}%</span></a>`);
	});
	const paidPct = Math.round(((pay.Paid || 0) / total) * 100);
	return `<div class="sga-eye tight"><h2>Payment breakdown</h2><span class="rule"></span></div>
	<div class="sga-donwrap"><div class="sga-donut" style="background:conic-gradient(${stops.join(",")})">
	  <div class="mid"><b>${paidPct}%</b><span>Paid</span></div></div>
	  <div class="sga-legend">${legend.join("")}</div></div>`;
}
function hbars(rows, color, title, linkFn) {
	rows = rows || [];
	const max = Math.max(1, ...rows.map((r) => r.value));
	const bars = rows.map((r) => {
		const inner = `<div class="top"><span class="lab">${_esc(r.label)}</span><span class="val">${_int(r.value)}</span></div>
		 <div class="track"><i style="width:${Math.max(3, (r.value / max) * 100)}%"></i></div>`;
		const href = linkFn && linkFn(r);
		return href ? `<a class="hbar lnk" href="${href}">${inner}</a>` : `<div class="hbar">${inner}</div>`;
	}).join("") || '<div class="sga-empty">No data</div>';
	return `<div class="sga-eye tight"><h2>${_esc(title || "")}</h2><span class="rule"></span></div><div class="sga-hbars">${bars}</div>`;
}
function qlist(title, rows) {
	rows = rows || [];
	const body = rows.map((r) =>
		`<a class="sga-qrow" href="/app/job-order/${encodeURIComponent(r.name)}">
		 <span>${_esc(r.name)}</span><span class="t">${_esc(_rel(r.modified))}</span></a>`).join("") || '<div class="sga-empty">None</div>';
	return `<div class="sga-card"><div class="sga-qtitle">${_esc(title)}</div><div class="sga-qlist">${body}</div></div>`;
}
function shortcut(label, meta, href, icon) {
	return `<a class="sga-shortcut" href="${href}">
	  <span class="ic">${frappe.utils.icon(icon, "sm")}</span>
	  <span class="lb">${_esc(label)}</span>${meta ? `<span class="mt">${_esc(meta)}</span>` : ""}</a>`;
}
function report(name) {
	return `<a class="sga-rep" href="/app/query-report/${encodeURIComponent(name)}">${_esc(name)}</a>`;
}
function fstep(v, n) {
	return `<div class="fstep"><div class="v">${_int(v)}</div><div class="n">${n}</div></div>`;
}
function trend(rows) {
	rows = rows || [];
	const W = 720, H = 150, n = rows.length || 1;
	const max = Math.max(1, ...rows.map((r) => r.value));
	const step = n > 1 ? W / (n - 1) : W;
	const pts = rows.map((r, i) => [i * step, H - (r.value / max) * (H - 24) - 6]);
	const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(0) + "," + p[1].toFixed(0)).join(" ");
	const area = `${line} L${W},${H} L0,${H} Z`;
	const labels = rows.map((r) => `<span>${_esc(r.label.slice(5))}</span>`).join("");
	const last = pts[pts.length - 1] || [0, 0];
	return `<div class="sga-eye tight"><h2>New job orders · 12 months</h2><span class="rule"></span></div>
	<div class="sga-trend"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
	  <line class="gl" x1="0" y1="35" x2="${W}" y2="35"/><line class="gl" x1="0" y1="80" x2="${W}" y2="80"/><line class="gl" x1="0" y1="125" x2="${W}" y2="125"/>
	  <defs><linearGradient id="sgaFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--sga-brand)" stop-opacity=".26"/><stop offset="1" stop-color="var(--sga-brand)" stop-opacity="0"/></linearGradient></defs>
	  <path fill="url(#sgaFill)" d="${area}"/><path fill="none" stroke="var(--sga-brand)" stroke-width="2.5" stroke-linejoin="round" d="${line}"/>
	  <circle cx="${last[0].toFixed(0)}" cy="${last[1].toFixed(0)}" r="4.5" fill="var(--sga-accent)"/></svg>
	  <div class="xlab">${labels}</div></div>`;
}

function aging_section(d) {
	const rows = d.aging || [];
	if (!rows.length) return "";
	const max = Math.max(1, ...rows.map((r) => r.amt || 0));
	const col = { "0-30": "var(--sga-good)", "31-60": "var(--sga-amber)", "61-90": "var(--sga-orange)", "90+": "var(--sga-bad)" };
	const over = rows.find((r) => r.bucket === "90+") || {};
	const totalN = rows.reduce((a, r) => a + (r.n || 0), 0);
	const bars = rows.map((r) =>
		`<div class="hbar"><div class="top"><span class="lab">${_esc(r.bucket)} days · ${_int(r.n)} invoices</span><span class="val">${_money(r.amt)}</span></div>
		 <div class="track"><i style="width:${Math.max(4, ((r.amt || 0) / max) * 100)}%;background:${col[r.bucket] || "var(--sga-brand)"}"></i></div></div>`).join("");
	const debtors = d.top_debtors || [];
	const dmax = Math.max(1, ...debtors.map((x) => x.value || 0));
	const dbars = debtors.map((x) =>
		`<div class="hbar"><div class="top"><span class="lab">${_esc((x.label || "—").slice(0, 30))}</span><span class="val">${_money(x.value)}</span></div>
		 <div class="track"><i style="width:${Math.max(5, ((x.value || 0) / dmax) * 100)}%;background:var(--sga-bad)"></i></div></div>`).join("") || '<div class="sga-empty">None</div>';
	return `<div class="sga-sec"><div class="sga-eye"><h2>Receivables aging & debtors</h2><span class="rule"></span></div>
	<div class="sga-mini2">
	  ${kpi("Total outstanding", _money(d.aging_total || 0), `${_int(totalN)} unpaid invoices`, "var(--sga-orange)", null, joHref({ payment_status: "Not Paid" }))}
	  ${kpi("90+ days overdue", _money(over.amt || 0), `<span class="sga-chip bad">${_int(over.n || 0)} invoices · action needed</span>`, "var(--sga-bad)", null, joHref({ payment_status: "Not Paid" }))}
	</div>
	<div class="sga-grid k2" style="margin-top:14px">
	  <div class="sga-card"><div class="sga-qtitle">By invoice age</div><div class="sga-hbars">${bars}</div></div>
	  <div class="sga-card"><div class="sga-qtitle">Top debtors · who owes most</div><div class="sga-hbars">${dbars}</div></div>
	</div></div>`;
}

function svc_bars(rows) {
	rows = rows || [];
	const max = Math.max(1, ...rows.map((r) => r.revenue || 0));
	const bars = rows.map((r) =>
		`<div class="hbar"><div class="top"><span class="lab">${_esc((r.label || "").slice(0, 32))} <span style="color:var(--sga-muted)">· ${_int(r.value)} jobs</span></span><span class="val">${_money(r.revenue)}</span></div>
		 <div class="track"><i style="width:${Math.max(3, ((r.revenue || 0) / max) * 100)}%"></i></div></div>`).join("");
	return `<div class="sga-eye tight"><h2>Revenue by service · all time</h2><span class="rule"></span></div><div class="sga-hbars">${bars}</div>`;
}

function trend2(rows, series) {
	rows = rows || [];
	const W = 720, H = 150;
	const max = Math.max(1, ...rows.flatMap((r) => series.map((s) => Number(r[s.key] || 0))));
	const n = rows.length || 1, step = n > 1 ? W / (n - 1) : W;
	const lines = series.map((s) => {
		const pts = rows.map((r, i) => [i * step, H - (Number(r[s.key] || 0) / max) * (H - 24) - 6]);
		const path = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(0) + "," + p[1].toFixed(0)).join(" ");
		const last = pts[pts.length - 1] || [0, 0];
		return `<path fill="none" stroke="${s.color}" stroke-width="2.5" stroke-linejoin="round" d="${path}"/><circle cx="${last[0].toFixed(0)}" cy="${last[1].toFixed(0)}" r="4" fill="${s.color}"/>`;
	}).join("");
	const legend = series.map((s) => `<span class="lg"><i style="background:${s.color}"></i>${_esc(s.label)}</span>`).join("");
	const labels = rows.map((r) => `<span>${_esc(String(r.label).slice(5))}</span>`).join("");
	return `<div class="sga-legend2">${legend}</div><div class="sga-trend"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
	  <line class="gl" x1="0" y1="35" x2="${W}" y2="35"/><line class="gl" x1="0" y1="80" x2="${W}" y2="80"/><line class="gl" x1="0" y1="125" x2="${W}" y2="125"/>
	  ${lines}</svg><div class="xlab">${labels}</div></div>`;
}

function compliance_section(d) {
	const c = d.compliance || {}, t = d.turnaround || {};
	const kyc = _pct(c.kyc, c.total), loe = _pct(c.loe, c.total);
	const wpColor = c.wp_pending > 0 ? "var(--sga-bad)" : "var(--sga-good)";
	return `<div class="sga-sec"><div class="sga-eye"><h2>Compliance & efficiency</h2><span class="rule"></span></div>
	<div class="sga-grid k4">
	  ${kpi("Avg turnaround", (t.avg_days || 0) + " days", `${_int(t.n || 0)} finished jobs measured`, "var(--sga-brand)")}
	  ${kpi("KYC received", kyc + "%", `${_int(c.kyc || 0)} of ${_int(c.total || 0)} jobs`, "var(--sga-good)", kyc)}
	  ${kpi("LOE received", loe + "%", `${_int(c.loe || 0)} of ${_int(c.total || 0)} jobs`, "var(--sga-good)", loe)}
	  ${kpi("Working papers", _int(c.wp_pending || 0) + " pending", `of ${_int(c.wp_applicable || 0)} due since May 2026`, wpColor)}
	</div></div>`;
}

function attCard(att, checkins) {
	att = att || {};
	const attDefs = [
		["Present", "var(--sga-good)", att.Present, true], ["Absent", "var(--sga-bad)", att.Absent, true],
		["On Leave", "var(--sga-slate2)", att["On Leave"], false], ["Half Day", "var(--sga-amber)", att["Half Day"], false],
		["WFH", "var(--sga-brand-soft)", att["Work From Home"], false], ["Holidays", "var(--sga-slate)", att.holidays, true]];
	const tiles = attDefs.filter(([, , v, a]) => a || v).map(([k, c, v]) =>
		`<div class="sga-stat"><span class="dot" style="background:${c}"></span><div class="v">${_int(v || 0)}</div><div class="n">${_esc(k)}</div></div>`).join("") || '<div class="sga-empty">No attendance this month</div>';
	const note = `<div class="sga-attnote">${_int(att.working_days)} working days so far · <b>Sundays &amp; public holidays excluded</b>${att.holiday_list ? " (" + _esc(att.holiday_list) + ")" : ""}</div>`;
	const ci = (checkins || []).map((c) => {
		const io = (c.log_type || "").toUpperCase(), cls = io === "IN" ? "in" : "out";
		return `<div class="sga-ci"><span class="io ${cls}">${_esc(io || "—")}</span><span class="tm">${_esc(fmtDT(c.time))}</span></div>`;
	}).join("") || '<div class="sga-empty">No check-ins</div>';
	return `<div class="sga-grid k2">
	  <div class="sga-card"><div class="sga-qtitle">Days this month</div><div class="sga-stats sga-stats-sm">${tiles}</div>${note}</div>
	  <div class="sga-card"><div class="sga-qtitle">Recent check-ins</div><div class="sga-cilist">${ci}</div></div>
	</div>`;
}

function hrSection(hr) {
	const shortco = (c) => _esc((c || "").replace("Saif Chartered Accountants LLC- Dubai", "Saif — Dubai")
		.replace("SGA World Auditing Accounting LLC - Abu Dhabi", "SGA — Abu Dhabi")
		.replace("SGA World Auditing Accounting LLC SPC-Dubai", "SGA — SPC Dubai")
		.replace("T K Chandy & Associates", "T K Chandy (India)"));
	const nz = (v) => (!v ? '<span class="z">0</span>' : String(v));
	const hc = (hr.headcount || []).map((h) => `<span class="hc">${shortco(h.company)} · <b>${_int(h.n)}</b></span>`).join("");
	const ol = (hr.on_leave || []).map((x) =>
		`<div class="sga-qrow"><span>${_esc(x.label)} · ${_esc(x.leave_type)}</span><span class="t">till ${_esc(fmtDate(x.to_date))}</span></div>`).join("") || '<div class="sga-empty">Nobody on leave today ✓</div>';

	const nameL = (e) => `<a class="tlnk" href="${listHref("leave-allocation", { employee: e.emp })}">${_esc(e.employee_name)}</a>`;
	const attCell = (e, status, v) => `<td class="num"><a class="tlnk" href="${listHref("attendance", { employee: e.emp, status })}">${nz(v)}</a></td>`;

	// leave balances table
	const lrows = (hr.team_leave || []).map((e) => {
		const total = (e.annual || 0) + (e.sick || 0) + (e.casual || 0) + (e.legacy || 0);
		return `<tr><td>${nameL(e)}</td><td class="mut">${shortco(e.company)}</td>
		  <td class="num">${nz(e.annual)}</td><td class="num">${nz(e.sick)}</td><td class="num">${nz(e.casual)}</td><td class="num">${nz(e.legacy)}</td><td class="num tot">${total}</td></tr>`;
	}).join("");
	const ltable = `<table class="sga-tbl"><thead><tr><th>Employee</th><th>Company</th><th class="num">Annual / Earned</th><th class="num">Sick</th><th class="num">Casual</th><th class="num">Legacy</th><th class="num">Total left</th></tr></thead><tbody>${lrows}</tbody></table>`;

	// attendance table (numbers link to the filtered Attendance list)
	const arows = (hr.team_attendance || []).map((e) =>
		`<tr><td><a class="tlnk" href="${listHref("attendance", { employee: e.emp })}">${_esc(e.employee_name)}</a></td><td class="mut">${shortco(e.company)}</td>
		  ${attCell(e, "Present", e.present)}${attCell(e, "Absent", e.absent)}${attCell(e, "On Leave", e.on_leave)}<td class="num">${nz(e.holidays)}</td><td class="num tot">${e.working_days}</td></tr>`).join("");
	const atable = `<table class="sga-tbl"><thead><tr><th>Employee</th><th>Company</th><th class="num">Present</th><th class="num">Absent</th><th class="num">On&nbsp;Leave</th><th class="num">Holidays</th><th class="num">Working&nbsp;days</th></tr></thead><tbody>${arows}</tbody></table>`;

	return `<div class="sga-hc"><span class="hc total"><b>${_int(hr.active)}</b> active staff</span>${hc}</div>
	<div class="sga-grid k2" style="margin-top:14px">
	  <div class="sga-card"><div class="sga-qtitle">On leave today</div><div class="sga-qlist">${ol}</div></div>
	  <div class="sga-card"><div class="sga-qtitle">Quick HR links</div><div class="sga-links">
	    ${shortcut("All Employees", `${_int(hr.active)}`, "/app/employee", "users")}
	    ${shortcut("Leave Balance Report", "", "/app/query-report/SGA Employee Leave Balance", "small-file")}
	    ${shortcut("Attendance", "", "/app/attendance", "calendar")}
	    ${shortcut("Leave Applications", "", "/app/leave-application", "small-file")}
	  </div></div>
	</div>
	<div class="sga-card" style="margin-top:14px"><div class="sga-qtitle">Team leave balances · days remaining in 2026</div><div class="sga-tblwrap">${ltable}</div>
	  <div class="sga-attnote">Casual applies to India (T K Chandy) staff · <b>Legacy</b> = leave carried over from before this system.</div></div>
	<div class="sga-card" style="margin-top:14px"><div class="sga-qtitle">Team attendance · ${_esc(hr.month || "this month")}</div><div class="sga-tblwrap">${atable}</div>
	  <div class="sga-attnote">Sundays &amp; public holidays excluded (each staff on their own UAE / India calendar).</div></div>`;
}

// ---------- styles ----------
function inject_styles() {
	if (document.getElementById("sga-dash-style")) return;
	const css = `
.sga-dash{--sga-brand:#155636;--sga-brand-deep:#0E3A22;--sga-brand-soft:#2E8B43;--sga-accent:#3DB54A;
 --sga-good:#2E8B43;--sga-amber:#C0902F;--sga-orange:#CC6B3C;--sga-bad:#B0413A;--sga-slate:#7C8B94;--sga-slate2:#54707C;
 --sga-surface:#fff;--sga-surface2:#F2F7F3;--sga-line:#E1E9E2;--sga-ink:#17251C;--sga-ink2:#45524A;--sga-muted:#74837A;
 font-variant-numeric:tabular-nums;color:var(--sga-ink);padding-bottom:30px}
[data-theme="dark"] .sga-dash{--sga-brand:#43B64A;--sga-brand-deep:#0C2C1A;--sga-brand-soft:#2E8B43;--sga-accent:#5CCB63;
 --sga-good:#4FB56A;--sga-amber:#DCB14E;--sga-orange:#E08B57;--sga-bad:#E0685F;--sga-slate:#8FA1AB;--sga-slate2:#A9C0CB;
 --sga-surface:#18211B;--sga-surface2:#121A14;--sga-line:#26332A;--sga-ink:#EAF1EC;--sga-ink2:#BCCAC0;--sga-muted:#8A9B90}
.sga-dash a{text-decoration:none;color:inherit}
.sga-loading,.sga-empty{color:var(--sga-muted);padding:24px 4px;font-size:14px}
.sga-head{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;
 background:linear-gradient(125deg,#06200E 0%,#0C3520 55%,#124A2C 100%);color:#fff;border-radius:16px;padding:22px 24px;margin-top:4px;
 box-shadow:0 10px 30px rgba(8,40,22,.18)}
.sga-brand{display:flex;align-items:center;gap:12px}
.sga-logo{width:48px;height:48px;border-radius:12px;background:#fff;border:1px solid rgba(255,255,255,.4);
 display:grid;place-items:center;padding:6px;flex:0 0 auto;box-shadow:0 2px 6px rgba(0,0,0,.12)}
.sga-logo img{width:100%;height:100%;object-fit:contain;display:block}
.sga-bname{font-size:18px;font-weight:650}.sga-bsub{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:rgba(255,255,255,.72);margin-top:2px}
.sga-greet{display:flex;align-items:center;gap:12px}
.sga-greet .gtext{text-align:right}
.sga-greet .g1{font-size:15px;font-weight:600}.sga-greet .g2{font-size:12px;color:rgba(255,255,255,.75);margin-top:2px}
.sga-av{width:46px;height:46px;border-radius:50%;overflow:hidden;flex:0 0 auto;border:2px solid rgba(255,255,255,.45);
 background:rgba(255,255,255,.16);display:grid;place-items:center}
.sga-av img{width:100%;height:100%;object-fit:cover;display:block}
.sga-av.init{font-weight:700;font-size:15px;color:#fff}
.sga-ctx{display:flex;gap:26px;flex-wrap:wrap;margin:16px 4px 0}
.sga-ctx .c{display:flex;flex-direction:column}.sga-ctx .n{font-size:19px;font-weight:650}.sga-ctx .l{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--sga-muted)}
.sga-controls{display:flex;align-items:center;gap:12px;margin:14px 4px 0;flex-wrap:wrap}
.sga-controls .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--sga-muted);font-weight:600}
.sga-company{background:var(--sga-surface);color:var(--sga-ink);border:1px solid var(--sga-line);border-radius:8px;padding:6px 10px;font-size:13px;max-width:360px}
.sga-scope{font-size:12px;color:var(--sga-brand);font-weight:600}.sga-scope.muted{color:var(--sga-muted);font-weight:500}
.sga-sec{margin-top:26px}
.sga-eye{display:flex;align-items:center;gap:10px;margin-bottom:12px}.sga-eye.tight{margin-bottom:14px}
.sga-eye h2{font-size:12px;font-weight:700;letter-spacing:.11em;text-transform:uppercase;color:var(--sga-muted);margin:0}
.sga-eye .rule{height:1px;background:var(--sga-line);flex:1}
.sga-grid{display:grid;gap:14px}.sga-grid.k4{grid-template-columns:repeat(4,1fr)}.sga-grid.k3{grid-template-columns:repeat(3,1fr)}.sga-grid.k2{grid-template-columns:1fr 1fr}
@media(max-width:1000px){.sga-grid.k4{grid-template-columns:repeat(2,1fr)}.sga-grid.k3,.sga-grid.k2{grid-template-columns:1fr}}
.sga-card{background:var(--sga-surface);border:1px solid var(--sga-line);border-radius:13px;padding:16px}
.sga-card.kpi{position:relative;overflow:hidden}
.kpi .stripe{position:absolute;left:0;top:0;bottom:0;width:4px}
.kpi .cap{font-size:11.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--sga-muted);font-weight:600}
.kpi .big{font-size:28px;font-weight:700;margin-top:7px;letter-spacing:.01em}
.kpi .sub{font-size:12.5px;color:var(--sga-ink2);margin-top:7px}
.sga-mini{height:6px;border-radius:4px;background:var(--sga-surface2);border:1px solid var(--sga-line);overflow:hidden;margin-top:10px}
.sga-mini>i{display:block;height:100%;border-radius:4px}
.sga-chip{display:inline-flex;align-items:center;font-size:11.5px;font-weight:650;padding:2px 8px;border-radius:999px}
.sga-chip.good{background:color-mix(in srgb,var(--sga-good) 16%,transparent);color:var(--sga-good)}
.sga-chip.warn{background:color-mix(in srgb,var(--sga-amber) 20%,transparent);color:var(--sga-amber)}
.sga-chip.bad{background:color-mix(in srgb,var(--sga-bad) 16%,transparent);color:var(--sga-bad)}
.sga-stats{display:grid;grid-template-columns:repeat(8,1fr);gap:10px}
@media(max-width:1000px){.sga-stats{grid-template-columns:repeat(4,1fr)}}@media(max-width:560px){.sga-stats{grid-template-columns:repeat(2,1fr)}}
.sga-stat{background:var(--sga-surface);border:1px solid var(--sga-line);border-radius:11px;padding:12px;position:relative;display:block}
.sga-stat .dot{width:9px;height:9px;border-radius:50%;position:absolute;top:13px;right:12px}
.sga-stat .v{font-size:22px;font-weight:700}.sga-stat .n{font-size:11.5px;color:var(--sga-muted);margin-top:2px;line-height:1.3}
.sga-stats.sga-stats-sm{grid-template-columns:repeat(3,1fr)}@media(max-width:560px){.sga-stats.sga-stats-sm{grid-template-columns:repeat(2,1fr)}}
.sga-attnote{margin-top:10px;font-size:11.5px;color:var(--sga-muted);line-height:1.5}
.sga-cilist{display:flex;flex-direction:column;gap:2px}
.sga-ci{display:flex;align-items:center;gap:11px;padding:7px 4px;border-top:1px solid var(--sga-line);font-size:13px}
.sga-ci:first-child{border-top:0}
.sga-ci .io{font-size:10px;font-weight:700;padding:2px 9px;border-radius:999px;letter-spacing:.05em;min-width:40px;text-align:center}
.sga-ci .io.in{background:color-mix(in srgb,var(--sga-good) 16%,transparent);color:var(--sga-good)}
.sga-ci .io.out{background:color-mix(in srgb,var(--sga-slate) 20%,transparent);color:var(--sga-slate2)}
.sga-ci .tm{color:var(--sga-ink2)}
.sga-donwrap{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.sga-donut{--s:158px;width:var(--s);height:var(--s);flex:0 0 var(--s);border-radius:50%;position:relative;
 -webkit-mask:radial-gradient(circle at center,transparent 47px,#000 48px);mask:radial-gradient(circle at center,transparent 47px,#000 48px)}
.sga-donut .mid{position:absolute;inset:0;display:grid;place-items:center;text-align:center}
.sga-donut .mid b{font-size:24px;font-weight:750}.sga-donut .mid span{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--sga-muted)}
.sga-legend{flex:1;min-width:200px;display:flex;flex-direction:column;gap:8px}
.sga-legend .li{display:flex;align-items:center;gap:9px;font-size:13px}
.sga-legend .sw{width:11px;height:11px;border-radius:3px}.sga-legend .lab{flex:1;color:var(--sga-ink2)}.sga-legend .val{font-weight:700}
.sga-legend .pct{color:var(--sga-muted);font-size:12px;width:42px;text-align:right}
.sga-hbars{display:flex;flex-direction:column;gap:10px}
.hbar .top{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px}.hbar .top .lab{color:var(--sga-ink2)}.hbar .top .val{font-weight:700}
.track{height:9px;border-radius:5px;background:var(--sga-surface2);border:1px solid var(--sga-line);overflow:hidden}
.track>i{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,var(--sga-brand-soft),var(--sga-brand))}
.sga-qtitle{font-size:13px;font-weight:700;margin-bottom:8px}
.sga-qlist{display:flex;flex-direction:column}
.sga-qrow{display:flex;justify-content:space-between;gap:10px;padding:8px 6px;border-top:1px solid var(--sga-line);font-size:13px}
.sga-qrow:first-child{border-top:0}.sga-qrow:hover{background:var(--sga-surface2)}.sga-qrow .t{color:var(--sga-muted);font-size:12px}
.sga-links{display:flex;flex-direction:column;gap:8px}
.sga-shortcut{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--sga-line);border-radius:10px;background:var(--sga-surface2)}
.sga-shortcut:hover{border-color:var(--sga-brand)}.sga-shortcut .lb{font-weight:600;font-size:13.5px;flex:1}.sga-shortcut .mt{color:var(--sga-muted);font-size:12px}
.sga-shortcut .ic{color:var(--sga-brand);display:flex}
.sga-rep-title{font-size:13px;font-weight:700;margin-bottom:10px}
.sga-replist{display:flex;flex-direction:column;gap:2px}
.sga-rep{padding:9px 6px;border-top:1px solid var(--sga-line);font-size:13.5px;color:var(--sga-brand);font-weight:550}
.sga-rep:first-child{border-top:0}.sga-rep:hover{text-decoration:underline}
.sga-mini2{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:1000px){.sga-mini2{grid-template-columns:1fr}}
.sga-legend2{display:flex;gap:18px;margin-bottom:8px;font-size:12.5px;color:var(--sga-ink2)}
.sga-legend2 .lg{display:flex;align-items:center;gap:7px}
.sga-legend2 .lg i{width:13px;height:3px;border-radius:2px;display:inline-block}
.sga-trend svg{width:100%;height:160px;display:block}.sga-trend .gl{stroke:var(--sga-line);stroke-width:1}
.sga-trend .xlab{display:flex;justify-content:space-between;font-size:10px;color:var(--sga-muted);margin-top:4px}
.sga-funnel{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}@media(max-width:620px){.sga-funnel{grid-template-columns:repeat(2,1fr)}}
.fstep{background:var(--sga-surface2);border:1px solid var(--sga-line);border-radius:11px;padding:13px}
.fstep .v{font-size:24px;font-weight:750}.fstep .n{font-size:12px;color:var(--sga-muted);margin-top:3px}.fstep .arw{color:var(--sga-accent);font-weight:700}
.sga-period{display:flex;border:1px solid var(--sga-line);border-radius:8px;overflow:hidden;flex:0 0 auto}
.sga-period button{border:0;background:var(--sga-surface);color:var(--sga-muted);font-size:12px;font-weight:600;padding:5px 12px;cursor:pointer}
.sga-period button+button{border-left:1px solid var(--sga-line)}
.sga-period button.on{background:var(--sga-brand);color:#fff}
.sga-warn{margin-top:12px;font-size:12px;color:var(--sga-bad);background:color-mix(in srgb,var(--sga-bad) 10%,transparent);
 border:1px solid color-mix(in srgb,var(--sga-bad) 26%,transparent);border-radius:8px;padding:8px 10px}
.sga-dash .lnk{cursor:pointer}
.sga-card.kpi.lnk{transition:border-color .12s ease, box-shadow .12s ease}
.sga-card.kpi.lnk:hover{border-color:var(--sga-brand);box-shadow:0 4px 14px rgba(21,86,54,.12)}
.sga-stat[href]{transition:border-color .12s ease}.sga-stat[href]:hover{border-color:var(--sga-brand)}
.hbar.lnk:hover .lab{color:var(--sga-brand)}.hbar.lnk:hover .track{outline:1px solid var(--sga-brand);outline-offset:1px;border-radius:5px}
.sga-legend .li.lnk:hover .lab{color:var(--sga-brand)}
.sga-ctx a.c.lnk:hover .n{color:var(--sga-brand)}
.sga-hc{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.sga-hc .hc{font-size:12.5px;color:var(--sga-ink2);background:var(--sga-surface);border:1px solid var(--sga-line);border-radius:999px;padding:5px 12px}
.sga-hc .hc.total{background:var(--sga-brand);color:#fff;border-color:var(--sga-brand)}
.sga-hc .hc b{font-weight:700}
.sga-tblwrap{overflow-x:auto}
.sga-tbl{width:100%;border-collapse:collapse;font-size:13px}
.sga-tbl th{text-align:left;color:var(--sga-muted);font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;padding:7px 8px;border-bottom:1px solid var(--sga-line);white-space:nowrap}
.sga-tbl td{padding:7px 8px;border-bottom:1px solid var(--sga-line)}
.sga-tbl td.mut{color:var(--sga-muted)}
.sga-tbl td.num,.sga-tbl th.num{text-align:right;font-variant-numeric:tabular-nums}
.sga-tbl tbody tr:hover td{background:var(--sga-surface2)}
.sga-tbl td .z{color:var(--sga-muted)}
.sga-tbl td.tot{font-weight:700}
.sga-tbl a.tlnk{color:inherit;border-bottom:1px dotted var(--sga-line)}
.sga-tbl a.tlnk:hover{color:var(--sga-brand);border-bottom-color:var(--sga-brand)}
.sga-tbl td.num a.tlnk{border-bottom:0}.sga-tbl td.num a.tlnk:hover{text-decoration:underline}
.sga-foot{margin-top:26px;text-align:center;color:var(--sga-muted);font-size:12px}
`;
	const s = document.createElement("style");
	s.id = "sga-dash-style";
	s.textContent = css;
	document.head.appendChild(s);
}
