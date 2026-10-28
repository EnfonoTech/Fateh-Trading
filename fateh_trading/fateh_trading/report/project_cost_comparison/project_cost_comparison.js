// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Project Cost Comparison"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "project_type",
			label: __("Project Type"),
			fieldtype: "Link",
			options: "Project Type",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOpen\nCompleted\nCancelled",
		},
		{
			fieldname: "from_date",
			label: __("Start Date (From)"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("End Date (To)"),
			fieldtype: "Date",
		},
	],
};
