# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""One consolidated monthly report per employee — merges the old
Monthly / Work Flow / Contributor reports. Includes the employee's OWNED
jobs and the jobs they CONTRIBUTE to (Role column), with workflow (status,
aging, carry-forward, collaborators) and money (proposed/invoiced/paid).

Scope: managers see everyone (or one, via the Employee filter); other staff
are always locked to their own jobs — so it serves both the admin and the
employee versions from a single report."""

import json

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_first_day, getdate, nowdate

MGMT_ROLES = {"System Manager", "Job Order Admin", "Job Order Admin Support",
              "Job Order Semi Admin", "Job Order Partner", "HR Manager"}
ACTIVE = ("Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending")
DONE = ("Finished", "Closed (Failed)")
# "on hold" jobs stall for client/external reasons, not employee performance —
# excluded from the turnaround/efficiency time so staff aren't penalised for them.
HOLD = ("Temporarily stopped", "Awaiting Client Data")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.from_date:
		filters.from_date = get_first_day(nowdate())
	if not filters.to_date:
		filters.to_date = nowdate()
	data, summary, chart, message = get_data(filters)
	return get_columns(), data, message, chart, summary


# relative-rating weights. Invoiced amount is weighted highest (per management).
# Speed's weight is redistributed to the others when an employee has no datable
# finished jobs, so missing time data never drags a rating down.
# NOTE: a manual reviewer rating is planned to be blended in later — see
# saif-erp-reports-rating memory.
# One unified weighted rating (management-set). Each component is scored 0–1 and
# the weights of any missing components (no turnaround data, no reviewer mark) are
# redistributed across the rest — so a blank never penalises. Review = mark/10.
RATING_W = {"finished": 0.32, "volume": 0.30, "invoiced": 0.10, "collected": 0.10,
            "speed": 0.08, "review": 0.10}


def compute_team_ratings(frm, to):
	"""Per-employee metrics for the period, scored RELATIVE to the whole team.
	Volume credits owner + collaborators; invoiced / finished / turnaround credit
	the owning accountant only. Returns {user_id: {...score, stars, rank...}}."""
	from saif_erp import api
	# management staff (approvers/reviewers) are not rated or ranked as accountants
	ex_users = set(api.hr_report_exclude_users())
	frm, to = getdate(frm), getdate(to)
	params = {"from": frm, "to": to, "active": ACTIVE}
	period = ("(jo.job_date between %(from)s and %(to)s"
	          " or (jo.job_date < %(from)s and jo.job_status in %(active)s)"
	          " or (jo.job_date < %(from)s and jo.closure_date between %(from)s and %(to)s))")
	sql = f"""
		select 'o' role, jo.name, jo.accountant emp, jo.job_status, jo.job_date,
			jo.closure_date, jo.invoiced_amount, jo.paid_amount, jo.custom_reviewer_rating rrating
		from `tabJob Order` jo where jo.docstatus=1 and {period} and jo.accountant is not null
		union all
		select 'c', jo.name, joc.to_accountant, jo.job_status, jo.job_date,
			jo.closure_date, jo.invoiced_amount, jo.paid_amount, jo.custom_reviewer_rating
		from `tabJob Order Contributors` joc join `tabJob Order` jo on jo.name = joc.parent
		where jo.docstatus=1 and {period} and joc.to_accountant is not null
	"""
	rows = frappe.db.sql(sql, params, as_dict=True)
	names = list({r.name for r in rows})
	finish = _finish_dates(names)
	stopped = _stopped_days(names)  # days each job spent Temporarily stopped

	agg = {}
	for r in rows:
		if r.emp in ex_users:
			continue  # management/approver — never listed or rated as staff
		m = agg.setdefault(r.emp, {"volume": 0, "invoiced": 0.0, "collected": 0.0,
		                           "finished": 0, "turns": [], "reviews": []})
		m["volume"] += 1
		if r.role != "o":
			continue  # money, completion & review credit only to the owning accountant
		if r.rrating:  # reviewer mark on this owned job (0–10)
			m["reviews"].append(flt(r.rrating))
		if r.job_date and frm <= getdate(r.job_date) <= to:
			m["invoiced"] += flt(r.invoiced_amount)   # billed this period
			m["collected"] += flt(r.paid_amount)      # received this period
		fin = r.closure_date or finish.get(r.name)
		fin = getdate(fin) if fin else None
		if r.job_status in DONE and fin and frm <= fin <= to and r.job_date:
			m["finished"] += 1
			# active turnaround = elapsed minus time the job was Temporarily stopped
			active_days = max(0, date_diff(fin, getdate(r.job_date)) - stopped.get(r.name, 0))
			m["turns"].append(active_days)

	if not agg:
		return {}

	# Everyone with activity keeps a rating (so a resigned person's own report
	# still shows a score). But the comparison BENCHMARK and the RANKING use only
	# currently-active staff — resigned/left people don't pad "#N of M" or the
	# leaderboard. Each rating record carries `active` so callers can filter.
	active = {
		e.user_id
		for e in frappe.get_all(
			"Employee", filters={"status": "Active", "user_id": ["is", "set"]},
			fields=["user_id"],
		)
		if e.user_id not in ex_users
	}
	for m in agg.values():
		m["avg_turn"] = round(sum(m["turns"]) / len(m["turns"])) if m["turns"] else None
	bench = [m for u, m in agg.items() if u in active] or list(agg.values())
	mx = {k: max((m[k] for m in bench), default=0) or 1
	      for k in ("volume", "invoiced", "collected", "finished")}
	best_turn = min((m["avg_turn"] for m in bench if m["avg_turn"]), default=None)

	# Unified weighted score: each present component scored 0–1 relative to the
	# team (review is mark/10, absolute); the weights of any absent component
	# (no turnaround, no reviewer mark) are redistributed, so a blank never hurts.
	for u, m in agg.items():
		m["active"] = u in active
		parts = {
			"volume": m["volume"] / mx["volume"],
			"invoiced": m["invoiced"] / mx["invoiced"],
			"collected": m["collected"] / mx["collected"],
			"finished": m["finished"] / mx["finished"],
		}
		if m["avg_turn"] and best_turn:
			parts["speed"] = best_turn / m["avg_turn"]  # 1.0 = fastest in team
		m["review_avg"] = (sum(m["reviews"]) / len(m["reviews"])) if m["reviews"] else None
		m["review_n"] = len(m["reviews"])
		if m["reviews"]:
			parts["review"] = m["review_avg"] / 10.0
		total_w = sum(RATING_W[k] for k in parts)
		score = sum(v * RATING_W[k] for k, v in parts.items()) / total_w
		m["score"] = round(score * 100)

	# rank + stars are relative to the ACTIVE team only
	ranked = sorted((kv for kv in agg.items() if kv[1]["active"]), key=lambda kv: -kv[1]["score"])
	top = (ranked[0][1]["score"] if ranked else max((m["score"] for m in agg.values()), default=0)) or 1
	for i, (_emp, m) in enumerate(ranked, 1):
		m["rank"], m["team"] = i, len(ranked)
	for m in agg.values():
		m.setdefault("rank", None)
		m.setdefault("team", len(ranked))
		m["stars"] = max(1, min(5, round(5 * m["score"] / top)))
	return agg


# ---- shared, restrained palette + rating HTML (used on-screen and in the PDF) ----
C_GREEN = "#0E4A34"
C_GOLD = "#C08A2E"
C_MUTED = "#78837C"
C_LINE = "#E3E8E4"
C_TINT = "#F4F8F5"


def star_html(n, size=14):
	n = int(n or 0)
	return "".join(
		"<span style='color:%s;font-size:%dpx;letter-spacing:1px'>&#9733;</span>"
		% (C_GOLD if i < n else "#D7DCD8", size)
		for i in range(5)
	)


def rating_badge_html(m, show_rank=True):
	"""Compact rating badge: stars + score, optional rank."""
	rank = ""
	if show_rank and m.get("rank"):
		rank = ("<span style='margin-left:12px;color:%s;font-weight:600;font-size:12px'>"
		        "Rank #%d</span>" % (C_GREEN, m["rank"]))
	return (
		"<div style='display:inline-flex;align-items:center;gap:10px;padding:6px 14px;"
		"background:%s;border:1px solid %s;border-radius:20px'>"
		"<span style='font-size:11px;font-weight:700;letter-spacing:.6px;color:%s;"
		"text-transform:uppercase'>Rating</span>%s"
		"<span style='font-weight:800;color:%s;font-size:15px'>%d<span style='color:%s;"
		"font-size:11px;font-weight:600'>/100</span></span>%s</div>"
		% (C_TINT, C_LINE, C_MUTED, star_html(m.get("stars", 0)), C_GREEN, m.get("score", 0), C_MUTED, rank)
	)


def leaderboard_html(ratings):
	"""Active-team rating table (admin view)."""
	active = {u: m for u, m in ratings.items() if m.get("active")}
	if not active:
		return ""
	emap = {
		e.user_id: (e.employee_name, e.company or "")
		for e in frappe.get_all("Employee", filters={"user_id": ["in", list(active)]},
		                        fields=["user_id", "employee_name", "company"])
	}
	head = ("#", "Employee", "Company", "Works", "Finished", "Turn (d)", "Invoiced", "Score", "Rating")
	th = "".join("<th style='padding:6px 8px;text-align:%s'>%s</th>"
	             % ("right" if h in ("Works", "Finished", "Turn (d)", "Invoiced", "Score", "#") else "left", h)
	             for h in head)
	trs = []
	for _u, m in sorted(active.items(), key=lambda kv: kv[1]["rank"]):
		name, company = emap.get(_u, (_u, ""))
		turn = m["avg_turn"] if m["avg_turn"] is not None else "—"
		bg = C_TINT if m["rank"] % 2 == 0 else "#fff"
		cells = [
			("r", m["rank"]), ("l", frappe.utils.escape_html(name)),
			("lm", frappe.utils.escape_html(company)), ("r", m["volume"]),
			("r", m["finished"]), ("r", turn),
			("r", frappe.utils.fmt_money(m["invoiced"])), ("r", m["score"]),
			("st", star_html(m["stars"], 12)),
		]
		tds = []
		for kind, val in cells:
			align = "right" if kind == "r" else "left"
			color = ";color:%s;font-size:10px" % C_MUTED if kind == "lm" else ""
			nowrap = ";white-space:nowrap" if kind in ("r", "st") else ""
			tds.append("<td style='padding:5px 8px;text-align:%s;border-bottom:1px solid %s%s%s'>%s</td>"
			           % (align, C_LINE, color, nowrap, val))
		trs.append("<tr style='background:%s'>%s</tr>" % (bg, "".join(tds)))
	return (
		"<div style='font-size:13px;font-weight:800;color:%s;margin:2px 0 6px'>Employee Rating "
		"<span style='font-size:9.5px;font-weight:500;color:%s'>· Finished 32%% · Volume 30%% · "
		"Invoiced 10%% · Collected 10%% · Time 8%% · Report quality 10%% (active team; blanks redistributed)</span></div>"
		"<table style='width:100%%;border-collapse:collapse;font-size:11px'>"
		"<thead><tr style='background:%s;color:#fff'>%s</tr></thead><tbody>%s</tbody></table>"
		% (C_GREEN, C_MUTED, C_GREEN, th, "".join(trs))
	)


def get_columns():
	return [
		{"label": _("Role"), "fieldname": "role", "fieldtype": "Data", "width": 95},
		{"label": _("Job Order"), "fieldname": "job_order", "fieldtype": "Link", "options": "Job Order", "width": 135},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 175},
		{"label": _("Service"), "fieldname": "service", "fieldtype": "Data", "width": 150},
		{"label": _("Status"), "fieldname": "job_status", "fieldtype": "Data", "width": 130},
		{"label": _("Job Date"), "fieldname": "job_date", "fieldtype": "Date", "width": 90},
		{"label": _("Aging"), "fieldname": "aging", "fieldtype": "Data", "width": 75},
		{"label": _("Carry Fwd"), "fieldname": "carry_forward", "fieldtype": "Data", "width": 80},
		{"label": _("Other Accountants"), "fieldname": "other_accountants", "fieldtype": "Data", "width": 175},
		{"label": _("Proposed"), "fieldname": "proposed_amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Invoiced"), "fieldname": "invoiced_amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Paid"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 100},
		{"label": _("Transfer"), "fieldname": "transfer", "fieldtype": "Data", "width": 140},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
	]


def _finish_dates(names):
	"""Best-effort finish date per job from the change-log (track_changes): the
	timestamp it last moved into a DONE status. Used only where the manual
	Closure Date is blank (which is ~93% of finished jobs). Historical/migrated
	jobs with no change-log simply have no finish date and are left out of the
	turnaround average rather than guessed."""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select docname, creation, data from `tabVersion`
		   where ref_doctype='Job Order' and docname in %(n)s
		     and data like '%%job_status%%' order by creation asc""",
		{"n": tuple(names)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		try:
			d = json.loads(r.data)
		except Exception:
			continue
		for ch in d.get("changed", []):
			if ch and ch[0] == "job_status" and ch[2] in DONE:
				out[r.docname] = getdate(r.creation)  # asc order → last DONE wins
	return out


def _stopped_days(names):
	"""Days each job spent in 'Temporarily stopped' (from the change-log), so that
	client-caused pauses can be removed from the accountant's turnaround. Reads the
	job_status transitions: time from entering 'Temporarily stopped' until it moves
	to any other status. Jobs with no change-log return 0 (nothing to exclude)."""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select docname, creation, data from `tabVersion`
		   where ref_doctype='Job Order' and docname in %(n)s
		     and data like '%%job_status%%' order by creation asc""",
		{"n": tuple(names)},
		as_dict=True,
	)
	out, since = {}, {}
	for r in rows:
		try:
			d = json.loads(r.data)
		except Exception:
			continue
		for ch in d.get("changed", []):
			if not ch or ch[0] != "job_status":
				continue
			when = getdate(r.creation)
			if ch[2] == "Temporarily stopped":
				since[r.docname] = when
			elif ch[1] == "Temporarily stopped" and r.docname in since:
				out[r.docname] = out.get(r.docname, 0) + date_diff(when, since.pop(r.docname))
	return out


def get_data(filters):
	is_mgr = bool(MGMT_ROLES & set(frappe.get_roles()))
	users = None  # None = all (managers)
	if filters.get("employee"):
		uid = frappe.db.get_value("Employee", filters.employee, "user_id")
		users = [uid or "__none__"]
	if not is_mgr:
		users = [frappe.session.user]  # staff always locked to self

	params = {"from": filters.from_date, "to": filters.to_date, "active": ACTIVE}
	# new-this-period OR carried-forward-and-still-active OR carried-and-closed-this-period
	period = ("(jo.job_date between %(from)s and %(to)s"
	          " or (jo.job_date < %(from)s and jo.job_status in %(active)s)"
	          " or (jo.job_date < %(from)s and jo.closure_date between %(from)s and %(to)s))")
	owned_u = contrib_u = ""
	if users is not None:
		params["users"] = tuple(users)
		owned_u = " and jo.accountant in %(users)s"
		contrib_u = " and joc.to_accountant in %(users)s"

	collab = "(select group_concat(distinct c2.to_accountant separator ', ') from `tabJob Order Contributors` c2 where c2.parent=jo.name)"
	sql = f"""
		select 'Accountant' role, jo.name job_order, jo.customer, coalesce(it.item_name, jo.service) service,
			jo.job_status, jo.job_date, jo.closure_date, jo.accountant emp_user,
			jo.proposed_amount, jo.invoiced_amount, jo.paid_amount, jo.job_status_remark remarks,
			jo.transferred_from, jo.transferred_to, {collab} other_accountants, jo.custom_reviewer_rating rrating
		from `tabJob Order` jo left join `tabItem` it on it.name = jo.service
		where jo.docstatus=1 and {period}{owned_u}
		union all
		select 'Contributor', jo.name, jo.customer, coalesce(it.item_name, jo.service),
			jo.job_status, jo.job_date, jo.closure_date, joc.to_accountant,
			jo.proposed_amount, jo.invoiced_amount, jo.paid_amount, jo.job_status_remark,
			jo.transferred_from, jo.transferred_to, {collab}, jo.custom_reviewer_rating
		from `tabJob Order Contributors` joc
		join `tabJob Order` jo on jo.name = joc.parent
		left join `tabItem` it on it.name = jo.service
		where jo.docstatus=1 and {period}{contrib_u}
		order by job_date desc
	"""
	rows = frappe.db.sql(sql, params, as_dict=True)
	frm = getdate(filters.from_date)
	to = getdate(filters.to_date)
	tdy = getdate(nowdate())
	finish_log = _finish_dates(list({r.job_order for r in rows}))
	out, turnaround = [], []  # turnaround = finished jobs with a known finish date
	for r in rows:
		# In the all-staff view the owner row + "Other Accountants" column already
		# convey collaboration, so drop the redundant collaborator rows there — one
		# row per job keeps counts, money and drill-downs consistent. In a single-
		# person view the collaborator rows are kept (that's how they see jobs they
		# only contributed to).
		if users is None and r.role == "Contributor":
			continue
		fin = r.closure_date or finish_log.get(r.job_order)
		fin = getdate(fin) if fin else None
		is_done = r.job_status in DONE
		on_hold = r.job_status in HOLD
		end = fin if (is_done and fin) else tdy
		aging = date_diff(end, r.job_date) if r.job_date else 0
		if is_done and fin and r.job_date and frm <= fin <= to and r.role == "Accountant":
			turnaround.append(date_diff(fin, r.job_date))
		transfer = ""
		if r.transferred_to or r.transferred_from:
			transfer = ("%s → %s" % (r.transferred_from or "—", r.transferred_to or "—"))
		others = (r.other_accountants or "")
		if r.emp_user:
			others = ", ".join(a for a in others.split(", ") if a and a != r.emp_user)
		out.append({
			"role": r.role, "job_order": r.job_order, "customer": r.customer, "service": r.service,
			"job_status": r.job_status, "job_date": r.job_date,
			"aging": ("%d days" % aging),
			"carry_forward": "Yes" if (r.job_date and getdate(r.job_date) < frm) else "No",
			"other_accountants": others,
			"proposed_amount": flt(r.proposed_amount), "invoiced_amount": flt(r.invoiced_amount),
			"paid_amount": flt(r.paid_amount), "transfer": transfer, "remarks": r.remarks,
			"reviewer_rating": r.rrating,
			"_finish": fin, "_done": is_done, "_hold": on_hold,
		})

	# ---- efficiency summary (headline numbers) ----
	# Money is split into THIS-PERIOD jobs vs CARRIED-FORWARD jobs so the
	# headline figures reflect only the selected month, not value that may
	# have been invoiced/earned in earlier months on still-open jobs.
	# Dedupe to job level: an owner row + a collaborator row are the SAME job, so
	# counting rows would inflate totals (badly on wide ranges / all-staff). Counts
	# use unique jobs; money is credited to the OWNER row only, so a job's invoiced
	# amount is counted exactly once and never against a collaborator.
	jobs = {}
	for d in out:
		if d["job_order"] not in jobs or d["role"] == "Accountant":
			jobs[d["job_order"]] = d
	jobs = list(jobs.values())
	owner_rows = [d for d in out if d["role"] == "Accountant"]

	this_jobs = [d for d in jobs if d["carry_forward"] == "No"]
	carr_jobs = [d for d in jobs if d["carry_forward"] == "Yes"]
	this_month = len(this_jobs)
	carried = len(carr_jobs)
	single = sum(1 for d in jobs if not d["other_accountants"] and d["role"] == "Accountant")
	collab = sum(1 for d in jobs if d["other_accountants"] or d["role"] == "Contributor")
	# Finished THIS PERIOD = jobs whose finish date falls inside the window
	# (not merely "currently Finished"), so it measures output for the period.
	finished_period = sum(1 for d in jobs if d["_done"] and d["_finish"] and frm <= d["_finish"] <= to)
	on_hold = sum(1 for d in jobs if d["_hold"])
	# fair turnaround: finished jobs with a known finish date only — excludes
	# still-open and on-hold jobs, so client-side delays don't inflate it.
	avg_turn = round(sum(turnaround) / len(turnaround)) if turnaround else "—"
	inv_new = sum(d["invoiced_amount"] for d in owner_rows if d["carry_forward"] == "No")
	col_new = sum(d["paid_amount"] for d in owner_rows if d["carry_forward"] == "No")
	inv_carr = sum(d["invoiced_amount"] for d in owner_rows if d["carry_forward"] == "Yes")
	col_carr = sum(d["paid_amount"] for d in owner_rows if d["carry_forward"] == "Yes")
	# restrained indicators: green = output/money, red = attention, grey = neutral
	summary = [
		{"label": _("Works handled"), "value": len(jobs), "datatype": "Int", "indicator": "Green"},
		{"label": _("New this period"), "value": this_month, "datatype": "Int", "indicator": "Grey"},
		{"label": _("Carried forward"), "value": carried, "datatype": "Int", "indicator": "Grey"},
		{"label": _("Single work"), "value": single, "datatype": "Int", "indicator": "Grey"},
		{"label": _("Collaborated"), "value": collab, "datatype": "Int", "indicator": "Grey"},
		{"label": _("Finished this period"), "value": finished_period, "datatype": "Int", "indicator": "Green"},
		{"label": _("On hold (client)"), "value": on_hold, "datatype": "Int", "indicator": "Red"},
		{"label": _("Avg turnaround (finished, days)"), "value": avg_turn,
		 "datatype": "Int" if turnaround else "Data", "indicator": "Grey"},
		{"label": _("Invoiced (this period)"), "value": inv_new, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Collected (this period)"), "value": col_new, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Invoiced (carried fwd)"), "value": inv_carr, "datatype": "Currency", "indicator": "Grey"},
		{"label": _("Collected (carried fwd)"), "value": col_carr, "datatype": "Currency", "indicator": "Grey"},
	]

	# ---- who the report covers + the rating, rendered in the banner ----
	target_uid = None
	if filters.get("employee"):
		target_uid = frappe.db.get_value("Employee", filters.employee, "user_id")
	elif not is_mgr:
		target_uid = frappe.session.user
	ratings = compute_team_ratings(frm, to)
	rating_block = ""
	if target_uid and ratings.get(target_uid):
		# staff self-view drops the rank; managers viewing one employee keep it
		rating_block = ("<div style='margin-top:8px'>%s</div>"
		                % rating_badge_html(ratings[target_uid], show_rank=is_mgr))
	elif not target_uid and is_mgr:  # admin all-staff view → full leaderboard
		rating_block = "<div style='margin-top:10px'>%s</div>" % leaderboard_html(ratings)

	# ---- clickable drill-downs: filter the table to a category ----
	cat = (filters.get("category") or "").strip()
	drill = _drill_html([
		("all", _("All"), len(jobs)),
		("new", _("New"), this_month),
		("carried", _("Carried fwd"), carried),
		("finished", _("Finished"), finished_period),
		("on_hold", _("On hold"), on_hold),
		("collaborated", _("Collaborated"), collab),
	], cat)
	message = _banner(filters, is_mgr) + drill + rating_block

	# ---- chart: workload by status ----
	from collections import Counter
	sc = Counter(d["job_status"] for d in out)
	chart = {
		"type": "donut",
		"data": {"labels": list(sc.keys()), "datasets": [{"name": "Jobs", "values": list(sc.values())}]},
		"height": 260,
	}

	# apply the drill-down filter to the TABLE only (summary stays whole-period)
	data = [d for d in out if _in_category(d, cat, frm, to)]
	return data, summary, chart, message


def _in_category(d, cat, frm, to):
	if not cat or cat == "all":
		return True
	if cat == "new":
		return d["carry_forward"] == "No"
	if cat == "carried":
		return d["carry_forward"] == "Yes"
	if cat == "finished":
		return bool(d["_done"] and d["_finish"] and frm <= d["_finish"] <= to)
	if cat == "on_hold":
		return bool(d["_hold"])
	if cat == "collaborated":
		return bool(d["other_accountants"] or d["role"] == "Contributor")
	return True


def _drill_html(items, active):
	active = active or "all"
	links = []
	for key, label, val in items:
		on = (key == active) or (active == "" and key == "all")
		style = ("background:%s;color:#fff;" % C_GREEN) if on else ("background:%s;color:%s;" % (C_TINT, C_GREEN))
		links.append(
			"<a href='#' class='sga-drill' data-cat='%s' style='%s"
			"border:1px solid %s;border-radius:14px;padding:3px 11px;margin:0 5px 4px 0;"
			"display:inline-block;font-size:11.5px;text-decoration:none;font-weight:600'>"
			"%s <span style='opacity:.8'>%s</span></a>"
			% (key, style, C_LINE, frappe.utils.escape_html(label), val)
		)
	return ("<div style='margin-top:9px'><span style='font-size:10px;color:%s;"
	        "text-transform:uppercase;letter-spacing:.5px;margin-right:6px'>View</span>%s</div>"
	        % (C_MUTED, "".join(links)))


def _banner(filters, is_mgr):
	"""HTML banner shown above the report naming who/what it covers."""
	name, company = _("All Staff"), _("All Entities")
	emp = filters.get("employee")
	if not emp and not is_mgr:
		emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if emp:
		row = frappe.db.get_value("Employee", emp, ["employee_name", "company"])
		if row:
			name, company = row[0] or emp, row[1] or ""
	period = "%s — %s" % (getdate(filters.from_date).strftime("%d %b %Y"),
	                      getdate(filters.to_date).strftime("%d %b %Y"))
	return (
		"<div style='padding:9px 14px;border-left:5px solid #3DB54A;background:#f3faf5;"
		"border-radius:6px;margin:2px 0 4px'>"
		"<span style='font-size:16px;font-weight:800;color:#155636'>%s</span>"
		"<span style='color:#155636;font-weight:600'>%s</span>"
		"<span style='color:#777;margin-left:10px;font-size:12px'>%s</span></div>"
		% (frappe.utils.escape_html(name),
		   ("  ·  " + frappe.utils.escape_html(company)) if company else "",
		   frappe.utils.escape_html(period))
	)
