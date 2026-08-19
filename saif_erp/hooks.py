app_name = "saif_erp"
app_title = "SAIF ERP"
app_publisher = "SGA World FZ LLC"
app_description = "SGA/SAIF custom app: Job Order, Proposals, HR, reports and dashboards"
app_email = "santhosh@saifaudit.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "saif_erp",
# 		"logo": "/assets/saif_erp/logo.png",
# 		"title": "SAIF ERP",
# 		"route": "/saif_erp",
# 		"has_permission": "saif_erp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/saif_erp/css/saif_erp.css"
# desk-load alert for expired / expiring / missing employee documents (HR/mgmt only)
app_include_js = "doc_expiry_alert.bundle.js"

# add the document-expiry alert counts to the desk boot for eligible users
boot_session = "saif_erp.boot.boot_session"

# include js, css files in header of web template
# web_include_css = "/assets/saif_erp/css/saif_erp.css"
# web_include_js = "/assets/saif_erp/js/saif_erp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "saif_erp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "saif_erp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "saif_erp.utils.jinja_methods",
# 	"filters": "saif_erp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "saif_erp.install.before_install"
# after_install = "saif_erp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "saif_erp.uninstall.before_uninstall"
# after_uninstall = "saif_erp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "saif_erp.utils.before_app_install"
# after_app_install = "saif_erp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "saif_erp.utils.before_app_uninstall"
# after_app_uninstall = "saif_erp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "saif_erp.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "saif_erp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# Monthly Job Order reports: 06:00 on the 1st, covering the previous month.
# Dormant on the local bench (scheduler + email are off); fires on production.
scheduler_events = {
	# Document-expiry + compliance-deadline reminders (email HR/accountant 30/15/7 days ahead).
	"daily": [
		"saif_erp.document_expiry.notify_document_expiry",
		"saif_erp.compliance.generate_forward_periods",
		"saif_erp.compliance.notify_compliance_deadlines",
		# Zoho Books -> Job Order invoice sync (opt-in via zoho_books.auto_sync)
		"saif_erp.zoho_books.scheduled_sync",
	],
	"cron": {
		"0 6 1 * *": [
			"saif_erp.monthly_report_pdf.send_monthly_reports"
		]
	}
}

# Testing
# -------

# before_tests = "saif_erp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "saif_erp.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "saif_erp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "saif_erp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["saif_erp.utils.before_request"]
# after_request = ["saif_erp.utils.after_request"]

# Job Events
# ----------
# before_job = ["saif_erp.utils.before_job"]
# after_job = ["saif_erp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"saif_erp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []



# ------------------------------------------------------------------
# SAIF ERP — Job Order redesign
# ------------------------------------------------------------------

# Business logic ported from DB Server Scripts into app code
doc_events = {
	"Job Order": {
		"validate": "saif_erp.job_order.enforce_review",
		"before_update_after_submit": "saif_erp.job_order.enforce_review",
		"on_update": [
			"saif_erp.job_order.sync_approval_status",
			"saif_erp.compliance.sync_job_order",
			"saif_erp.job_order.compute_stage",
		],
		"on_update_after_submit": [
			"saif_erp.job_order.sync_approval_status",
			"saif_erp.compliance.sync_job_order",
			"saif_erp.job_order.compute_stage",
		],
	},
}

# Row-level security: a plain Job Order Accountant only sees the Credential Manager
# records assigned to them; management roles see all. (See credential_manager.py.)
permission_query_conditions = {
	"Credential Manager": "saif_erp.credential_manager.get_permission_query_conditions",
}
has_permission = {
	"Credential Manager": "saif_erp.credential_manager.has_permission",
}

# Migratable customizations (exported via `bench export-fixtures`)
fixtures = [
	{"doctype": "Workflow", "filters": [["name", "=", "Job Order Approval"]]},
	{"doctype": "Workflow State", "filters": [["name", "in", ["Draft", "Pending Approval", "Approved", "Rejected"]]]},
	{"doctype": "Workflow Action Master", "filters": [["name", "in", ["Request Approval", "Approve", "Reject"]]]},
	{"doctype": "Custom Field", "filters": [["name", "in", [
		"Job Order-workflow_state", "Job Order-custom_review_sb", "Job Order-custom_reviewer_rating",
		"Job Order-custom_review_remark", "Job Order-custom_reviewed_by", "Job Order-custom_review_date",
		# progress / stage tracking
		"Job Order-custom_progress_sb", "Job Order-custom_stage", "Job Order-custom_progress",
		"Job Order-custom_progress_cb", "Job Order-draft_sent_date", "Job Order-draft_sent_by",
		"Job Order-draft_approved_date", "Job Order-custom_progress_html", "Job Order-tab_billing",
		# 2/3-column layout breaks
		"Job Order-cb_customer", "Job Order-cb_service", "Job Order-cb_service2",
		"Job Order-cb_compliance", "Job Order-cb_billing", "Job Order-cb_billing2",
		"Job Order-cb_delivery", "Job Order-cb_delivery2", "Job Order-cb_transfer",
	]]]},
	{"doctype": "Client Script", "filters": [["name", "in", [
		"Job Order - Reviewer Rating Access",
		"Job Order - Progress Checklist",
		"JB button in quotation and hide create sales order"]]]},
	{"doctype": "Property Setter", "filters": [["doc_type", "=", "Job Order"], ["field_name", "=", "job_status"], ["property", "=", "options"]]},
	{"doctype": "Property Setter", "filters": [["doc_type", "=", "Credential Manager"], ["field_name", "=", "portal_password"], ["property", "=", "fieldtype"]]},
	# SAIF dashboard — number cards (extended per redesign step)
	{"doctype": "Number Card", "filters": [["name", "in", [
		# Job Order
		"Approval Waiting Job Orders", "Total Open Job Orders", "Total Progress Job Orders",
		"Total Pending Job Orders", "Total Data Waiting Job Orders", "Total Temporary Stopped Job Orders",
		"Paid", "Payment status Partial", "Payment status Pending", "Payment status Hold Despute",
		# Proposal / Quotation
		"Total Proposals", "Proposal to JB", "Proposal waiting for client approval", "waiting for Job Order",
		# Leave (custom SAIF cards; Attendance + Employees-on-Leave are HRMS defaults, not shipped)
		"Leave Application", "Leave Application -Total2", "Leave Application-Rejected",
	]]]},
	# SAIF dashboard workspaces
	{"doctype": "Workspace", "filters": [["name", "in", ["Admin Dash", "Job Orders", "SGA Reports"]]]},
	# Redesigned workflow email notifications (branded HTML, guarded Jinja)
	{"doctype": "Notification", "filters": [["name", "in", [
		"New Job Order Created – Approval Required | {{ doc.name }}",
		"Notification Settings (Approved → email to Accountant)",
		"Quotation Submitted Alert",
		"attendance-request-notification",
		"Attendance Request Approval",
		"Job Order Reassigned – New Accountant",
		"Job Order Rejected – Preparer Alert",
		"Job Order Under Review – Reviewer Alert",
	]]]},
	{"doctype": "Email Template", "filters": [["name", "in", [
		"Leave Approval – Action Required",
		"Leave Status Update – Employee Notification",
	]]]},
]
