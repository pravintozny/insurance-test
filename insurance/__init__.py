"""Customer and insurance product management (mock/local, in-memory)."""
from .audit import AuditEntry, AuditLog
from .customers import Address, Customer, CustomerService
from .errors import NotFoundError, ValidationError, WorkflowError
from .products import (CoverageType, Product, ProductCategory, ProductService,
                       ProductStatus)

__all__ = ["AuditEntry", "AuditLog", "Address", "Customer", "CustomerService",
           "NotFoundError", "ValidationError", "WorkflowError", "CoverageType",
           "Product", "ProductCategory", "ProductService", "ProductStatus"]
