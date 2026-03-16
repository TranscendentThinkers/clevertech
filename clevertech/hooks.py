app_name = "clevertech"
app_title = "Clevertech"
app_publisher = "Bharatbodh"
app_description = "Clevertech"
app_email = "saket.vaidya@transcendent.co.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "clevertech",
# 		"logo": "/assets/clevertech/logo.png",
# 		"title": "Clevertech",
# 		"route": "/clevertech",
# 		"has_permission": "clevertech.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/clevertech/css/clevertech.css"
# app_include_js = "/assets/clevertech/js/clevertech.js"

# include js, css files in header of web template
# web_include_css = "/assets/clevertech/css/clevertech.css"
# web_include_js = "/assets/clevertech/js/clevertech.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "clevertech/public/scss/website"

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
# app_include_icons = "clevertech/public/icons.svg"

# Home Pages
# ----------
doc_events = {
        "Quality Inspection": {
            "validate":"clevertech.server_scripts.quality_inspection.validate",
            "on_submit":"clevertech.server_scripts.quality_inspection.on_submit",
            "before_insert":"clevertech.server_scripts.quality_inspection.before_validate",
        },
        "Item": {
            "before_validate":"clevertech.server_scripts.item.before_validate"
        },
        "Purchase Receipt": {
            "on_submit": [
                "clevertech.server_scripts.purchase_receipt.on_submit",
                "clevertech.project_component_master.procurement_hooks.on_pr_submit",
            ],
#            "before_validate": "clevertech.server_scripts.purchase_receipt.before_validate",
            "before_submit":"clevertech.server_scripts.purchase_receipt.before_submit",
            "on_cancel": "clevertech.project_component_master.procurement_hooks.on_pr_cancel",
        },
        "Purchase Order": {
#            "before_validate": "clevertech.server_scripts.purchase_order.before_validate",
            "validate": [
                "clevertech.supply_chain.server_scripts.purchase_order.validate",
                "clevertech.project_component_master.purchase_order_validation.validate_purchase_order_qty",
            ],
            "on_submit": "clevertech.project_component_master.procurement_hooks.on_po_submit",
            "on_cancel": [
                "clevertech.supply_chain.server_scripts.purchase_order.on_cancel",
                "clevertech.project_component_master.procurement_hooks.on_po_cancel",
            ],
        },
        "Material Request": {
            "before_validate": "clevertech.server_scripts.material_request.before_validate",
            "validate": [
                "clevertech.server_scripts.material_request_validate.validate",
                "clevertech.project_component_master.material_request_validation.validate_material_request_qty",
            ],
            "on_submit": "clevertech.project_component_master.procurement_hooks.on_mr_submit",
            "on_cancel": "clevertech.project_component_master.procurement_hooks.on_mr_cancel",
            "before_save": "clevertech.server_scripts.material_request.set_default_warehouses_from_item_defaults"
        },
        "BOM": {
            "before_insert": "clevertech.design.server_scripts.bom.before_insert",
            "validate": "clevertech.project_component_master.bom_hooks.on_bom_validate",
            "on_submit": "clevertech.project_component_master.bom_hooks.on_bom_submit",
            "on_cancel": "clevertech.project_component_master.bom_hooks.on_bom_cancel",
            "on_update_after_submit": "clevertech.project_component_master.bom_hooks.on_bom_update"
        },
        "Request for Quotation": {
           # "before_save": "clevertech.server_scripts.request_for_quotation.before_save",
            "validate": [
                "clevertech.supply_chain.server_scripts.request_for_quotation.validate",
                "clevertech.project_component_master.rfq_validation.validate_rfq_qty",
            ],
            "on_submit": "clevertech.project_component_master.procurement_hooks.on_rfq_submit",
            "on_cancel": "clevertech.project_component_master.procurement_hooks.on_rfq_cancel",
        },
        "Supplier Quotation": {
            "validate":"clevertech.supply_chain.server_scripts.supplier_quotation.validate",
          #  "before_submit":"clevertech.supply_chain.server_scripts.supplier_quotation.before_submit",
        },
        "Sales Invoice": {
            "before_validate": "clevertech.server_scripts.sales_invoice.before_validate",
        },
}
doctype_js = {
        "Material Request":"public/js/material_request.js",
        "Request for Quotation":"public/js/request_for_quotation.js",
        "Supplier Quotation":"public/js/supplier_quotation.js",
        "Purchase Order":"public/js/purchase_order.js",
        "Purchase Receipt":"public/js/purchase_receipt.js",
        "Project":"public/js/project.js",
        "Item":"public/js/item_update.js",
        
}
fixtures = [
    {
        "doctype": "Workflow State"
    },
    {
        "doctype": "Workflow Action Master"
    },
    {
        "doctype": "Workflow",
        "filters": [
            ["name", "=", "SQC Approval Workflow Without Conditions"]
        ]
    },
    {
        "doctype": "Letter Head",
        "filters": [
            ["name","in",["Clevertech Letter Head","QC Letter Head"]]
        ]
    },
    {
        "doctype": "Email Template",
        "filters": [
            ["name", "=", "Request for Quotation"]
        ]
    }
]
#doctype_list_js = {
#        "Item":"public/js/item_list.js",
#}




#app_include_js = "/assets/clevertech/js/row_highlight.js"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "clevertech.utils.jinja_methods",
# 	"filters": "clevertech.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "clevertech.install.before_install"
# after_install = "clevertech.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "clevertech.uninstall.before_uninstall"
# after_uninstall = "clevertech.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "clevertech.utils.before_app_install"
# after_app_install = "clevertech.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "clevertech.utils.before_app_uninstall"
# after_app_uninstall = "clevertech.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "clevertech.notifications.get_notification_config"

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

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
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

# scheduler_events = {
# 	"all": [
# 		"clevertech.tasks.all"
# 	],
# 	"daily": [
# 		"clevertech.tasks.daily"
# 	],
# 	"hourly": [
# 		"clevertech.tasks.hourly"
# 	],
# 	"weekly": [
# 		"clevertech.tasks.weekly"
# 	],
# 	"monthly": [
# 		"clevertech.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "clevertech.install.before_tests"

# Overriding Methods
# ------------------------------

override_whitelisted_methods = {
	"erpnext.buying.doctype.request_for_quotation.request_for_quotation.create_supplier_quotation": "clevertech.supply_chain.server_scripts.rfq_portal.create_supplier_quotation",
	"erpnext.stock.doctype.material_request.material_request.make_request_for_quotation": "clevertech.supply_chain.server_scripts.rfq_get_items.make_request_for_quotation",
	"erpnext.buying.doctype.request_for_quotation.request_for_quotation.get_item_from_material_requests_based_on_supplier": "clevertech.supply_chain.server_scripts.rfq_get_items.get_item_from_material_requests_based_on_supplier"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Purchase Order": "clevertech.purchase_order_dashboard.get_data"
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["clevertech.utils.before_request"]
# after_request = ["clevertech.utils.after_request"]

# Job Events
# ----------
# before_job = ["clevertech.utils.before_job"]
# after_job = ["clevertech.utils.after_job"]

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
# 	"clevertech.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

