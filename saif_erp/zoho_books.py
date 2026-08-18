# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Read-only Zoho Books -> Job Order invoice sync.

Pulls invoices from Zoho Books and updates the matching Job Order's invoice
header ONLY: invoice_number, invoice_date, invoiced_amount, paid_amount,
balance_amount, payment_status. It NEVER writes back to Zoho.

Zoho Books stays the accounting system of record; ERP keeps just enough to link
revenue to a Job Order (dashboards, ratings, receivables follow-up). Matching is
by the Job Order name/number carried on the Zoho invoice.

Setup lives entirely in per-site config, so the SAME code runs unchanged on the
live server — only the credentials + active scheduler differ. Configure via
`bench --site <site> set-config -g zoho_books '<json>'` or edit site_config.json
(NEVER commit credentials):

  "zoho_books": {
    "region": "com",                 # data centre: com | sa | eu | in | com.au | jp
    "organization_id": "8600000...",
    "client_id": "1000...",
    "client_secret": "....",
    "refresh_token": "1000....",     # obtained once, see get_refresh_token()
    "jo_field": "reference_number",  # where the JO number sits on the invoice
    "jo_pattern": "JOB-\\d{4}-\\d+", # regex to pull the JO number out of that field
    "preserve_hold": 1               # don't auto-clear a manual "Hold / Dispute"
  }
"""

import re

import frappe
from frappe.utils import flt, getdate

# ---- Zoho invoice status -> our Job Order payment_status --------------------
STATUS_MAP = {
	"paid": "Paid",
	"partially_paid": "Partial Payment",
	"sent": "Not Paid",
	"overdue": "Not Paid",
	"unpaid": "Not Paid",
	"viewed": "Not Paid",
}
# Not-yet-finalised / dead invoices are NOT synced at all — a draft isn't a real
# invoice and must never overwrite a Job Order's manually-entered figures.
SKIP_STATUSES = {"draft", "void", "written_off"}
# Job Order fields this sync is allowed to touch — nothing else.
SYNCED_FIELDS = ("invoice_number", "invoice_date", "invoiced_amount",
                 "paid_amount", "balance_amount", "payment_status")


def _conf():
	c = frappe.conf.get("zoho_books")
	if not c:
		frappe.throw("Zoho Books is not configured (site_config key 'zoho_books').")
	return c


def _dc(region):
	"""Regional Zoho domains. UAE accounts are usually 'com' or 'sa'."""
	region = (region or "com").lstrip(".")
	return (f"https://accounts.zoho.{region}", f"https://www.zohoapis.{region}")


# ---- OAuth (server-to-server "Self Client") --------------------------------
def get_refresh_token(grant_token, region=None, client_id=None, client_secret=None):
	"""ONE-TIME: exchange a short-lived Self-Client grant token for a permanent
	refresh token. Run once (System Manager), then store the returned refresh
	token in site_config. Grant tokens expire in minutes — generate & use fast."""
	import requests

	c = frappe.conf.get("zoho_books") or {}
	region = region or c.get("region", "com")
	client_id = client_id or c.get("client_id")
	client_secret = client_secret or c.get("client_secret")
	accounts, _ = _dc(region)
	r = requests.post(f"{accounts}/oauth/v2/token", params={
		"grant_type": "authorization_code",
		"client_id": client_id,
		"client_secret": client_secret,
		"code": grant_token,
	}, timeout=30)
	data = r.json()
	if not data.get("refresh_token"):
		frappe.throw(f"Zoho did not return a refresh token: {data}")
	return data  # contains refresh_token — copy it into site_config, do NOT log


def _access_token():
	"""Fetch a short-lived access token from the stored refresh token, cached
	~55 min so we don't re-mint on every call."""
	import requests

	cached = frappe.cache().get_value("zoho_books_access_token")
	if cached:
		return cached
	c = _conf()
	accounts, _ = _dc(c.get("region"))
	r = requests.post(f"{accounts}/oauth/v2/token", params={
		"grant_type": "refresh_token",
		"refresh_token": c["refresh_token"],
		"client_id": c["client_id"],
		"client_secret": c["client_secret"],
	}, timeout=30)
	tok = r.json().get("access_token")
	if not tok:
		frappe.throw(f"Zoho token refresh failed: {r.json()}")
	frappe.cache().set_value("zoho_books_access_token", tok, expires_in_sec=3300)
	return tok


def _api_get(path, params=None):
	import requests

	c = _conf()
	_, api = _dc(c.get("region"))
	params = dict(params or {})
	params["organization_id"] = c["organization_id"]
	r = requests.get(f"{api}/books/v3{path}",
	                 headers={"Authorization": f"Zoho-oauthtoken {_access_token()}"},
	                 params=params, timeout=60)
	r.raise_for_status()
	return r.json()


def list_organizations():
	"""Helper for setup — find your organization_id."""
	return _api_get("/organizations").get("organizations", [])


def fetch_invoices(modified_since=None, max_pages=50):
	"""Pull invoices (list view has header totals + balance + status), paginated.
	`modified_since` (YYYY-MM-DD) limits to recently-changed invoices for the
	daily incremental sync."""
	out, page = [], 1
	while page <= max_pages:
		params = {"page": page, "per_page": 200}
		if modified_since:
			params["last_modified_time"] = str(modified_since)
		data = _api_get("/invoices", params)
		out.extend(data.get("invoices", []))
		if not data.get("page_context", {}).get("has_more_page"):
			break
		page += 1
	return out


# ---- matching + mapping (pure, unit-testable) ------------------------------
def extract_jo(inv, jo_field="reference_number", jo_pattern=None):
	"""Find the Job Order number on a Zoho invoice. Looks at the configured
	field first, then custom fields / reference / notes, then applies the
	optional regex to isolate the JO code from surrounding text."""
	candidates = []
	if inv.get(jo_field):
		candidates.append(str(inv[jo_field]))
	candidates.append(str(inv.get("reference_number") or ""))
	for cf in inv.get("custom_fields", []) or []:
		if cf.get("value"):
			candidates.append(str(cf["value"]))
	candidates.append(str(inv.get("notes") or ""))
	for val in candidates:
		val = val.strip()
		if not val:
			continue
		if jo_pattern:
			m = re.search(jo_pattern, val, re.I)
			if m:
				return m.group(0).upper()
		elif val:
			return val
	return None


def map_status(zoho_status):
	return STATUS_MAP.get((zoho_status or "").lower())


def _invoice_values(inv):
	"""The invoice-header values we mirror onto the Job Order."""
	total = flt(inv.get("total"))
	balance = flt(inv.get("balance"))
	return {
		"invoice_number": inv.get("invoice_number"),
		"invoice_date": getdate(inv["date"]) if inv.get("date") else None,
		"invoiced_amount": total,
		"paid_amount": round(total - balance, 2),
		"balance_amount": balance,
		"payment_status": map_status(inv.get("status")),
	}


# ---- the sync ---------------------------------------------------------------
def sync_invoices(dry_run=True, modified_since=None, invoices=None):
	"""Pull Zoho invoices, match to Job Orders by JO number, and update the
	invoice header. Returns a summary + per-row change list. `dry_run=True`
	(default) computes changes but writes NOTHING. `invoices` may be injected
	(list of dicts) to test matching/mapping without a live connection."""
	c = frappe.conf.get("zoho_books") or {}
	jo_field = c.get("jo_field", "reference_number")
	jo_pattern = c.get("jo_pattern")
	preserve_hold = c.get("preserve_hold", 1)

	if invoices is None:
		invoices = fetch_invoices(modified_since=modified_since)

	changes, unmatched, skipped, draft_skipped = [], [], 0, 0
	for inv in invoices:
		if (inv.get("status") or "").lower() in SKIP_STATUSES:
			draft_skipped += 1   # draft/void/written-off never overwrite ERP figures
			continue
		jo = extract_jo(inv, jo_field, jo_pattern)
		if not jo or not frappe.db.exists("Job Order", jo):
			unmatched.append({"invoice": inv.get("invoice_number"),
			                  "zoho_ref": inv.get("reference_number"), "jo": jo})
			continue
		cur = frappe.db.get_value("Job Order", jo, SYNCED_FIELDS, as_dict=True)
		new = _invoice_values(inv)
		if new["payment_status"] is None:
			new["payment_status"] = cur.payment_status  # unknown status -> leave as-is
		if preserve_hold and cur.payment_status == "Hold / Dispute":
			new["payment_status"] = "Hold / Dispute"    # never auto-clear a manual hold
		diff = {f: new[f] for f in SYNCED_FIELDS
		        if str(cur.get(f) or "") != str(new[f] or "")}
		if not diff:
			skipped += 1
			continue
		changes.append({"job_order": jo, "invoice": inv.get("invoice_number"),
		                "diff": diff})
		if not dry_run:
			for f, v in diff.items():
				frappe.db.set_value("Job Order", jo, f, v, update_modified=False)

	if not dry_run and changes:
		frappe.db.commit()

	summary = {"mode": "DRY-RUN" if dry_run else "APPLIED",
	           "pulled": len(invoices), "changed": len(changes),
	           "unchanged": skipped, "unmatched": len(unmatched),
	           "draft_skipped": draft_skipped}
	return {"summary": summary, "changes": changes, "unmatched": unmatched}


# ---- triggers ---------------------------------------------------------------
@frappe.whitelist()
def zoho_sync_now(dry_run=1, modified_since=None):
	"""Manual trigger (System Manager). dry_run=1 previews, dry_run=0 applies."""
	frappe.only_for(("System Manager", "Job Order Admin", "Job Order Partner"))
	return sync_invoices(dry_run=int(dry_run), modified_since=modified_since)


def scheduled_sync():
	"""Daily incremental sync (applies changes). Opt-in: only runs when
	`zoho_books.auto_sync` is set, so configuring credentials for manual
	dry-run testing does NOT start auto-writing. Dormant on the local bench
	(scheduler paused); fires on production once enabled."""
	c = frappe.conf.get("zoho_books")
	if not c or not c.get("auto_sync"):
		return
	from frappe.utils import add_days, nowdate
	res = sync_invoices(dry_run=False, modified_since=add_days(nowdate(), -3))
	frappe.logger("zoho_books").info(res["summary"])
