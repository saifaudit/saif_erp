# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Read-only data API for the SGA Job Orders management dashboard."""

import frappe

MANAGEMENT_ROLES = {
	"System Manager", "Job Order Admin", "Job Order Admin Support",
	"Job Order Partner", "Job Order Semi Admin",
}
# FULL management sees financials/sales/aging; Admin Support gets an operational
# view only (job orders, approvals, proposals) — no money/financial exposure.
FULL_MANAGEMENT_ROLES = {
	"System Manager", "Job Order Admin", "Job Order Partner", "Job Order Semi Admin",
}
# Team HR overview (leave balances, attendance) is management-only — not HR User
# or Admin Support. Keeps sensitive all-staff HR data to top management.
HR_ROLES = {"System Manager", "HR Manager"}


def _is_manager():
	return bool(MANAGEMENT_ROLES & set(frappe.get_roles()))


def _is_full_mgmt():
	return bool(FULL_MANAGEMENT_ROLES & set(frappe.get_roles()))


def _is_hr():
	return bool(HR_ROLES & set(frappe.get_roles()))


def _hr_overview(att_month=None):
	"""Firm-wide HR snapshot for admins who may see all employee records.
	att_month ('YYYY-MM') selects the month for the team-attendance table."""
	tdy = frappe.utils.today()
	att_month = att_month or frappe.utils.getdate(tdy).strftime("%Y-%m")
	active = frappe.db.count("Employee", {"status": "Active"})
	headcount = frappe.db.sql(
		"select company, count(*) n from `tabEmployee` where status='Active' group by company order by n desc", as_dict=True)
	on_leave = frappe.db.sql(
		"""select e.employee_name label, la.leave_type, la.from_date, la.to_date
		from `tabLeave Application` la join `tabEmployee` e on e.name = la.employee
		where la.docstatus=1 and la.status='Approved' and la.from_date <= %s and la.to_date >= %s
		order by la.to_date""", (tdy, tdy), as_dict=True)
	# current + upcoming approved leaves, with clash detection (overlapping staff)
	upcoming = frappe.db.sql(
		"""select e.employee_name label, la.employee emp, la.leave_type, la.from_date, la.to_date, la.total_leave_days days
		from `tabLeave Application` la join `tabEmployee` e on e.name = la.employee
		where la.docstatus=1 and la.status='Approved' and la.to_date >= %s
		order by la.from_date limit 30""", (tdy,), as_dict=True)
	for u in upcoming:
		others = {v["emp"] for v in upcoming if v["emp"] != u["emp"]
		          and v["from_date"] <= u["to_date"] and v["to_date"] >= u["from_date"]}
		u["clash"] = len(others)
	# days each employee already has committed to current+future approved leave
	future_by_emp = {}
	for u in upcoming:
		future_by_emp[u["emp"]] = future_by_emp.get(u["emp"], 0) + (u["days"] or 0)
	# per-employee leave balances (Annual/Earned, Sick, Casual, Legacy = carried-over)
	lts = ["Annual Leave", "Earned Leave", "Sick Leave (Medical Certificate)", "Casual Leave", "Legacy Leave"]
	yend = "%s-12-31" % frappe.utils.getdate(tdy).year  # scope balances to the current year
	rows = frappe.db.sql(
		"""select e.name emp, e.employee_name nm, e.company co, lle.leave_type lt, round(sum(lle.leaves),1) bal
		from `tabLeave Ledger Entry` lle join `tabEmployee` e on e.name = lle.employee
		where e.status='Active' and lle.docstatus=1 and lle.leave_type in %(lts)s and lle.from_date <= %(yend)s
		group by e.name, lle.leave_type""", {"lts": tuple(lts), "yend": yend}, as_dict=True)
	bymap = {}
	for r in rows:
		d = bymap.setdefault(r.emp, {"emp": r.emp, "employee_name": r.nm, "company": r.co,
		                             "annual": 0, "sick": 0, "casual": 0, "legacy": 0,
		                             "future": future_by_emp.get(r.emp, 0)})
		if r.lt in ("Annual Leave", "Earned Leave"):
			d["annual"] = r.bal
		elif "Sick" in r.lt:
			d["sick"] = r.bal
		elif r.lt == "Casual Leave":
			d["casual"] = r.bal
		elif r.lt == "Legacy Leave":
			d["legacy"] = r.bal
	team_leave = sorted(bymap.values(), key=lambda x: (x["company"] or "", x["employee_name"]))
	# legacy from the register (source of truth), not the broken allocation
	for d in team_leave:
		d["legacy"] = _legacy_balance(d["emp"])
	# team attendance this month (holiday-aware, per employee)
	team_attendance = []
	month_label = frappe.utils.getdate(att_month + "-01").strftime("%B %Y")
	for e in frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name", "company"], order_by="company, employee_name"):
		a = _attendance_for(e.name, att_month)
		team_attendance.append({"emp": e.name, "employee_name": e.employee_name, "company": e.company,
		                        "present": a.get("Present", 0), "absent": a.get("Absent", 0),
		                        "on_leave": a.get("On Leave", 0), "holidays": a.get("holidays", 0),
		                        "working_days": a.get("working_days", 0)})
	return {"active": active, "headcount": headcount, "on_leave": on_leave, "upcoming": upcoming,
	        "team_leave": team_leave, "team_attendance": team_attendance,
	        "month": month_label, "att_month": att_month}


def _attendance_for(emp, month=None):
	"""Holiday-aware attendance summary for one employee, for a given month
	('YYYY-MM'; defaults to the current month). Excludes the weekly-off day
	(e.g. Sunday) and public holidays from the employee's Holiday List. The
	current month is capped at today; past months use the full month."""
	from datetime import timedelta
	empty = {"Present": 0, "Absent": 0, "Half Day": 0, "On Leave": 0, "Work From Home": 0, "holidays": 0, "working_days": 0}
	if not emp:
		return {**empty, "holiday_list": None, "month": ""}
	tdy = frappe.utils.getdate(frappe.utils.today())
	try:
		month_start = frappe.utils.getdate(month + "-01") if month else frappe.utils.getdate(frappe.utils.get_first_day(tdy))
	except Exception:
		month_start = frappe.utils.getdate(frappe.utils.get_first_day(tdy))
	month_end = frappe.utils.getdate(frappe.utils.get_last_day(month_start))
	cap_end = min(month_end, tdy)  # don't count the future
	label = month_start.strftime("%B %Y")
	emp_hl = frappe.db.get_value("Employee", emp, "holiday_list")
	if cap_end < month_start:  # month is entirely in the future
		return {**empty, "holiday_list": emp_hl, "month": label}
	holiday_dates, wo_idx = set(), None
	if emp_hl:
		weekly_off = frappe.db.get_value("Holiday List", emp_hl, "weekly_off")
		wo_idx = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(weekly_off)
		holiday_dates = {frappe.utils.getdate(r[0]) for r in frappe.db.sql(
			"select holiday_date from `tabHoliday` where parent=%s and holiday_date between %s and %s",
			(emp_hl, month_start, cap_end))}

	def is_off(dt):
		return dt in holiday_dates or (wo_idx is not None and dt.weekday() == wo_idx)

	# Count attendance exactly as recorded, so every tile matches its click-through
	# list. (Sundays marked "Absent" therefore show up — a data pattern to fix at the
	# source rather than hide here.)
	counts = {"Present": 0, "Absent": 0, "Half Day": 0, "On Leave": 0, "Work From Home": 0}
	for r in frappe.db.sql("select attendance_date, status from `tabAttendance` where employee=%s and attendance_date between %s and %s and docstatus=1", (emp, month_start, cap_end), as_dict=True):
		counts[r.status] = counts.get(r.status, 0) + 1
	elapsed = (cap_end - month_start).days + 1
	working_days = sum(1 for i in range(elapsed) if not is_off(month_start + timedelta(days=i)))
	return {**counts, "holidays": elapsed - working_days, "working_days": working_days,
	        "holiday_list": emp_hl, "month": label,
	        "employee": emp, "from_date": str(month_start), "to_date": str(cap_end)}


def hr_report_exclude_users():
	"""User ids of management staff to leave OUT of the staff HR / performance
	reports — they approve/review, they don't do accountant or attendance work,
	so they should not be listed or rated as staff. By user id so it survives
	across sites; override with site_config `saif_hr_report_exclude`."""
	return frappe.conf.get("saif_hr_report_exclude") or [
		"santhosh@saifaudit.com", "chandy@saifaudit.com"]


def hr_report_exclude_names():
	"""Employee records for the excluded management users (see
	hr_report_exclude_users) — used to filter them out of the staff HR reports."""
	users = hr_report_exclude_users()
	return frappe.get_all("Employee", {"user_id": ["in", users]}, pluck="name")


def _legacy_balance(emp):
	"""Legacy (carried-over) leave balance from the custom Legacy Leave Register —
	the source of truth. Legacy is tracked in the register, not via allocations,
	so we read the closing balance rather than the (broken) Leave Allocation."""
	if not emp:
		return 0
	r = frappe.db.get_value("Legacy Leave Register", {"employee": emp},
	                        ["balance_legacy_leaves", "closing_balance_2025"], as_dict=True)
	if not r:
		return 0
	val = r.get("balance_legacy_leaves") or r.get("closing_balance_2025") or 0
	return max(0, val)  # a negative register balance is a source-data error; show 0 available


def _personal(emp):
	"""Personal leave balance + holiday-aware attendance for one employee.
	Used by both the staff 'My Work' view and the manager's own card."""
	empty = {"my_leave": [], "my_attendance": {}, "my_checkins": []}
	if not emp:
		return empty
	yend = "%s-12-31" % frappe.utils.getdate(frappe.utils.today()).year
	my_leave = frappe.db.sql(
		"""select leave_type,
			sum(case when transaction_type='Leave Allocation' and is_expired=0 and leaves>0 then leaves else 0 end) allocated,
			-1*sum(case when transaction_type='Leave Application' then leaves else 0 end) taken,
			sum(leaves) balance
		from `tabLeave Ledger Entry` where employee=%s and docstatus=1 and from_date <= %s
		group by leave_type having allocated<>0 or taken<>0 or balance<>0""",
		(emp, yend), as_dict=True,
	)
	# legacy from the register (source of truth), not the ledger
	legbal = _legacy_balance(emp)
	my_leave = [r for r in my_leave if r["leave_type"] != "Legacy Leave"]
	if legbal:
		my_leave.append({"leave_type": "Legacy Leave", "allocated": legbal, "taken": 0, "balance": legbal})
	my_attendance = _attendance_for(emp)
	my_checkins = frappe.get_all(
		"Employee Checkin", filters={"employee": emp},
		fields=["log_type", "time"], order_by="time desc", limit=40,
	)
	return {"my_leave": my_leave, "my_attendance": my_attendance, "my_checkins": my_checkins}


# Job Order aging buckets: (label, min_days, max_days) by days since job_date.
JOB_AGING_DEFS = [
	("≤10 days", 0, 10), ("11–20 days", 11, 20), ("21–30 days", 21, 30),
	("31–45 days", 31, 45), ("46–90 days", 46, 90), ("90+ days", 91, None),
]


def _job_aging(jo, extra_where, params):
	"""Aging of ACTIVE job orders (not Finished/Closed, not cancelled) by days since
	job_date. `extra_where` is appended SQL ('' or ' AND ...'); `params` binds it.
	Each bucket carries the job_date range (lo/hi) so the UI can build a drill-down
	list filter that matches the count exactly."""
	from frappe.utils import add_days, today
	t = today()
	r = frappe.db.sql(
		f"""select
			sum(datediff(curdate(), job_date) <= 10) b0,
			sum(datediff(curdate(), job_date) between 11 and 20) b1,
			sum(datediff(curdate(), job_date) between 21 and 30) b2,
			sum(datediff(curdate(), job_date) between 31 and 45) b3,
			sum(datediff(curdate(), job_date) between 46 and 90) b4,
			sum(datediff(curdate(), job_date) > 90) b5
		from {jo}
		where docstatus < 2 and job_status not in ('Finished','Closed (Failed)')
			and job_date is not null{extra_where}""",
		params, as_dict=True,
	)[0]
	counts = [r.b0, r.b1, r.b2, r.b3, r.b4, r.b5]
	out = []
	for (label, dlo, dhi), c in zip(JOB_AGING_DEFS, counts):
		hi = str(add_days(t, -dlo))
		lo = str(add_days(t, -dhi)) if dhi is not None else None
		out.append({"label": label, "count": int(c or 0), "lo": lo, "hi": hi})
	return out


def _filings_summary(accountant=None):
	"""Open compliance filings (within 90 days + overdue) bucketed for a dashboard card."""
	from collections import Counter
	from saif_erp.compliance import get_open_filings
	fils = get_open_filings(accountant=accountant, within_days=90, include_overdue=True)
	bc = Counter(f["band"] for f in fils)
	return {"total": len(fils), "Overdue": bc.get("Overdue", 0), "≤ 30 days": bc.get("≤ 30 days", 0),
	        "31 – 60 days": bc.get("31 – 60 days", 0), "61 – 90 days": bc.get("61 – 90 days", 0)}


ACTIVE_STATUSES = "('Open','Progress','Under Review','Awaiting Client Data','Temporarily stopped','Pending')"


@frappe.whitelist()
def dashboard_data(period="year", company=None, att_month=None):
	"""Aggregates for the SGA dashboard. Firm-wide figures are for managers;
	everyone else gets the header + their own recent job orders.

	period: 'year' (current calendar year, default) or 'all' (all time) —
	applies to the financial KPIs.
	"""
	jo = "`tabJob Order`"
	manager = _is_manager()
	period = "all" if str(period).lower() == "all" else "year"

	# ---- greeting (current user's employee card) ----
	emp = frappe.db.get_value(
		"Employee", {"user_id": frappe.session.user},
		["employee_name", "designation", "company", "department", "image"], as_dict=True,
	) or {}
	greeting = {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"employee_name": emp.get("employee_name"),
		"designation": emp.get("designation"),
		"company": emp.get("company"),
		"department": emp.get("department"),
		"image": frappe.db.get_value("User", frappe.session.user, "user_image") or emp.get("image"),
		"logo": frappe.db.get_single_value("Website Settings", "app_logo") or "/files/logoonly200x200.png",
		"is_manager": manager,
	}

	if not manager:
		# personal "My Work" payload — everything scoped to the signed-in user
		me = frappe.session.user
		my_status = {r["v"]: r["c"] for r in frappe.db.sql(
			f"select job_status v, count(*) c from {jo} where accountant=%s and docstatus=1 group by job_status",
			me, as_dict=True,
		)}
		active = ["Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending"]
		my_counts = {
			"active": sum(my_status.get(s, 0) for s in active),
			"open": my_status.get("Open", 0),
			"finished": my_status.get("Finished", 0),
			"attention": my_status.get("Awaiting Client Data", 0) + my_status.get("Temporarily stopped", 0),
		}
		recent = frappe.get_all(
			"Job Order", filters={"accountant": me},
			fields=["name", "customer", "company", "job_status", "job_status_remark", "modified"],
			order_by="modified desc", limit=10,
		)
		# jobs needing my attention (actionable to-do)
		my_action = frappe.get_all(
			"Job Order",
			filters={"accountant": me, "job_status": ["in", ["Awaiting Client Data", "Temporarily stopped", "Under Review"]]},
			fields=["name", "customer", "company", "job_status", "job_status_remark", "modified"],
			order_by="modified desc", limit=8,
		)
		my_by_service = frappe.db.sql(
			f"""select coalesce(it.item_name, jo.service, 'Unknown') label, count(*) value
			from {jo} jo left join `tabItem` it on it.name = jo.service
			where jo.accountant=%(me)s and jo.docstatus=1 group by label order by value desc limit 6""",
			{"me": me}, as_dict=True,
		)
		my_payment = {r["v"]: r["c"] for r in frappe.db.sql(
			f"select payment_status v, count(*) c from {jo} where accountant=%(me)s and docstatus=1 group by payment_status",
			{"me": me}, as_dict=True,
		)}
		# my proposal pipeline (accountants create proposals; this is their entry point)
		my_proposals = {
			"total": frappe.db.count("Quotation", {"owner": me}),
			"converted": frappe.db.count("Quotation", {"owner": me, "custom_job_order_created": 1}),
			"awaiting": frappe.db.count("Quotation", {"owner": me, "custom_client_acceptance_type": "Not Confirmed"}),
			# my proposals accepted + submitted but still not turned into a Job Order
			"awaiting_jo": frappe.db.count("Quotation", {"owner": me, "custom_client_acceptance_confirmed": 1, "custom_job_order_created": 0, "docstatus": 1}),
		}
		my_aging = _job_aging(jo, " AND accountant=%(me)s", {"me": me})
		my_filings = _filings_summary(accountant=me)
		emp = frappe.db.get_value("Employee", {"user_id": me}, "name")
		_p = _personal(emp)
		my_leave, my_attendance, my_checkins = _p["my_leave"], _p["my_attendance"], _p["my_checkins"]
		return {
			"greeting": greeting, "manager": False, "my_status": my_status, "my_counts": my_counts,
			"recent_mine": recent, "my_leave": my_leave, "my_action": my_action,
			"my_by_service": my_by_service, "my_payment": my_payment, "my_aging": my_aging,
			"my_filings": my_filings,
			"my_attendance": my_attendance, "my_checkins": my_checkins, "my_proposals": my_proposals,
		}

	# Optional company filter (group has multiple entities). Escaped + inlined so
	# the DATE_FORMAT('%Y-%m') queries are unaffected by param binding.
	comp = company if company and frappe.db.exists("Company", company) else None
	comp_val = frappe.db.escape(comp) if comp else None

	def cw(alias=None):
		if not comp:
			return ""
		col = f"{alias}.company" if alias else "company"
		return f" AND {col} = {comp_val}"

	def cfilt(f):
		if comp:
			f = dict(f); f["company"] = comp
		return f

	companies = frappe.db.sql(
		"select company label, count(*) n from `tabJob Order` where docstatus=1 and company is not null group by company order by n desc",
		as_dict=True,
	)

	def kv(rows):
		return {r["v"]: r["c"] for r in rows}

	job_status = kv(frappe.db.sql(f"select job_status v, count(*) c from {jo} where 1=1{cw()} group by job_status", as_dict=True))
	payment_status = kv(frappe.db.sql(f"select payment_status v, count(*) c from {jo} where 1=1{cw()} group by payment_status", as_dict=True))

	money_where = "docstatus=1" + (" AND YEAR(job_date)=YEAR(CURDATE())" if period == "year" else "") + cw()
	m = frappe.db.sql(
		f"select sum(invoiced_amount) inv, sum(paid_amount) paid, sum(proposed_amount) prop "
		f"from {jo} where {money_where}", as_dict=True,
	)[0]
	inv, paid = float(m.inv or 0), float(m.paid or 0)
	money = {
		"invoiced": inv, "collected": paid, "outstanding": inv - paid,
		"proposed": float(m.prop or 0),
		"collection_rate": round(paid / inv * 100) if inv else 0,
		"period": period, "period_label": "This year" if period == "year" else "All time",
	}
	# Billing status breakdown (counts + amounts), same scope as `money`. Drives the
	# Financial snapshot's status cards: waiting-to-invoice / paid / unpaid / partial.
	bill = frappe.db.sql(f"""
		select
		  sum(case when coalesce(invoiced_amount,0)=0 then 1 else 0 end) waiting_n,
		  sum(case when coalesce(invoiced_amount,0)=0 then coalesce(proposed_amount,0) else 0 end) waiting_amt,
		  sum(case when payment_status='Paid' then 1 else 0 end) paid_n,
		  sum(case when payment_status='Paid' then coalesce(paid_amount,0) else 0 end) paid_amt,
		  sum(case when payment_status='Not Paid' then 1 else 0 end) unpaid_n,
		  sum(case when payment_status='Not Paid' then coalesce(invoiced_amount,0)-coalesce(paid_amount,0) else 0 end) unpaid_amt,
		  sum(case when payment_status='Partial Payment' then 1 else 0 end) partial_n,
		  sum(case when payment_status='Partial Payment' then coalesce(invoiced_amount,0)-coalesce(paid_amount,0) else 0 end) partial_amt,
		  sum(case when payment_status='Hold / Dispute' then 1 else 0 end) hold_n,
		  sum(case when payment_status='Hold / Dispute' then coalesce(invoiced_amount,0)-coalesce(paid_amount,0) else 0 end) hold_amt
		from {jo} where {money_where}
	""", as_dict=True)[0]
	money["billing"] = {k: float(v or 0) for k, v in bill.items()}

	by_service = frappe.db.sql(
		f"""select coalesce(it.item_name, jo.service, 'Unknown') label, count(*) value,
			round(sum(jo.invoiced_amount)) revenue
		from {jo} jo left join `tabItem` it on it.name = jo.service
		where jo.docstatus = 1{cw("jo")} group by label order by revenue desc limit 8""", as_dict=True,
	)
	by_month = frappe.db.sql(
		f"""select DATE_FORMAT(job_date, '%Y-%m') label, count(*) value from {jo}
		where job_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH){cw()}
		group by label order by label""", as_dict=True,
	)
	# Current workload = ACTIVE job orders held by ACTIVE employees (excludes
	# resigned/unlinked accountants so ex-staff don't appear).
	by_accountant = frappe.db.sql(
		f"""select e.employee_name label, jo.accountant user, count(*) value
		from {jo} jo
		inner join `tabEmployee` e on e.user_id = jo.accountant and e.status = 'Active'
		where jo.docstatus = 1 and jo.job_status in {ACTIVE_STATUSES}{cw("jo")}
		group by jo.accountant, e.employee_name order by value desc limit 8""", as_dict=True,
	)
	# Data-hygiene: active jobs still assigned to non-active (resigned) staff.
	orphan_active = frappe.db.sql(
		f"""select count(*) from {jo} jo
		left join `tabEmployee` e on e.user_id = jo.accountant and e.status = 'Active'
		where jo.docstatus = 1 and jo.job_status in {ACTIVE_STATUSES} and e.name is null{cw("jo")}""",
	)[0][0]

	# Receivables aging (unpaid submitted job orders by invoice age)
	aging_rows = frappe.db.sql(
		f"""select case
			when datediff(curdate(), invoice_date) <= 30 then '0-30'
			when datediff(curdate(), invoice_date) <= 60 then '31-60'
			when datediff(curdate(), invoice_date) <= 90 then '61-90'
			else '90+' end bucket,
			count(*) n, round(sum(balance_amount)) amt
		from {jo} where docstatus=1 and balance_amount > 0 and invoice_date is not null{cw()}
		group by bucket""", as_dict=True,
	)
	order = {"0-30": 0, "31-60": 1, "61-90": 2, "90+": 3}
	aging = sorted(aging_rows, key=lambda r: order.get(r["bucket"], 9))
	aging_total = sum(float(r["amt"] or 0) for r in aging)

	# Revenue trend (invoiced vs collected) + throughput (created vs finished)
	rev_trend = frappe.db.sql(
		f"""select DATE_FORMAT(job_date, '%Y-%m') label, round(sum(invoiced_amount)) inv, round(sum(paid_amount)) paid
		from {jo} where docstatus=1 and job_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH){cw()}
		group by label order by label""", as_dict=True,
	)

	# Monthly sales (invoiced) — current year vs the previous two, for the admin.
	this_year = frappe.utils.getdate(frappe.utils.today()).year
	cur_month = frappe.utils.getdate(frappe.utils.today()).month
	sm = {y: [0.0] * 12 for y in (this_year - 2, this_year - 1, this_year)}
	for r in frappe.db.sql(
		f"""select year(job_date) yr, month(job_date) mo, round(sum(invoiced_amount)) amt
		from {jo} where docstatus=1 and job_date >= '{this_year - 2}-01-01'{cw()}
		group by yr, mo""", as_dict=True):
		if r.yr in sm and r.mo:
			sm[r.yr][int(r.mo) - 1] = float(r.amt or 0)
	ly_total = sum(sm[this_year - 1])
	ly_same = sum(sm[this_year - 1][:cur_month])
	ytd = sum(sm[this_year][:cur_month])
	sales_monthly = {
		"labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
		"years": [this_year - 2, this_year - 1, this_year],
		"series": {str(y): sm[y] for y in sm},
		"ytd": ytd, "ly_total": ly_total, "ly_same": ly_same,
		"ly_avg": round(ly_total / 12) if ly_total else 0,
		"yoy": round((ytd - ly_same) / ly_same * 100) if ly_same else 0,
	}
	throughput = frappe.db.sql(
		f"""select DATE_FORMAT(job_date, '%Y-%m') label, count(*) created,
			sum(case when job_status='Finished' then 1 else 0 end) finished
		from {jo} where docstatus=1 and job_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH){cw()}
		group by label order by label""", as_dict=True,
	)
	top_debtors = frappe.db.sql(
		f"""select c.customer_name label, jo.customer cust, round(sum(jo.balance_amount)) value
		from {jo} jo left join `tabCustomer` c on c.name = jo.customer
		where jo.docstatus=1 and jo.balance_amount > 0{cw("jo")}
		group by jo.customer order by value desc limit 6""", as_dict=True,
	)

	# Top customers by job count (+ revenue)
	top_customers = frappe.db.sql(
		f"""select c.customer_name label, jo.customer cust, count(*) value, round(sum(jo.invoiced_amount)) revenue
		from {jo} jo left join `tabCustomer` c on c.name = jo.customer
		where jo.docstatus=1{cw("jo")} group by jo.customer order by value desc limit 6""", as_dict=True,
	)

	# Compliance snapshot (working-paper rule only applies to jobs created on/after the cutoff)
	WP_CUTOFF = "2026-05-07"
	sub_total = frappe.db.count("Job Order", cfilt({"docstatus": 1}))
	wp_applicable = frappe.db.count("Job Order", cfilt({"job_status": "Finished", "creation": [">=", WP_CUTOFF]}))
	wp_done = frappe.db.count("Job Order", cfilt({"job_status": "Finished", "creation": [">=", WP_CUTOFF], "audit_working_paper_created": 1}))
	compliance = {
		"total": sub_total,
		"kyc": frappe.db.count("Job Order", cfilt({"docstatus": 1, "kyc_received": 1})),
		"loe": frappe.db.count("Job Order", cfilt({"docstatus": 1, "loe_received": 1})),
		"wp_applicable": wp_applicable, "wp_done": wp_done, "wp_pending": wp_applicable - wp_done,
	}

	# Average turnaround (finished jobs with a valid closure date)
	t = frappe.db.sql(
		f"""select round(avg(datediff(closure_date, job_date))) avg_days, count(*) n from {jo}
		where job_status='Finished' and closure_date is not null and closure_date >= job_date{cw()}""", as_dict=True,
	)[0]
	turnaround = {"avg_days": t.avg_days or 0, "n": t.n or 0}

	proposals = {
		"total": frappe.db.count("Quotation", cfilt({})),
		"converted": frappe.db.count("Quotation", cfilt({"custom_job_order_created": 1})),
		# proposals still awaiting the client's yes/no (excludes the few that are
		# already accepted-by-email/signed but sitting in Draft — those aren't "waiting").
		"awaiting_acceptance": frappe.db.count("Quotation", cfilt({"custom_client_acceptance_type": "Not Confirmed"})),
		# accepted by the client but not yet turned into a Job Order — only live,
		# submitted proposals count (exclude Cancelled + Draft), matching the card.
		"awaiting_jo": frappe.db.count("Quotation", cfilt({"custom_client_acceptance_confirmed": 1, "custom_job_order_created": 0, "docstatus": 1})),
	}

	def recent(status):
		return frappe.db.sql(
			f"select name, customer, modified from {jo} where job_status=%s{cw()} order by modified desc limit 5",
			(status,), as_dict=True,
		)

	counts = {
		"job_orders": frappe.db.count("Job Order", cfilt({})),
		"customers": frappe.db.count("Customer"),
		"employees": frappe.db.count("Employee", {"status": "Active"}),
		"proposals": proposals["total"],
		"credentials": frappe.db.count("Credential Manager"),
	}
	active = sum(job_status.get(s, 0) for s in
	             ["Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending"])

	# frequently-used approval queues (mirrors the old Admin Dash tabs).
	# approval_status='Pending' reliably tracks JOs awaiting approval (Draft +
	# Pending Approval); workflow_state='Pending Approval' misses backfilled ones.
	approvals = {
		"jo_pending": frappe.db.count("Job Order", {"approval_status": "Pending"}),
		"leave_pending": frappe.db.count("Leave Application", {"status": "Open"}),
		# attendance requests awaiting action (drafts not yet approved/submitted)
		"attendance_pending": frappe.db.count("Attendance Request", {"docstatus": 0}),
	}

	# Job Order aging (operational — kept for Admin Support too). Company-scoped
	# like the rest of the manager view; company_scope lets the UI match the drill-down.
	job_aging = _job_aging(jo, cw(), {})

	# Compliance filings due (firm-wide, operational — kept for Admin Support).
	filings = _filings_summary()

	# Employee document expiry summary (passport/visa/Emirates ID/etc within 90 days).
	# Personal-document data — full management only (blanked for Admin Support below).
	from collections import Counter as _Counter
	from saif_erp.document_expiry import get_expiring_documents as _ged
	_docs = _ged(company=comp, within_days=90)
	_bc = _Counter(d["band"] for d in _docs)
	doc_expiry = {"total": len(_docs), "Expired": _bc.get("Expired", 0),
	              "≤ 30 days": _bc.get("≤ 30 days", 0), "31 – 60 days": _bc.get("31 – 60 days", 0),
	              "61 – 90 days": _bc.get("61 – 90 days", 0)}

	# Admin Support gets an OPERATIONAL view — strip financial data from the payload
	# so money/sales/aging/debtors are neither shown nor sent.
	full_mgmt = _is_full_mgmt()
	if not full_mgmt:
		money = {"invoiced": 0, "collected": 0, "outstanding": 0, "proposed": 0,
		         "collection_rate": 0, "period": period, "period_label": money.get("period_label")}
		sales_monthly = None
		aging, aging_total, top_debtors, rev_trend, by_service = [], 0, [], [], []
		compliance = turnaround = None
		# doc_expiry kept — Admin Support manages employee documents (it holds no salary data)

	return {
		"greeting": greeting, "manager": True, "full_mgmt": full_mgmt, "counts": counts, "money": money,
		"zoho_enabled": bool(frappe.conf.get("zoho_books")),
		"approvals": approvals,
		"job_aging": job_aging, "company_scope": comp, "doc_expiry": doc_expiry, "filings": filings,
		"active_jobs": active, "job_status": job_status, "payment_status": payment_status,
		"by_service": by_service, "by_month": by_month, "by_accountant": by_accountant,
		"orphan_active": orphan_active, "proposals": proposals,
		"aging": aging, "aging_total": aging_total, "top_customers": top_customers,
		"top_debtors": top_debtors, "rev_trend": rev_trend, "throughput": throughput,
		"sales_monthly": sales_monthly,
		"compliance": compliance, "turnaround": turnaround,
		"companies": companies, "company": comp,
		"me_personal": _personal(frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")),
		"hr": _hr_overview(att_month) if _is_hr() else None,
		"recent": {"open": recent("Open"), "progress": recent("Progress"), "finished": recent("Finished")},
	}
