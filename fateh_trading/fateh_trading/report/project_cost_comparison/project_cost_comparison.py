# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	report_summary = get_report_summary(data)
	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{
			"fieldname": "name",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 150,
		},
		{"fieldname": "project_name", "label": _("Project Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 140,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 140,
		},
		{
			"fieldname": "estimated_costing",
			"label": _("Estimated Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "total_purchase_cost",
			"label": _("Purchase Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "total_consumed_material_cost",
			"label": _("Consumed Material Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"fieldname": "total_costing_amount",
			"label": _("Timesheet Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "actual_cost",
			"label": _("Actual Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "variance",
			"label": _("Variance (Actual - Estimated)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 190,
		},
		{"fieldname": "variance_percent", "label": _("Variance %"), "fieldtype": "Percent", "width": 110},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 90,
			"hidden": 1,
		},
	]


def get_data(filters):
	conditions = get_conditions(filters)

	projects = frappe.db.get_all(
		"Project",
		filters=conditions,
		fields=[
			"name",
			"project_name",
			"status",
			"company",
			"customer",
			"estimated_costing",
			"total_purchase_cost",
			"total_consumed_material_cost",
			"total_costing_amount",
		],
		order_by="company, project_name",
	)

	company_currency = {}
	for project in projects:
		actual_cost = (
			flt(project.total_purchase_cost)
			+ flt(project.total_consumed_material_cost)
			+ flt(project.total_costing_amount)
		)
		project["actual_cost"] = actual_cost
		project["variance"] = actual_cost - flt(project.estimated_costing)
		project["variance_percent"] = (
			(project["variance"] / flt(project.estimated_costing)) * 100
			if project.estimated_costing
			else 0
		)

		if project.company not in company_currency:
			company_currency[project.company] = frappe.get_cached_value(
				"Company", project.company, "default_currency"
			)
		project["currency"] = company_currency[project.company]

	return projects


def get_conditions(filters):
	conditions = {}

	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("project"):
		conditions["name"] = filters.project
	if filters.get("project_type"):
		conditions["project_type"] = filters.project_type
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("from_date"):
		conditions["expected_start_date"] = (">=", filters.from_date)
	if filters.get("to_date"):
		conditions["expected_end_date"] = ("<=", filters.to_date)

	return conditions


def get_chart_data(data):
	if not data:
		return None

	labels, estimated, actual = [], [], []
	for project in data[:30]:
		labels.append(project.project_name or project.name)
		estimated.append(project.estimated_costing)
		actual.append(project.actual_cost)

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Estimated Cost"), "values": estimated},
				{"name": _("Actual Cost"), "values": actual},
			],
		},
		"type": "bar",
		"colors": ["#7575ff", "#fc4f51"],
	}


def get_report_summary(data):
	if not data:
		return None

	total_estimated = sum(flt(p.estimated_costing) for p in data)
	total_actual = sum(flt(p.actual_cost) for p in data)
	total_variance = total_actual - total_estimated

	return [
		{
			"value": total_estimated,
			"indicator": "Blue",
			"label": _("Total Estimated Cost"),
			"datatype": "Currency",
		},
		{
			"value": total_actual,
			"indicator": "Blue",
			"label": _("Total Actual Cost"),
			"datatype": "Currency",
		},
		{
			"value": total_variance,
			"indicator": "Red" if total_variance > 0 else "Green",
			"label": _("Total Variance"),
			"datatype": "Currency",
		},
	]
