# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Branded, print-ready HTML for the SGA Monthly Job Order Report.

One renderer feeds two paths:
  * preview()  -> returns standalone HTML; the report button opens it in a new
                  tab so the user can Ctrl+P -> Save as PDF (no server PDF engine
                  needed, so it works on the local bench too).
  * email_pdf()-> wraps the same HTML with frappe.utils.pdf.get_pdf for the
                  monthly auto-email attachment on production (wkhtmltopdf there).
"""

import os

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, fmt_money, get_first_day, getdate, nowdate

from saif_erp.saif_erp.report.sga_monthly_job_order_report import (
	sga_monthly_job_order_report as R,
)

# restrained, professional palette (shared with the on-screen report)
BRAND = R.C_GREEN       # deep green — headings, numbers, table header
ACCENT = "#2E7D50"      # muted green — thin accents
INK = "#24302A"
MUTED = R.C_MUTED
LINE = R.C_LINE
TINT = R.C_TINT
GOLD = R.C_GOLD

ORG_NAMES = ("SGA World Auditing Accounting LLC SPC", "Saif Chartered Accountants")

_LOGO = None


def _logo_data_uri():
	"""The green hex logo as a base64 data URI — self-contained so it renders
	in the browser print view and in the server-side PDF without a URL."""
	global _LOGO
	if _LOGO is None:
		import base64

		path = os.path.join(os.path.dirname(__file__), "public", "images", "sga-logo.png")
		try:
			with open(path, "rb") as fh:
				_LOGO = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
		except OSError:
			_LOGO = ""
	return _LOGO

# columns shown on the printed sheet (trimmed from the 14 on-screen columns)
PRINT_COLS = [
	("job_order", "Job Order"),
	("customer", "Customer"),
	("service", "Service"),
	("job_status", "Status"),
	("reviewer_rating", "Review"),
	("job_date", "Job Date"),
	("aging", "Aging"),
	("carry_forward", "C/F"),
	("other_accountants", "Collaborators"),
	("proposed_amount", "Proposed"),
	("invoiced_amount", "Invoiced"),
	("paid_amount", "Paid"),
]
MONEY = {"proposed_amount", "invoiced_amount", "paid_amount"}


def _period(from_date, to_date):
	from_date = from_date or get_first_day(nowdate())
	to_date = to_date or nowdate()
	return getdate(from_date), getdate(to_date)


def _who_and_company(employee):
	"""Return (display name, company) for the report subject."""
	if employee:
		name, company = frappe.db.get_value(
			"Employee", employee, ["employee_name", "company"]
		) or (employee, None)
		return name or employee, company or ""
	return _("All Staff"), _("All Entities")


def _esc(v):
	return frappe.utils.escape_html("" if v is None else str(v))


def render_html(employee=None, from_date=None, to_date=None):
	frm, to = _period(from_date, to_date)
	filters = frappe._dict({"from_date": frm, "to_date": to})
	if employee:
		filters.employee = employee
	rows, summary, _chart, _msg = R.get_data(filters)

	who, company = _who_and_company(employee)
	period_lbl = "%s  —  %s" % (frm.strftime("%d %b %Y"), to.strftime("%d %b %Y"))

	# summary cards
	cards = "".join(
		"<div class='card'><div class='cv'>%s</div><div class='cl'>%s</div></div>"
		% (
			(fmt_money(c["value"]) if c.get("datatype") == "Currency" else _esc(c["value"])),
			_esc(c["label"]),
		)
		for c in summary
	)

	# table
	head = "".join("<th>%s</th>" % _esc(lbl) for _f, lbl in PRINT_COLS)
	body_rows = []
	for r in rows:
		tds = []
		for f, _lbl in PRINT_COLS:
			v = r.get(f)
			if f in MONEY:
				cell = fmt_money(flt(v))
				tds.append("<td class='num'>%s</td>" % cell)
			elif f == "carry_forward":
				cls = "cf" if v == "Yes" else ""
				tds.append("<td class='%s'>%s</td>" % (cls, _esc(v)))
			elif f == "reviewer_rating":
				stars = R.star_html(round(flt(v) * 5), 11) if v else "<span style='color:#bbb'>—</span>"
				tds.append("<td style='white-space:nowrap'>%s</td>" % stars)
			else:
				tds.append("<td>%s</td>" % _esc(v))
		body_rows.append("<tr>%s</tr>" % "".join(tds))
	body = "".join(body_rows) or (
		"<tr><td colspan='%d' class='empty'>No job orders in this period.</td></tr>" % len(PRINT_COLS)
	)

	# rating: single employee → badge (rank only for managers); admin → leaderboard
	is_mgr = bool(R.MGMT_ROLES & set(frappe.get_roles()))
	ratings = R.compute_team_ratings(frm, to)
	rating_block = ""
	if employee:
		uid = frappe.db.get_value("Employee", employee, "user_id")
		if uid and ratings.get(uid):
			rating_block = ("<div class='rate'>%s</div>"
			                % R.rating_badge_html(ratings[uid], show_rank=is_mgr))
	elif is_mgr:
		lb = R.leaderboard_html(ratings)
		rating_block = ("<div class='lb'>%s</div>" % lb) if lb else ""

	generated = getdate(nowdate()).strftime("%d %b %Y")
	return f"""<!doctype html><html><head><meta charset="utf-8">
<title>SGA Job Order Report — {_esc(who)}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         color: {INK}; margin: 0; padding: 18px; font-size: 12px; }}
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-end;
         border-bottom: 2px solid {BRAND}; padding-bottom: 10px; margin-bottom: 14px; gap:16px; }}
  .hdr .brand {{ display:flex; align-items:center; gap:12px; }}
  .hdr .brand img {{ height: 48px; width:auto; }}
  .hdr .brand .o1 {{ font-size:15px; font-weight:800; color:{BRAND}; letter-spacing:.2px; }}
  .hdr .brand .o2 {{ font-size:11.5px; font-weight:600; color:{MUTED}; margin-top:2px; }}
  .hdr .who {{ text-align:right; }}
  .hdr .who .tag {{ font-size: 10px; font-weight:700; letter-spacing:1.4px;
        text-transform:uppercase; color:{MUTED}; }}
  .hdr .who .name {{ font-size: 17px; font-weight:800; color:{INK}; margin-top:2px; }}
  .hdr .who .co {{ font-size: 11.5px; color:{BRAND}; font-weight:600; margin-top:1px; }}
  .hdr .who .per {{ font-size: 11.5px; color:{MUTED}; margin-top:3px; }}
  .rate {{ margin-bottom:14px; }}
  .lb {{ margin-bottom:16px; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .card {{ flex:1 1 118px; border:1px solid {LINE}; border-radius:8px;
          padding:9px 11px; background:#fff; }}
  .card .cv {{ font-size:18px; font-weight:800; color:{BRAND}; font-variant-numeric:tabular-nums; }}
  .card .cl {{ font-size:9.5px; color:{MUTED}; margin-top:3px; text-transform:uppercase;
          letter-spacing:.4px; font-weight:600; }}
  table.jobs {{ width:100%; border-collapse:collapse; }}
  table.jobs th {{ background:{BRAND}; color:#fff; text-align:left; padding:7px 8px; font-size:10.5px;
        font-weight:600; letter-spacing:.2px; }}
  table.jobs td {{ padding:5px 8px; border-bottom:1px solid {LINE}; font-size:11px; vertical-align:top; }}
  table.jobs tbody tr:nth-child(even) td {{ background:{TINT}; }}
  table.jobs td.num {{ text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; }}
  table.jobs td.cf {{ color:{GOLD}; font-weight:700; }}
  table.jobs td.empty {{ text-align:center; color:{MUTED}; padding:24px; }}
  .foot {{ margin-top:14px; font-size:10px; color:{MUTED}; text-align:right;
          border-top:1px solid {LINE}; padding-top:8px; }}
  @media print {{ body {{ padding:0; }} .noprint {{ display:none; }} }}
</style></head><body>
  <div class="hdr">
    <div class="brand">
      <img src="{_logo_data_uri()}" alt="logo">
      <div><div class="o1">{_esc(ORG_NAMES[0])}</div>
        <div class="o2">{_esc(ORG_NAMES[1])}</div></div>
    </div>
    <div class="who">
      <div class="tag">Job Order Report</div>
      <div class="name">{_esc(who)}</div>
      <div class="co">{_esc(company)}</div>
      <div class="per">{_esc(period_lbl)}</div>
    </div>
  </div>
  {rating_block}
  <div class="cards">{cards}</div>
  <table class="jobs"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
  <div class="foot">Generated {generated} · SAIF ERP</div>
</body></html>"""


def render_table_page(title_tag, who, sub, summary, columns, data, compact=False):
	"""Branded landscape page for ANY tabular report (cards + table). Reused by
	the Attendance & Leave, Payroll and Monthly Attendance Sheet reports.
	compact=True shrinks cells for many-column sheets (e.g. day-by-day)."""
	NUM = {"Int", "Float", "Currency", "Percent"}
	cards = "".join(
		"<div class='card'><div class='cv'>%s</div><div class='cl'>%s</div></div>"
		% ((fmt_money(c["value"]) if c.get("datatype") == "Currency" else _esc(c["value"])), _esc(c["label"]))
		for c in (summary or [])
	)
	head = "".join(
		"<th style='text-align:%s'>%s</th>"
		% ("right" if c.get("fieldtype") in NUM else ("center" if c.get("align") == "center" else "left"),
		   _esc(c["label"]).replace("\n", "<br>"))
		for c in columns
	)
	SHEET = {"P": "#0E7A3B", "W": "#1F6FB2", "½": "#0E7A3B", "A": "#C0392B",
	         "L": "#C0902F", "S": "#9AA5A0", "H": "#7A6BB0"}
	body_rows = []
	for r in data:
		tds = []
		for c in columns:
			f, ft = c["fieldname"], c.get("fieldtype")
			v = r.get(f)
			if ft in NUM:
				cell = fmt_money(v) if ft == "Currency" else _esc(v)
				tds.append("<td class='num'>%s</td>" % cell)
			elif c.get("align") == "center":
				color = SHEET.get(v)
				sv = ("<b style='color:%s'>%s</b>" % (color, _esc(v))) if color else _esc(v)
				tds.append("<td style='text-align:center'>%s</td>" % sv)
			else:
				tds.append("<td>%s</td>" % _esc(v))
		body_rows.append("<tr>%s</tr>" % "".join(tds))
	body = "".join(body_rows) or ("<tr><td colspan='%d' class='empty'>No data.</td></tr>" % len(columns))
	cell_css = ("th{{padding:3px 2px;font-size:8px}} td{{padding:2px 2px;font-size:8.5px}}"
	            if compact else "th{{padding:7px 8px;font-size:10.5px}} td{{padding:5px 8px;font-size:11px}}")
	generated = getdate(nowdate()).strftime("%d %b %Y")
	return f"""<!doctype html><html><head><meta charset="utf-8">
<title>SGA {_esc(title_tag)} — {_esc(who)}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color:{INK};
         margin:0; padding:18px; font-size:12px; }}
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-end;
         border-bottom:2px solid {BRAND}; padding-bottom:10px; margin-bottom:14px; gap:16px; }}
  .hdr .brand {{ display:flex; align-items:center; gap:12px; }}
  .hdr .brand img {{ height:48px; width:auto; }}
  .hdr .brand .o1 {{ font-size:15px; font-weight:800; color:{BRAND}; }}
  .hdr .brand .o2 {{ font-size:11.5px; font-weight:600; color:{MUTED}; margin-top:2px; }}
  .hdr .who {{ text-align:right; }}
  .hdr .who .tag {{ font-size:10px; font-weight:700; letter-spacing:1.4px; text-transform:uppercase; color:{MUTED}; }}
  .hdr .who .name {{ font-size:17px; font-weight:800; color:{INK}; margin-top:2px; }}
  .hdr .who .per {{ font-size:11.5px; color:{MUTED}; margin-top:3px; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .card {{ flex:1 1 120px; border:1px solid {LINE}; border-radius:8px; padding:9px 11px; background:#fff; }}
  .card .cv {{ font-size:18px; font-weight:800; color:{BRAND}; font-variant-numeric:tabular-nums; }}
  .card .cl {{ font-size:9.5px; color:{MUTED}; margin-top:3px; text-transform:uppercase; letter-spacing:.4px; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ background:{BRAND}; color:#fff; font-weight:600; }}
  td {{ border-bottom:1px solid {LINE}; }}
  {cell_css}
  tbody tr:nth-child(even) td {{ background:{TINT}; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  td.empty {{ text-align:center; color:{MUTED}; padding:24px; }}
  .foot {{ margin-top:14px; font-size:10px; color:{MUTED}; text-align:right; border-top:1px solid {LINE}; padding-top:8px; }}
  @media print {{ body {{ padding:0; }} }}
</style></head><body>
  <div class="hdr">
    <div class="brand"><img src="{_logo_data_uri()}" alt="logo">
      <div><div class="o1">{_esc(ORG_NAMES[0])}</div><div class="o2">{_esc(ORG_NAMES[1])}</div></div>
    </div>
    <div class="who"><div class="tag">{_esc(title_tag)}</div>
      <div class="name">{_esc(who)}</div><div class="per">{_esc(sub)}</div></div>
  </div>
  <div class="cards">{cards}</div>
  <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
  <div class="foot">Generated {generated} · SAIF ERP</div>
</body></html>"""


@frappe.whitelist()
def attendance_preview(month=None, year=None, company=None, employee=None):
	"""Branded HTML for the Attendance & Leave report (opened for browser Save-as-PDF)."""
	from saif_erp.saif_erp.report.sga_attendance_and_leave import sga_attendance_and_leave as A

	f = {"month": month, "year": year, "company": company, "employee": employee}
	cols, data, _msg, _chart, summary = A.execute(f)
	who = _("All Staff")
	if employee:
		who = frappe.db.get_value("Employee", employee, "employee_name") or employee
	import calendar

	sub = "%s %s · %d staff" % (calendar.month_name[cint(month) or getdate(nowdate()).month],
	                            cint(year) or getdate(nowdate()).year, len(data))
	return render_table_page(_("Attendance & Leave"), who, sub, summary, cols, data)


@frappe.whitelist()
def attendance_sheet_preview(month=None, year=None, company=None, employee=None):
	"""Branded HTML for the day-by-day Monthly Attendance Sheet (compact)."""
	from saif_erp.saif_erp.report.sga_monthly_attendance_sheet import sga_monthly_attendance_sheet as S

	f = {"month": month, "year": year, "company": company, "employee": employee}
	cols, data, _msg, _chart, summary = S.execute(f)
	who = _("All Staff")
	if employee:
		who = frappe.db.get_value("Employee", employee, "employee_name") or employee
	import calendar

	sub = "%s %s · P present · A absent · L leave · W home · S week-off · H holiday" % (
		calendar.month_name[cint(month) or getdate(nowdate()).month], cint(year) or getdate(nowdate()).year)
	return render_table_page(_("Attendance Sheet"), who, sub, summary, cols, data, compact=True)


@frappe.whitelist()
def work_hours_preview(month=None, year=None, company=None, employee=None, min_hours=None):
	"""Branded HTML for the Work Hours Summary report."""
	from saif_erp.saif_erp.report.sga_work_hours_summary import sga_work_hours_summary as WH

	f = {"month": month, "year": year, "company": company, "employee": employee, "min_hours": min_hours}
	cols, data, _msg, _chart, summary = WH.execute(f)
	who = _("All Staff")
	if employee:
		who = frappe.db.get_value("Employee", employee, "employee_name") or employee
	import calendar

	sub = "%s %s · %d staff" % (calendar.month_name[cint(month) or getdate(nowdate()).month],
	                            cint(year) or getdate(nowdate()).year, len(data))
	return render_table_page(_("Work Hours"), who, sub, summary, cols, data)


@frappe.whitelist()
def payroll_preview(month=None, year=None, company=None, employee=None):
	"""Branded HTML for the Payroll Days Summary report."""
	from saif_erp.saif_erp.report.sga_payroll_days_summary import sga_payroll_days_summary as P

	f = {"month": month, "year": year, "company": company, "employee": employee}
	cols, data, _msg, _chart, summary = P.execute(f)
	who = _("All Staff")
	if employee:
		who = frappe.db.get_value("Employee", employee, "employee_name") or employee
	import calendar

	sub = "%s %s · %d staff" % (calendar.month_name[cint(month) or getdate(nowdate()).month],
	                            cint(year) or getdate(nowdate()).year, len(data))
	return render_table_page(_("Payroll Days"), who, sub, summary, cols, data)


@frappe.whitelist()
def preview(employee=None, from_date=None, to_date=None):
	"""Return standalone HTML; the report button opens it in a new tab to print."""
	return render_html(employee, from_date, to_date)


@frappe.whitelist()
def email_pdf(employee=None, from_date=None, to_date=None):
	"""Server-rendered PDF bytes (needs wkhtmltopdf/Chrome — present on production)."""
	return _pdf(employee, from_date, to_date)


# ---------------------------------------------------------------------------
# Monthly auto-email (scheduler hook, fires on production only)
# ---------------------------------------------------------------------------

# Default admin recipients; override on a site with
# `bench set-config saif_monthly_report_recipients '["a@x.com","b@y.com"]'`.
ADMIN_RECIPIENTS = ["santhosh@saifaudit.com"]

# A recipient must hold an accountant role. Management staff are excluded from the
# individual report (they get the all-staff admin report instead) via an explicit
# list — no roles are changed, so nobody's permissions/performance are affected.
RECIPIENT_ROLES = ["Job Order Accountant"]
MANAGEMENT_EXCLUDE = [
	"santhosh@saifaudit.com",   # Santhosh — gets the admin report
	"chandy@saifaudit.com",     # T K Chandy — CEO/Partner
	"info@saifaudit.com",       # Allysa Pancho Alorro — Admin Executive
]


def _users_with(roles):
	return set(frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent"))


def _accountant_users():
	"""Accountant-role users, minus management (who receive the admin report)."""
	incl = frappe.conf.get("saif_report_recipient_roles") or RECIPIENT_ROLES
	excl = frappe.conf.get("saif_report_management_exclude") or MANAGEMENT_EXCLUDE
	return _users_with(incl) - set(excl)


def _pdf(employee, from_date, to_date):
	from frappe.utils.pdf import get_pdf

	return get_pdf(render_html(employee, from_date, to_date), options={"orientation": "Landscape"})


def _prev_month():
	"""First and last day of the month before today."""
	last_prev = add_days(get_first_day(nowdate()), -1)
	return get_first_day(last_prev), last_prev


def _emp_email(e):
	return e.get("company_email") or e.get("user_id") or e.get("personal_email")


def _send(recipients, subject, intro, filename, pdf):
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=intro,
		attachments=[{"fname": filename, "fcontent": pdf}],
		reference_doctype="Report",
		reference_name="SGA Monthly Job Order Report",
	)


def send_monthly_reports(dry_run=False):
	"""Scheduled on the 1st: email the previous month's report — the all-staff
	PDF to the admins, and each active employee their own PDF. `dry_run` builds
	the HTML and lists recipients WITHOUT rendering PDFs or sending (so it can be
	checked on the local bench, which has no PDF engine and no outgoing email)."""
	dry_run = cint(dry_run)
	frm, to = _prev_month()
	label = frm.strftime("%B %Y")
	out = {"period": "%s → %s" % (frm, to), "label": label, "dry_run": bool(dry_run),
	       "admin": None, "staff": []}

	admins = frappe.conf.get("saif_monthly_report_recipients") or ADMIN_RECIPIENTS
	if admins:
		if dry_run:
			out["admin"] = {"to": admins, "html_bytes": len(render_html(None, frm, to))}
		else:
			_send(admins, "SAIF Job Order Report — %s (All Staff)" % label,
			      "<p>Attached is the all-staff Job Order report for <b>%s</b>.</p>" % label,
			      "Job Order Report - All Staff - %s.pdf" % label, _pdf(None, frm, to))
			out["admin"] = {"to": admins, "sent": True}

	acc_users = _accountant_users()
	emps = frappe.get_all(
		"Employee", filters={"status": "Active"},
		fields=["name", "employee_name", "user_id", "company_email", "personal_email"],
	)
	for e in emps:
		if e.user_id not in acc_users:  # only accountant-role staff get an email
			continue
		addr = _emp_email(e)
		if not addr or "@" not in addr:
			continue
		rows, _s, _c, _m = R.get_data(frappe._dict({"from_date": frm, "to_date": to, "employee": e.name}))
		if not rows:  # nothing to report this month — skip
			continue
		rec = {"employee": e.employee_name, "to": addr, "rows": len(rows)}
		if not dry_run:
			_send([addr], "Your Job Order Report — %s" % label,
			      "<p>Hi %s,</p><p>Attached is your Job Order report for <b>%s</b>.</p>"
			      % (frappe.utils.escape_html(e.employee_name), label),
			      "Job Order Report - %s - %s.pdf" % (e.employee_name, label),
			      _pdf(e.name, frm, to))
			rec["sent"] = True
		out["staff"].append(rec)
	return out


@frappe.whitelist()
def run_monthly_reports_now(dry_run=1):
	"""Manual trigger for admins to test on production (or dry-run anywhere)."""
	frappe.only_for("System Manager")
	return send_monthly_reports(dry_run=dry_run)
