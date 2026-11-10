import unittest
from decimal import Decimal

from insurance import (AuditLog, CoverageType, CustomerService, NotFoundError,
                       ProductCategory, ProductService, ProductStatus,
                       ValidationError, WorkflowError)
from insurance.seed import seed

BASE = dict(name="P", category="health", coverage_types=["dental"],
            base_premium="10.50", premium_frequency="monthly", currency="USD",
            min_duration_months=6, max_duration_months=12,
            coverage_limit="1000", deductible="10")


def mk(s=None, **kw):
    s = s or ProductService()
    return s, s.create(**{**BASE, **kw})


class ProductTests(unittest.TestCase):
    def test_create_each_category(self):
        s = ProductService()
        for cat, cov in (("health", "outpatient"), ("vehicle", "theft"),
                         ("life", "term_life")):
            p = s.create(**{**BASE, "category": cat, "coverage_types": [cov]})
            self.assertEqual(p.status, ProductStatus.DRAFT)
            self.assertEqual(p.category, ProductCategory(cat))
        self.assertEqual(len(s.list(category="vehicle")), 1)

    def test_decimal_and_annualisation(self):
        _, p = mk(base_premium="89.00")
        self.assertEqual(p.annual_base_premium, Decimal("1068.00"))
        _, p = mk(premium_frequency="quarterly", base_premium="100")
        self.assertEqual(p.annual_base_premium, Decimal("400"))
        _, p = mk(premium_frequency="annual", base_premium="100")
        self.assertEqual(p.annual_base_premium, Decimal("100"))

    def test_invalid_inputs(self):
        bad = [dict(name=" "), dict(category="pet"), dict(coverage_types=[]),
               dict(coverage_types=["bogus"]),
               dict(coverage_types=["dental", "dental"]),
               dict(coverage_types=["theft"]),  # wrong category
               dict(base_premium=0), dict(base_premium="abc"),
               dict(base_premium="NaN"), dict(coverage_limit=-1),
               dict(deductible=-1), dict(deductible="1000"),
               dict(premium_frequency="weekly"), dict(currency="usd"),
               dict(currency="US"), dict(min_duration_months=0),
               dict(min_duration_months=13), dict(max_duration_months=601),
               dict(min_duration_months=True), dict(min_duration_months="6")]
        for kw in bad:
            with self.subTest(kw=kw), self.assertRaises(ValidationError):
                mk(**kw)

    def test_failed_create_does_not_consume_id(self):
        s = ProductService()
        with self.assertRaises(ValidationError):
            s.create(**{**BASE, "name": ""})
        self.assertEqual(s.create(**BASE).id, "PRD-0001")

    def test_lifecycle(self):
        s, p = mk()
        s.activate(p.id)
        with self.assertRaises(WorkflowError):
            s.activate(p.id)
        s.retire(p.id)
        with self.assertRaises(WorkflowError):
            s.activate(p.id)
        with self.assertRaises(WorkflowError):
            s.update(p.id, name="x")

    def test_cannot_retire_draft(self):
        s, p = mk()
        with self.assertRaises(WorkflowError):
            s.retire(p.id)

    def test_update_versions_and_audit(self):
        s, p = mk()
        n = s.update(p.id, base_premium="12", coverage_types=["dental", "outpatient"])
        self.assertEqual(n.version, 2)
        self.assertEqual(n.coverage_types,
                         (CoverageType.DENTAL, CoverageType.OUTPATIENT))
        e = s.audit.entries("product", p.id)[-1]
        self.assertEqual(e.action, "product.updated")
        self.assertEqual(e.details["base_premium"]["to"], "12")

    def test_noop_update(self):
        s, p = mk()
        self.assertEqual(s.update(p.id, name="P").version, 1)
        self.assertEqual(len(s.audit.entries("product", p.id)), 1)

    def test_active_locks_category_but_allows_pricing(self):
        s, p = mk()
        s.activate(p.id)
        with self.assertRaises(WorkflowError):
            s.update(p.id, category="life", coverage_types=["term_life"])
        self.assertEqual(s.update(p.id, base_premium="11").base_premium, Decimal("11"))

    def test_update_validation_and_unknown_field(self):
        s, p = mk()
        with self.assertRaises(ValidationError):
            s.update(p.id, base_premium=-1)
        with self.assertRaises(ValidationError):
            s.update(p.id, status="active")
        self.assertEqual(s.get(p.id).version, 1)

    def test_not_found_and_filters(self):
        s, p = mk()
        with self.assertRaises(NotFoundError):
            s.get("x")
        self.assertEqual(s.list(status="draft"), [p])
        self.assertEqual(s.list(status="active"), [])

    def test_seed(self):
        a = AuditLog(); ps, cs = ProductService(a), CustomerService(a)
        seed(cs, ps)
        self.assertEqual(len(ps.list(status="active")), 3)
        self.assertEqual(len(cs.list()), 1)
        self.assertTrue(a.entries())


if __name__ == "__main__":
    unittest.main()
