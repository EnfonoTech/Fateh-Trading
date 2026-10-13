import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from fateh_trading.test import get_item_insights, get_last_landed_purchase_cost


class TestPriceAssistLandedCost(FrappeTestCase):
	"""Price Assist shows purchase cost after discount, including landed cost."""

	def _receipt_line(self):
		rows = frappe.db.sql(
			"""
			select c.item_code, c.valuation_rate, p.name
			from `tabPurchase Receipt Item` c
			join `tabPurchase Receipt` p on p.name = c.parent
			where p.docstatus = 1 and p.is_return = 0 and c.valuation_rate > 0
			order by p.posting_date desc, p.name desc
			limit 1
			""",
			as_dict=True,
		)
		return rows[0] if rows else None

	def test_cost_comes_from_valuation_rate(self):
		line = self._receipt_line()
		if not line:
			self.skipTest("no submitted Purchase Receipt")
		cost = get_last_landed_purchase_cost(line.item_code)
		self.assertGreater(cost, 0)
		insights = get_item_insights(customer="", item_code=line.item_code)
		self.assertAlmostEqual(insights["last_purchase_rate"], cost, places=4)

	def test_unknown_item_returns_zero(self):
		self.assertEqual(get_last_landed_purchase_cost("__no_such_item__"), 0)
