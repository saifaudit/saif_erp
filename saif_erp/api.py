# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Read-only data API for the SGA Job Orders management dashboard."""

import frappe

MANAGEMENT_ROLES = {
	"System Manager", "Job Order Admin", "Job Order Admin Support",
	"Job Order Partner", "Job Order Semi Admin",
}


def _is_manager():
	return bool(MANAGEMENT_ROLES & set(frappe.get_roles()))


ACTIVE_STATUSES = "('Open','Progress','Under Review','Awaiting Client Data','Temporarily stopped','Pending')"


@frappe.whitelist()
def dashboard_data(period="year"):
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
		emp = frappe.db.get_value("Employee", {"user_id": me}, "name")
		my_leave = []
		if emp:
			my_leave = frappe.db.sql(
				"""select leave_type,
					sum(case when transaction_type='Leave Allocation' and is_expired=0 and leaves>0 then leaves else 0 end) allocated,
					-1*sum(case when transaction_type='Leave Application' then leaves else 0 end) taken,
					sum(leaves) balance
				from `tabLeave Ledger Entry` where employee=%s and docstatus=1
				group by leave_type having allocated<>0 or taken<>0 or balance<>0""",
				emp, as_dict=True,
			)
		return {
			"greeting": greeting, "manager": False, "my_status": my_status,
			"my_counts": my_counts, "recent_mine": recent, "my_leave": my_leave,
		}

	def kv(rows):
		return {r["v"]: r["c"] for r in rows}

	job_status = kv(frappe.db.sql(f"select job_status v, count(*) c from {jo} group by job_status", as_dict=True))
	payment_status = kv(frappe.db.sql(f"select payment_status v, count(*) c from {jo} group by payment_status", as_dict=True))

	money_where = "docstatus=1" + (" AND YEAR(job_date)=YEAR(CURDATE())" if period == "year" else "")
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
		f"""select coalesce(it.item_name, jo.service, 'Unknown') label, count(*) value
		from {jo} jo left join `tabItem` it on it.name = jo.service
		where jo.docstatus = 1 group by label order by value desc limit 8""", as_dict=True,
	)
	by_month = frappe.db.sql(
		f"""select DATE_FORMAT(job_date, '%Y-%m') label, count(*) value from {jo}
		where job_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
		group by label order by label""", as_dict=True,
	)
	# Current workload = ACTIVE job orders held by ACTIVE employees (excludes
	# resigned/unlinked accountants so ex-staff don't appear).
	by_accountant = frappe.db.sql(
		f"""select e.employee_name label, count(*) value
		from {jo} jo
		inner join `tabEmployee` e on e.user_id = jo.accountant and e.status = 'Active'
		where jo.docstatus = 1 and jo.job_status in {ACTIVE_STATUSES}
		group by e.employee_name order by value desc limit 8""", as_dict=True,
	)
	# Data-hygiene: active jobs still assigned to non-active (resigned) staff.
	orphan_active = frappe.db.sql(
		f"""select count(*) from {jo} jo
		left join `tabEmployee` e on e.user_id = jo.accountant and e.status = 'Active'
		where jo.docstatus = 1 and jo.job_status in {ACTIVE_STATUSES} and e.name is null""",
	)[0][0]

	# Receivables aging (unpaid submitted job orders by invoice age)
	aging_rows = frappe.db.sql(
		f"""select case
			when datediff(curdate(), invoice_date) <= 30 then '0-30'
			when datediff(curdate(), invoice_date) <= 60 then '31-60'
			when datediff(curdate(), invoice_date) <= 90 then '61-90'
			else '90+' end bucket,
			count(*) n, round(sum(balance_amount)) amt
		from {jo} where docstatus=1 and balance_amount > 0 and invoice_date is not null
		group by bucket""", as_dict=True,
	)
	order = {"0-30": 0, "31-60": 1, "61-90": 2, "90+": 3}
	aging = sorted(aging_rows, key=lambda r: order.get(r["bucket"], 9))
	aging_total = sum(float(r["amt"] or 0) for r in aging)

	# Top customers by job count (+ revenue)
	top_customers = frappe.db.sql(
		f"""select c.customer_name label, count(*) value, round(sum(jo.invoiced_amount)) revenue
		from {jo} jo left join `tabCustomer` c on c.name = jo.customer
		where jo.docstatus=1 group by jo.customer order by value desc limit 6""", as_dict=True,
	)

	# Compliance snapshot (working-paper rule only applies to jobs created on/after the cutoff)
	WP_CUTOFF = "2026-05-07"
	sub_total = frappe.db.count("Job Order", {"docstatus": 1})
	wp_applicable = frappe.db.count("Job Order", {"job_status": "Finished", "creation": [">=", WP_CUTOFF]})
	wp_done = frappe.db.count("Job Order", {"job_status": "Finished", "creation": [">=", WP_CUTOFF], "audit_working_paper_created": 1})
	compliance = {
		"total": sub_total,
		"kyc": frappe.db.count("Job Order", {"docstatus": 1, "kyc_received": 1}),
		"loe": frappe.db.count("Job Order", {"docstatus": 1, "loe_received": 1}),
		"wp_applicable": wp_applicable, "wp_done": wp_done, "wp_pending": wp_applicable - wp_done,
	}

	# Average turnaround (finished jobs with a valid closure date)
	t = frappe.db.sql(
		f"""select round(avg(datediff(closure_date, job_date))) avg_days, count(*) n from {jo}
		where job_status='Finished' and closure_date is not null and closure_date >= job_date""", as_dict=True,
	)[0]
	turnaround = {"avg_days": t.avg_days or 0, "n": t.n or 0}

	proposals = {
		"total": frappe.db.count("Quotation"),
		"converted": frappe.db.count("Quotation", {"custom_job_order": ["is", "set"]}),
		"awaiting_acceptance": frappe.db.count("Quotation", {"custom_client_acceptance_type": "Not Confirmed"}),
		"awaiting_jo": frappe.db.count("Quotation", {"docstatus": 1, "custom_job_order": ["is", "not set"]}),
	}

	def recent(status):
		return frappe.db.sql(
			f"select name, customer, modified from {jo} where job_status=%s order by modified desc limit 5",
			(status,), as_dict=True,
		)

	counts = {
		"job_orders": frappe.db.count("Job Order"),
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
		"compliance": compliance, "turnaround": turnaround,
		"recent": {"open": recent("Open"), "progress": recent("Progress"), "finished": recent("Finished")},
	}
