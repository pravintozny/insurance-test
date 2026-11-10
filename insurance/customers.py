"""Customer profiles, contact details and policy ownership references.

Policy *issuance* is out of scope: ownership is just a link between a
customer and an externally supplied policy number.
"""
import re
from dataclasses import dataclass, field, replace
from datetime import date

from .audit import AuditLog
from .errors import NotFoundError, ValidationError, WorkflowError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{6,18}[0-9]$")
POLICY_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{3,31}$")
MIN_AGE = 18


@dataclass(frozen=True)
class Address:
    line1: str
    city: str
    postal_code: str
    country: str = "US"
    line2: str = ""


@dataclass(frozen=True)
class Customer:
    id: str
    first_name: str
    last_name: str
    date_of_birth: date
    email: str
    phone: str
    address: Address
    status: str = "active"  # active | inactive
    policy_numbers: tuple = ()


class CustomerService:
    def __init__(self, audit=None, today=date.today):
        self.audit = audit or AuditLog()
        self._today = today
        self._customers = {}
        self._seq = 0

    # -- validation ---------------------------------------------------
    def _validate(self, first_name, last_name, dob, email, phone, address,
                  exclude_id=None):
        errs = []
        if not (first_name or "").strip():
            errs.append("first_name is required")
        if not (last_name or "").strip():
            errs.append("last_name is required")
        if not isinstance(dob, date):
            errs.append("date_of_birth must be a date")
        else:
            t = self._today()
            age = t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))
            if dob > t:
                errs.append("date_of_birth cannot be in the future")
            elif age < MIN_AGE:
                errs.append(f"customer must be at least {MIN_AGE} years old")
            elif age > 120:
                errs.append("date_of_birth is implausible")
        if not EMAIL_RE.match(email or ""):
            errs.append("email is invalid")
        else:
            for c in self._customers.values():
                if c.id != exclude_id and c.email.lower() == email.lower():
                    errs.append("email is already registered")
        if not PHONE_RE.match(phone or ""):
            errs.append("phone is invalid")
        if not isinstance(address, Address):
            errs.append("address is required")
        else:
            if not address.line1.strip():
                errs.append("address.line1 is required")
            if not address.city.strip():
                errs.append("address.city is required")
            if not address.postal_code.strip():
                errs.append("address.postal_code is required")
            if len(address.country.strip()) != 2:
                errs.append("address.country must be an ISO 3166 alpha-2 code")
        if errs:
            raise ValidationError(errs)

    # -- operations ---------------------------------------------------
    def create(self, first_name, last_name, date_of_birth, email, phone,
               address, actor="system"):
        self._validate(first_name, last_name, date_of_birth, email, phone,
                       address)
        self._seq += 1
        cid = f"CUS-{self._seq:05d}"
        c = Customer(cid, first_name.strip(), last_name.strip(),
                     date_of_birth, email.strip(), phone.strip(), address)
        self._customers[cid] = c
        self.audit.record(actor, "customer.created", "customer", cid,
                          {"email": c.email})
        return c

    def get(self, customer_id):
        try:
            return self._customers[customer_id]
        except KeyError:
            raise NotFoundError(f"customer {customer_id} not found") from None

    def list(self, status=None, search=None):
        out = []
        for c in self._customers.values():
            if status and c.status != status:
                continue
            if search and search.lower() not in (
                    f"{c.first_name} {c.last_name} {c.email}").lower():
                continue
            out.append(c)
        return out

    def update_contact(self, customer_id, email=None, phone=None,
                       address=None, actor="system"):
        c = self.get(customer_id)
        new = replace(c, email=(email or c.email).strip(),
                      phone=(phone or c.phone).strip(),
                      address=address or c.address)
        self._validate(c.first_name, c.last_name, c.date_of_birth, new.email,
                       new.phone, new.address, exclude_id=c.id)
        changes = {k: {"from": str(getattr(c, k)), "to": str(getattr(new, k))}
                   for k in ("email", "phone", "address")
                   if getattr(c, k) != getattr(new, k)}
        self._customers[c.id] = new
        if changes:
            self.audit.record(actor, "customer.contact_updated", "customer",
                              c.id, changes)
        return new

    def update_profile(self, customer_id, first_name=None, last_name=None,
                       actor="system"):
        c = self.get(customer_id)
        new = replace(c, first_name=(first_name or c.first_name).strip(),
                      last_name=(last_name or c.last_name).strip())
        self._validate(new.first_name, new.last_name, c.date_of_birth,
                       c.email, c.phone, c.address, exclude_id=c.id)
        self._customers[c.id] = new
        self.audit.record(actor, "customer.profile_updated", "customer", c.id,
                          {"name": f"{new.first_name} {new.last_name}"})
        return new

    def deactivate(self, customer_id, actor="system"):
        c = self.get(customer_id)
        if c.status == "inactive":
            raise WorkflowError("customer already inactive")
        if c.policy_numbers:
            raise WorkflowError(
                "cannot deactivate a customer who owns policies")
        self._customers[c.id] = replace(c, status="inactive")
        self.audit.record(actor, "customer.deactivated", "customer", c.id)
        return self._customers[c.id]

    def reactivate(self, customer_id, actor="system"):
        c = self.get(customer_id)
        if c.status == "active":
            raise WorkflowError("customer already active")
        self._customers[c.id] = replace(c, status="active")
        self.audit.record(actor, "customer.reactivated", "customer", c.id)
        return self._customers[c.id]

    # -- policy ownership --------------------------------------------
    def link_policy(self, customer_id, policy_number, actor="system"):
        c = self.get(customer_id)
        if not POLICY_RE.match(policy_number or ""):
            raise ValidationError("policy_number is invalid")
        if c.status != "active":
            raise WorkflowError("inactive customers cannot own new policies")
        if any(policy_number in o.policy_numbers
               for o in self._customers.values()):
            raise ValidationError("policy_number is already owned")
        self._customers[c.id] = replace(
            c, policy_numbers=c.policy_numbers + (policy_number,))
        self.audit.record(actor, "customer.policy_linked", "customer", c.id,
                          {"policy_number": policy_number})
        return self._customers[c.id]

    def unlink_policy(self, customer_id, policy_number, actor="system"):
        c = self.get(customer_id)
        if policy_number not in c.policy_numbers:
            raise NotFoundError(f"policy {policy_number} not owned by {c.id}")
        self._customers[c.id] = replace(c, policy_numbers=tuple(
            p for p in c.policy_numbers if p != policy_number))
        self.audit.record(actor, "customer.policy_unlinked", "customer", c.id,
                          {"policy_number": policy_number})
        return self._customers[c.id]

    def owner_of(self, policy_number):
        for c in self._customers.values():
            if policy_number in c.policy_numbers:
                return c
        raise NotFoundError(f"policy {policy_number} has no owner")
