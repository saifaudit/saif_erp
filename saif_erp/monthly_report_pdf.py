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
from frappe.utils import flt, fmt_money, get_first_day, getdate, nowdate

from saif_erp.saif_erp.report.sga_monthly_job_order_report import (
	sga_monthly_job_order_report as R,
)

BRAND = "#155636"
ACCENT = "#3DB54A"

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


def _stars(n):
	return "★" * int(n) + "☆" * (5 - int(n))


def _leaderboard(frm, to):
	"""Team rating table for the admin (all-staff) PDF."""
	ratings = R.compute_team_ratings(frm, to)
	if not ratings:
		return ""
	# resolve user_id -> (name, company)
	emap = {}
	emps = frappe.get_all(
		"Employee", filters={"user_id": ["in", list(ratings)]},
		fields=["user_id", "employee_name", "company"],
	)
	for e in emps:
		emap[e.user_id] = (e.employee_name, e.company or "")
	ranked = sorted(ratings.items(), key=lambda kv: kv[1]["rank"])
	trs = []
	for uid, m in ranked:
		name, company = emap.get(uid, (uid, ""))
		turn = m["avg_turn"] if m["avg_turn"] is not None else "—"
		trs.append(
			"<tr><td class='num'>%d</td><td>%s</td><td class='co2'>%s</td>"
			"<td class='num'>%d</td><td class='num'>%d</td><td class='num'>%s</td>"
			"<td class='num'>%s</td><td class='num'>%d</td><td class='st'>%s</td></tr>"
			% (m["rank"], _esc(name), _esc(company), m["volume"], m["finished"],
			   turn, fmt_money(m["invoiced"]), m["score"], _stars(m["stars"]))
		)
	return (
		"<div class='lb'><div class='lbt'>Team Rating — this month "
		"<span class='lbn'>(Volume 30% · Invoiced 30% · Finished 25% · Speed 15%, relative to team)</span></div>"
		"<table class='lbtab'><thead><tr>"
		"<th>#</th><th>Employee</th><th>Company</th><th>Works</th><th>Finished</th>"
		"<th>Turn (d)</th><th>Invoiced</th><th>Score</th><th>Rating</th>"
		"</tr></thead><tbody>" + "".join(trs) + "</tbody></table></div>"
	)


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
			else:
				tds.append("<td>%s</td>" % _esc(v))
		body_rows.append("<tr>%s</tr>" % "".join(tds))
	body = "".join(body_rows) or (
		"<tr><td colspan='%d' class='empty'>No job orders in this period.</td></tr>" % len(PRINT_COLS)
	)

	# admin (all-staff) view gets a team rating leaderboard
	leaderboard = "" if employee else _leaderboard(frm, to)

	generated = getdate(nowdate()).strftime("%d %b %Y")
	return f"""<!doctype html><html><head><meta charset="utf-8">
<title>SGA Job Order Report — {_esc(who)}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         color: #222; margin: 0; padding: 18px; font-size: 12px; }}
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-end;
         border-bottom: 3px solid {BRAND}; padding-bottom: 10px; margin-bottom: 14px; gap:16px; }}
  .hdr .brand {{ display:flex; align-items:center; gap:12px; }}
  .hdr .brand img {{ height: 50px; width:auto; }}
  .hdr .brand .o1 {{ font-size:15px; font-weight:800; color:{BRAND}; letter-spacing:.2px; }}
  .hdr .brand .o2 {{ font-size:12px; font-weight:600; color:{ACCENT}; margin-top:2px; }}
  .hdr .who {{ text-align:right; }}
  .hdr .who .tag {{ font-size: 10px; font-weight:700; letter-spacing:1.2px;
        text-transform:uppercase; color:{ACCENT}; }}
  .hdr .who .name {{ font-size: 17px; font-weight:800; color:#111; margin-top:1px; }}
  .hdr .who .co {{ font-size: 11.5px; color:{BRAND}; font-weight:600; margin-top:1px; }}
  .hdr .who .per {{ font-size: 11.5px; color:#555; margin-top:3px; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }}
  .card {{ flex:1 1 120px; border:1px solid #e2e2e2; border-left:4px solid {ACCENT};
          border-radius:6px; padding:8px 10px; background:#fafdfb; }}
  .card .cv {{ font-size:17px; font-weight:800; color:{BRAND}; }}
  .card .cl {{ font-size:10.5px; color:#666; margin-top:2px; text-transform:uppercase; letter-spacing:.3px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ background:{BRAND}; color:#fff; text-align:left; padding:6px 7px; font-size:11px;
        font-weight:600; }}
  td {{ padding:5px 7px; border-bottom:1px solid #ececec; font-size:11px; vertical-align:top; }}
  tr:nth-child(even) td {{ background:#f7faf8; }}
  td.num {{ text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; }}
  td.cf {{ color:#C0902F; font-weight:700; }}
  td.empty {{ text-align:center; color:#888; padding:24px; }}
  .foot {{ margin-top:14px; font-size:10px; color:#999; text-align:right; }}
  .lb {{ margin-bottom:16px; }}
  .lb .lbt {{ font-size:13px; font-weight:800; color:{BRAND}; margin-bottom:6px; }}
  .lb .lbn {{ font-size:9.5px; font-weight:500; color:#888; letter-spacing:0; }}
  .lbtab td.co2 {{ color:#555; font-size:10px; }}
  .lbtab td.st {{ color:#C0902F; letter-spacing:1px; white-space:nowrap; }}
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
  <div class="cards">{cards}</div>
  {leaderboard}
  <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
  <div class="foot">Generated {generated} · SAIF ERP</div>
</body></html>"""


@frappe.whitelist()
def preview(employee=None, from_date=None, to_date=None):
	"""Return standalone HTML; the report button opens it in a new tab to print."""
	return render_html(employee, from_date, to_date)


@frappe.whitelist()
def email_pdf(employee=None, from_date=None, to_date=None):
	"""Server-rendered PDF bytes (needs wkhtmltopdf/Chrome — present on production)."""
	from frappe.utils.pdf import get_pdf

	html = render_html(employee, from_date, to_date)
	return get_pdf(html, options={"orientation": "Landscape"})
