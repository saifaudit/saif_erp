# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Read-only data API for the SGA Job Orders management dashboard."""

import frappe

MANAGEMENT_ROLES = {
	"System Manager", "Job Order Admin", "Job Order Admin Support",
	"Job Order Partner", "Job Order Semi Admin",
}
HR_ROLES = {"System Manager", "HR Manager", "HR User"}


def _is_manager():
	return bool(MANAGEMENT_ROLES & set(frappe.get_roles()))


def _is_hr():
	return bool(HR_ROLES & set(frappe.get_roles()))


def _hr_overview():
	"""Firm-wide HR snapshot for admins who may see all employee records."""
	tdy = frappe.utils.today()
	active = frappe.db.count("Employee", {"status": "Active"})
	headcount = frappe.db.sql(
		"select company, count(*) n from `tabEmployee` where status='Active' group by company order by n desc", as_dict=True)
	on_leave = frappe.db.sql(
		"""select e.employee_name label, la.leave_type, la.from_date, la.to_date
		from `tabLeave Application` la join `tabEmployee` e on e.name = la.employee
		where la.docstatus=1 and la.status='Approved' and la.from_date <= %s and la.to_date >= %s
		order by la.to_date""", (tdy, tdy), as_dict=True)
	# per-employee leave balances (Annual/Earned, Sick, Casual, Legacy = carried-over)
	lts = ["Annual Leave", "Earned Leave", "Sick Leave (Medical Certificate)", "Casual Leave", "Legacy Leave"]
	rows = frappe.db.sql(
		"""select e.name emp, e.employee_name nm, e.company co, lle.leave_type lt, round(sum(lle.leaves),1) bal
		from `tabLeave Ledger Entry` lle join `tabEmployee` e on e.name = lle.employee
		where e.status='Active' and lle.docstatus=1 and lle.leave_type in %(lts)s
		group by e.name, lle.leave_type""", {"lts": tuple(lts)}, as_dict=True)
	bymap = {}
	for r in rows:
		d = bymap.setdefault(r.emp, {"emp": r.emp, "employee_name": r.nm, "company": r.co, "annual": 0, "sick": 0, "casual": 0, "legacy": 0})
		if r.lt in ("Annual Leave", "Earned Leave"):
			d["annual"] = r.bal
		elif "Sick" in r.lt:
			d["sick"] = r.bal
		elif r.lt == "Casual Leave":
			d["casual"] = r.bal
		elif r.lt == "Legacy Leave":
			d["legacy"] = r.bal
	team_leave = sorted(bymap.values(), key=lambda x: (x["company"] or "", x["employee_name"]))
	# team attendance this month (holiday-aware, per employee)
	team_attendance = []
	for e in frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name", "company"], order_by="company, employee_name"):
		a = _attendance_for(e.name)
		team_attendance.append({"emp": e.name, "employee_name": e.employee_name, "company": e.company,
		                        "present": a.get("Present", 0), "absent": a.get("Absent", 0),
		                        "on_leave": a.get("On Leave", 0), "holidays": a.get("holidays", 0),
		                        "working_days": a.get("working_days", 0)})
	month = frappe.utils.getdate(frappe.utils.today()).strftime("%B %Y")
	return {"active": active, "headcount": headcount, "on_leave": on_leave, "team_leave": team_leave,
	        "team_attendance": team_attendance, "month": month}


def _attendance_for(emp):
	"""Holiday-aware attendance summary (this month) for one employee.
	Excludes the weekly-off day (e.g. Sunday) and public holidays from the
	employee's Holiday List. Public holidays are Holiday rows; the weekly-off
	is only a setting, so we exclude it by weekday."""
	from datetime import timedelta
	if not emp:
		return {}
	month_start = frappe.utils.getdate(frappe.utils.get_first_day(frappe.utils.today()))
	tdy = frappe.utils.getdate(frappe.utils.today())
	emp_hl = frappe.db.get_value("Employee", emp, "holiday_list")
	holiday_dates, wo_idx = set(), None
	if emp_hl:
		weekly_off = frappe.db.get_value("Holiday List", emp_hl, "weekly_off")
		wo_idx = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}.get(weekly_off)
		holiday_dates = {frappe.utils.getdate(r[0]) for r in frappe.db.sql(
			"select holiday_date from `tabHoliday` where parent=%s and holiday_date between %s and %s",
			(emp_hl, month_start, tdy))}

	def is_off(dt):
		return dt in holiday_dates or (wo_idx is not None and dt.weekday() == wo_idx)

	counts = {"Present": 0, "Absent": 0, "Half Day": 0, "On Leave": 0, "Work From Home": 0}
	# cap at today — don't count future-dated attendance (e.g. long approved leaves)
	for r in frappe.db.sql("select attendance_date, status from `tabAttendance` where employee=%s and attendance_date between %s and %s and docstatus=1", (emp, month_start, tdy), as_dict=True):
		if r.status == "Absent" and is_off(frappe.utils.getdate(r.attendance_date)):
			continue
		counts[r.status] = counts.get(r.status, 0) + 1
	elapsed = (tdy - month_start).days + 1
	working_days = sum(1 for i in range(elapsed) if not is_off(month_start + timedelta(days=i)))
	return {**counts, "holidays": elapsed - working_days, "working_days": working_days,
	        "holiday_list": emp_hl, "month": tdy.strftime("%B %Y")}


def _personal(emp):
	"""Personal leave balance + holiday-aware attendance for one employee.
	Used by both the staff 'My Work' view and the manager's own card."""
	empty = {"my_leave": [], "my_attendance": {}, "my_checkins": []}
	if not emp:
		return empty
	my_leave = frappe.db.sql(
		"""select leave_type,
			sum(case when transaction_type='Leave Allocation' and is_expired=0 and leaves>0 then leaves else 0 end) allocated,
			-1*sum(case when transaction_type='Leave Application' then leaves else 0 end) taken,
			sum(leaves) balance
		from `tabLeave Ledger Entry` where employee=%s and docstatus=1
		group by leave_type having allocated<>0 or taken<>0 or balance<>0""",
		emp, as_dict=True,
	)
	my_attendance = _attendance_for(emp)
	my_checkins = frappe.get_all(
		"Employee Checkin", filters={"employee": emp},
		fields=["log_type", "time"], order_by="time desc", limit=8,
	)
	return {"my_leave": my_leave, "my_attendance": my_attendance, "my_checkins": my_checkins}


ACTIVE_STATUSES = "('Open','Progress','Under Review','Awaiting Client Data','Temporarily stopped','Pending')"


@frappe.whitelist()
def dashboard_data(period="year", company=None):
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
			fields=["name", "customer", "job_status", "modified"], order_by="modified desc", limit=10,
		)
		# jobs needing my attention (actionable to-do)
		my_action = frappe.get_all(
			"Job Order",
			filters={"accountant": me, "job_status": ["in", ["Awaiting Client Data", "Temporarily stopped", "Under Review"]]},
			fields=["name", "customer", "job_status", "modified"], order_by="modified desc", limit=8,
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
		my_trend = frappe.db.sql(
			f"""select DATE_FORMAT(job_date, '%%Y-%%m') label, count(*) created,
				sum(case when job_status='Finished' then 1 else 0 end) finished
			from {jo} where accountant=%(me)s and docstatus=1 and job_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
			group by label order by label""",
			{"me": me}, as_dict=True,
		)
		emp = frappe.db.get_value("Employee", {"user_id": me}, "name")
		_p = _personal(emp)
		my_leave, my_attendance, my_checkins = _p["my_leave"], _p["my_attendance"], _p["my_checkins"]
		return {
			"greeting": greeting, "manager": False, "my_status": my_status, "my_counts": my_counts,
			"recent_mine": recent, "my_leave": my_leave, "my_action": my_action,
			"my_by_service": my_by_service, "my_payment": my_payment, "my_trend": my_trend,
			"my_attendance": my_attendance, "my_checkins": my_checkins,
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
		"converted": frappe.db.count("Quotation", cfilt({"custom_job_order": ["is", "set"]})),
		"awaiting_acceptance": frappe.db.count("Quotation", cfilt({"custom_client_acceptance_type": "Not Confirmed"})),
		"awaiting_jo": frappe.db.count("Quotation", cfilt({"docstatus": 1, "custom_job_order": ["is", "not set"]})),
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

	return {
		"greeting": greeting, "manager": True, "counts": counts, "money": money,
		"active_jobs": active, "job_status": job_status, "payment_status": payment_status,
		"by_service": by_service, "by_month": by_month, "by_accountant": by_accountant,
		"orphan_active": orphan_active, "proposals": proposals,
		"aging": aging, "aging_total": aging_total, "top_customers": top_customers,
		"top_debtors": top_debtors, "rev_trend": rev_trend, "throughput": throughput,
		"compliance": compliance, "turnaround": turnaround,
		"companies": companies, "company": comp,
		"me_personal": _personal(frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")),
		"hr": _hr_overview() if _is_hr() else None,
		"recent": {"open": recent("Open"), "progress": recent("Progress"), "finished": recent("Finished")},
	}
