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
			"fieldname": "total_sales_amount",
			"label": _("Order Value"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "total_billed_amount",
			"label": _("Billed Amount (Income)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"fieldname": "actual_cost",
			"label": _("Actual Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "gross_profit",
			"label": _("Gross Profit / (Loss)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 170,
		},
		{
			"fieldname": "gross_margin_percent",
			"label": _("Gross Margin %"),
			"fieldtype": "Percent",
			"width": 120,
		},
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
			"total_sales_amount",
			"total_billed_amount",
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
		project["gross_profit"] = flt(project.total_billed_amount) - actual_cost
		project["gross_margin_percent"] = (
			(project["gross_profit"] / flt(project.total_billed_amount)) * 100
			if project.total_billed_amount
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
	if filters.get("customer"):
		conditions["customer"] = filters.customer
	if filters.get("from_date"):
		conditions["expected_start_date"] = (">=", filters.from_date)
	if filters.get("to_date"):
		conditions["expected_end_date"] = ("<=", filters.to_date)

	return conditions


def get_chart_data(data):
	if not data:
		return None

	labels, income, cost, profit = [], [], [], []
	for project in data[:30]:
		labels.append(project.project_name or project.name)
		income.append(project.total_billed_amount)
		cost.append(project.actual_cost)
		profit.append(project.gross_profit)

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Billed Amount"), "values": income},
				{"name": _("Actual Cost"), "values": cost},
				{"name": _("Gross Profit"), "values": profit},
			],
		},
		"type": "bar",
		"colors": ["#7575ff", "#fc4f51", "#29a56c"],
	}


def get_report_summary(data):
	if not data:
		return None

	total_income = sum(flt(p.total_billed_amount) for p in data)
	total_cost = sum(flt(p.actual_cost) for p in data)
	total_profit = total_income - total_cost
	overall_margin = (total_profit / total_income * 100) if total_income else 0

	return [
		{
			"value": total_income,
			"indicator": "Blue",
			"label": _("Total Billed Amount"),
			"datatype": "Currency",
		},
		{
			"value": total_cost,
			"indicator": "Blue",
			"label": _("Total Actual Cost"),
			"datatype": "Currency",
		},
		{
			"value": total_profit,
			"indicator": "Green" if total_profit >= 0 else "Red",
			"label": _("Total Gross Profit / (Loss)"),
			"datatype": "Currency",
		},
		{
			"value": overall_margin,
			"indicator": "Green" if overall_margin >= 0 else "Red",
			"label": _("Overall Gross Margin %"),
			"datatype": "Percent",
		},
	]
