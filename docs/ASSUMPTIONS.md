# Business assumptions

Scope: Customer Management and Insurance Product Management only. Policy
issuance, premium calculation engine, claims, assessments, payments and
reporting are **not** implemented. All data is in-memory mock data.

## Customers
- Customers must be 18+ (ages computed against injectable "today").
- Email is unique (case-insensitive); phone is 8-20 chars of digits/space/dash with optional leading `+`.
- Policy ownership is a link from a customer to an external policy number; a
  policy number can have one owner. Inactive customers cannot gain policies
  and customers owning policies cannot be deactivated.

## Products
- Categories: health, vehicle, life; coverage types are restricted per category.
- Lifecycle: `draft -> active -> retired` (no other transitions). Retired is immutable;
  active products lock category/coverage; every edit bumps `version`.
- Duration is expressed in months, `1 <= min <= max <= 600`.
- Premium configuration fields: `base_premium` is the premium per
  `premium_frequency` period (monthly=12, quarterly=4, annual=1 periods/year).
  The only calculation provided is annualisation:
  `annual_base_premium = base_premium x periods_per_year`
  (e.g. 89.00 monthly -> 1068.00/year). Risk factors, discounts, taxes and
  underwriting are the future (excluded) pricing engine's concern.
- `deductible` must be >= 0 and < `coverage_limit`. Money uses `Decimal`.

## Audit trail
Every create/update/status change/ownership link is recorded in an append-only
`AuditLog` with actor, UTC timestamp, entity and before/after details.
