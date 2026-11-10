# insurance-test

Customer management and insurance product management (health, vehicle, life).
Pure Python 3.10+ standard library, in-memory, mock data only.

```python
from insurance import CustomerService, ProductService, AuditLog
audit = AuditLog()
products, customers = ProductService(audit), CustomerService(audit)
```

Run tests: `python3 -m unittest discover -s tests -v`

See [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) for business rules and premium configuration.
Out of scope: policy issuance, premium calculation engine, claims, payments, reporting.
