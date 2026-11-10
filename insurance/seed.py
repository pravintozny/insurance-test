"""Mock seed data (fictional; no real providers)."""
from datetime import date

from .customers import Address, CustomerService
from .products import ProductService


def seed(customers: CustomerService, products: ProductService):
    products.create("Basic Health", "health", ["hospitalization", "outpatient"],
                    "89.00", "monthly", "USD", 12, 12, "250000", "500")
    products.create("Comprehensive Auto", "vehicle", ["comprehensive", "theft"],
                    "620.00", "annual", "USD", 12, 36, "50000", "1000")
    products.create("Term Life 20", "life", ["term_life"], "310.00",
                    "quarterly", "USD", 60, 240, "500000")
    for p in products.list():
        products.activate(p.id)
    customers.create("Ada", "Example", date(1985, 4, 12), "ada@example.com",
                     "+1 555 010 0100",
                     Address("1 Sample St", "Springfield", "12345"))
