"""Insurance product catalogue: health, vehicle and life products.

Premium *configuration* only (base premium, frequency, factors). No premium
calculation engine lives here; see docs/ASSUMPTIONS.md.
"""
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum

from .audit import AuditLog
from .errors import NotFoundError, ValidationError, WorkflowError


class ProductCategory(str, Enum):
    HEALTH = "health"
    VEHICLE = "vehicle"
    LIFE = "life"


class ProductStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class CoverageType(str, Enum):
    # health
    HOSPITALIZATION = "hospitalization"
    OUTPATIENT = "outpatient"
    DENTAL = "dental"
    # vehicle
    THIRD_PARTY = "third_party"
    COMPREHENSIVE = "comprehensive"
    THEFT = "theft"
    # life
    TERM_LIFE = "term_life"
    WHOLE_LIFE = "whole_life"
    ACCIDENTAL_DEATH = "accidental_death"


ALLOWED_COVERAGES = {
    ProductCategory.HEALTH: {CoverageType.HOSPITALIZATION,
                             CoverageType.OUTPATIENT, CoverageType.DENTAL},
    ProductCategory.VEHICLE: {CoverageType.THIRD_PARTY,
                              CoverageType.COMPREHENSIVE, CoverageType.THEFT},
    ProductCategory.LIFE: {CoverageType.TERM_LIFE, CoverageType.WHOLE_LIFE,
                           CoverageType.ACCIDENTAL_DEATH},
}

PREMIUM_FREQUENCIES = {"monthly": 12, "quarterly": 4, "annual": 1}
TRANSITIONS = {
    ProductStatus.DRAFT: {ProductStatus.ACTIVE},
    ProductStatus.ACTIVE: {ProductStatus.RETIRED},
    ProductStatus.RETIRED: set(),
}
MAX_DURATION_MONTHS = 600


def _dec(value, name, errs):
    try:
        d = Decimal(str(value))
        if not d.is_finite():
            raise InvalidOperation
        return d
    except (InvalidOperation, ValueError):
        errs.append(f"{name} must be a number")
        return None


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    category: ProductCategory
    coverage_types: tuple
    base_premium: Decimal          # per premium_frequency period, in currency
    premium_frequency: str
    currency: str
    min_duration_months: int
    max_duration_months: int
    coverage_limit: Decimal
    deductible: Decimal = Decimal("0")
    status: ProductStatus = ProductStatus.DRAFT
    version: int = 1

    @property
    def annual_base_premium(self):
        """Base premium annualised: base_premium x periods per year."""
        return self.base_premium * PREMIUM_FREQUENCIES[self.premium_frequency]


class ProductService:
    def __init__(self, audit=None):
        self.audit = audit or AuditLog()
        self._products = {}
        self._seq = 0

    def _build(self, pid, name, category, coverage_types, base_premium,
               premium_frequency, currency, min_duration_months,
               max_duration_months, coverage_limit, deductible, status,
               version):
        errs = []
        if not (name or "").strip():
            errs.append("name is required")
        try:
            category = ProductCategory(category)
        except ValueError:
            errs.append("category must be health, vehicle or life")
            category = None
        covs = []
        try:
            covs = [CoverageType(c) for c in coverage_types]
        except (ValueError, TypeError):
            errs.append("coverage_types contains an unknown coverage type")
        if not covs:
            errs.append("at least one coverage type is required")
        elif len(set(covs)) != len(covs):
            errs.append("coverage_types contains duplicates")
        if category and covs and not set(covs) <= ALLOWED_COVERAGES[category]:
            errs.append(f"coverage types not allowed for {category.value}")
        bp = _dec(base_premium, "base_premium", errs)
        if bp is not None and bp <= 0:
            errs.append("base_premium must be greater than 0")
        cl = _dec(coverage_limit, "coverage_limit", errs)
        if cl is not None and cl <= 0:
            errs.append("coverage_limit must be greater than 0")
        ded = _dec(deductible, "deductible", errs)
        if ded is not None and ded < 0:
            errs.append("deductible cannot be negative")
        if ded is not None and cl is not None and ded >= cl:
            errs.append("deductible must be less than coverage_limit")
        if premium_frequency not in PREMIUM_FREQUENCIES:
            errs.append("premium_frequency must be monthly, quarterly or annual")
        if not (isinstance(currency, str) and len(currency) == 3
                and currency.isupper() and currency.isalpha()):
            errs.append("currency must be a 3-letter uppercase code")
        ok = True
        for label, v in (("min_duration_months", min_duration_months),
                         ("max_duration_months", max_duration_months)):
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                errs.append(f"{label} must be a positive integer")
                ok = False
        if ok:
            if min_duration_months > max_duration_months:
                errs.append("min_duration_months cannot exceed max_duration_months")
            if max_duration_months > MAX_DURATION_MONTHS:
                errs.append(f"max_duration_months cannot exceed {MAX_DURATION_MONTHS}")
        if errs:
            raise ValidationError(errs)
        return Product(pid, name.strip(), category, tuple(covs), bp,
                       premium_frequency, currency, min_duration_months,
                       max_duration_months, cl, ded, status, version)

    def create(self, name, category, coverage_types, base_premium,
               premium_frequency, currency, min_duration_months,
               max_duration_months, coverage_limit, deductible=0,
               actor="system"):
        pid = f"PRD-{self._seq + 1:04d}"
        p = self._build(pid, name, category, coverage_types, base_premium,
                        premium_frequency, currency, min_duration_months,
                        max_duration_months, coverage_limit, deductible,
                        ProductStatus.DRAFT, 1)
        self._seq += 1
        self._products[pid] = p
        self.audit.record(actor, "product.created", "product", pid,
                          {"name": p.name, "category": p.category.value})
        return p

    def get(self, product_id):
        try:
            return self._products[product_id]
        except KeyError:
            raise NotFoundError(f"product {product_id} not found") from None

    def list(self, category=None, status=None):
        return [p for p in self._products.values()
                if (category is None or p.category == ProductCategory(category))
                and (status is None or p.status == ProductStatus(status))]

    def update(self, product_id, actor="system", **changes):
        """Edit a product. Only drafts may change category/coverage; active
        products may change pricing/duration (version bumps); retired
        products are immutable."""
        p = self.get(product_id)
        if p.status == ProductStatus.RETIRED:
            raise WorkflowError("retired products cannot be modified")
        allowed = {"name", "category", "coverage_types", "base_premium",
                   "premium_frequency", "currency", "min_duration_months",
                   "max_duration_months", "coverage_limit", "deductible"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"unknown fields: {sorted(unknown)}")
        if p.status == ProductStatus.ACTIVE and (
                {"category", "coverage_types"} & set(changes)):
            raise WorkflowError(
                "category and coverage_types are locked once active")
        cur = dict(name=p.name, category=p.category,
                   coverage_types=p.coverage_types,
                   base_premium=p.base_premium,
                   premium_frequency=p.premium_frequency, currency=p.currency,
                   min_duration_months=p.min_duration_months,
                   max_duration_months=p.max_duration_months,
                   coverage_limit=p.coverage_limit, deductible=p.deductible)
        cur.update(changes)
        new = self._build(p.id, status=p.status, version=p.version + 1, **cur)
        diff = {k: {"from": str(getattr(p, k)), "to": str(getattr(new, k))}
                for k in allowed if getattr(p, k) != getattr(new, k)}
        if not diff:
            return p
        self._products[p.id] = new
        self.audit.record(actor, "product.updated", "product", p.id, diff)
        return new

    def _transition(self, product_id, target, actor):
        p = self.get(product_id)
        if target not in TRANSITIONS[p.status]:
            raise WorkflowError(
                f"cannot move product from {p.status.value} to {target.value}")
        self._products[p.id] = replace(p, status=target)
        self.audit.record(actor, f"product.{target.value}", "product", p.id,
                          {"from": p.status.value, "to": target.value})
        return self._products[p.id]

    def activate(self, product_id, actor="system"):
        return self._transition(product_id, ProductStatus.ACTIVE, actor)

    def retire(self, product_id, actor="system"):
        return self._transition(product_id, ProductStatus.RETIRED, actor)
