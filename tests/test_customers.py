import unittest
from datetime import date

from insurance import (Address, AuditLog, CustomerService, NotFoundError,
                       ValidationError, WorkflowError)

ADDR = Address("1 Main St", "Town", "12345")
TODAY = date(2026, 1, 1)


def svc():
    return CustomerService(AuditLog(), today=lambda: TODAY)


def mk(s, email="a@x.com"):
    return s.create("A", "B", date(1990, 1, 1), email, "+1 555 123 4567", ADDR)


class CustomerTests(unittest.TestCase):
    def test_create_and_get(self):
        s = svc(); c = mk(s)
        self.assertEqual(c.id, "CUS-00001")
        self.assertEqual(s.get(c.id), c)

    def test_validation_collects_errors(self):
        with self.assertRaises(ValidationError) as cm:
            svc().create("", " ", date(2020, 1, 1), "bad", "1",
                         Address("", "", "", "USA"))
        self.assertGreaterEqual(len(cm.exception.errors), 8)

    def test_age_boundary(self):
        s = svc()
        s.create("A", "B", date(2008, 1, 1), "a@x.com", "+1 555 123 4567", ADDR)
        with self.assertRaises(ValidationError):
            s.create("A", "B", date(2008, 1, 2), "b@x.com", "+1 555 123 4567", ADDR)

    def test_future_dob(self):
        with self.assertRaises(ValidationError):
            svc().create("A", "B", date(2027, 1, 1), "a@x.com", "+1 555 123 4567", ADDR)

    def test_duplicate_email(self):
        s = svc(); mk(s)
        with self.assertRaises(ValidationError):
            mk(s, "A@X.com")

    def test_update_contact_and_audit(self):
        s = svc(); c = mk(s)
        n = s.update_contact(c.id, email="new@x.com")
        self.assertEqual(n.email, "new@x.com")
        e = s.audit.entries("customer", c.id)[-1]
        self.assertEqual(e.action, "customer.contact_updated")
        self.assertEqual(e.details["email"]["from"], "a@x.com")

    def test_update_contact_invalid_and_own_email_ok(self):
        s = svc(); c = mk(s)
        with self.assertRaises(ValidationError):
            s.update_contact(c.id, phone="x")
        s.update_contact(c.id, email="a@x.com")  # unchanged, no dup error
        self.assertEqual(len(s.audit.entries("customer", c.id)), 1)

    def test_update_profile(self):
        s = svc(); c = mk(s)
        self.assertEqual(s.update_profile(c.id, first_name="Z").first_name, "Z")

    def test_not_found(self):
        with self.assertRaises(NotFoundError):
            svc().get("nope")

    def test_list_filters(self):
        s = svc(); a = mk(s); mk(s, "b@x.com")
        s.deactivate(a.id)
        self.assertEqual(len(s.list(status="active")), 1)
        self.assertEqual(len(s.list(search="B@X")), 1)

    def test_policy_ownership(self):
        s = svc(); a = mk(s); b = mk(s, "b@x.com")
        s.link_policy(a.id, "POL-1001")
        self.assertEqual(s.owner_of("POL-1001").id, a.id)
        with self.assertRaises(ValidationError):
            s.link_policy(b.id, "POL-1001")
        with self.assertRaises(ValidationError):
            s.link_policy(a.id, "bad policy")
        s.unlink_policy(a.id, "POL-1001")
        with self.assertRaises(NotFoundError):
            s.owner_of("POL-1001")
        with self.assertRaises(NotFoundError):
            s.unlink_policy(a.id, "POL-1001")

    def test_deactivate_rules(self):
        s = svc(); a = mk(s)
        s.link_policy(a.id, "POL-1001")
        with self.assertRaises(WorkflowError):
            s.deactivate(a.id)
        s.unlink_policy(a.id, "POL-1001")
        s.deactivate(a.id)
        with self.assertRaises(WorkflowError):
            s.deactivate(a.id)
        with self.assertRaises(WorkflowError):
            s.link_policy(a.id, "POL-2002")
        s.reactivate(a.id)
        with self.assertRaises(WorkflowError):
            s.reactivate(a.id)

    def test_audit_trail_order(self):
        s = svc(); a = mk(s); s.link_policy(a.id, "POL-1001")
        acts = [e.action for e in s.audit.entries()]
        self.assertEqual(acts, ["customer.created", "customer.policy_linked"])
        self.assertEqual([e.seq for e in s.audit.entries()], [1, 2])


if __name__ == "__main__":
    unittest.main()
