"""Generate the synthetic sample dataset. Run once: `python samples/generate.py`."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent
rng = random.Random(42)

COUNTRIES = [
    ("United States", "North America", 0.34),
    ("Canada", "North America", 0.08),
    ("United Kingdom", "Europe", 0.12),
    ("Germany", "Europe", 0.12),
    ("France", "Europe", 0.08),
    ("India", "Asia", 0.1),
    ("Japan", "Asia", 0.06),
    ("Australia", "Oceania", 0.05),
    ("Brazil", "South America", 0.05),
]
SEGMENTS = ["Consumer", "Small Business", "Enterprise"]
FIRST = ["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Riley", "Casey", "Jamie", "Avery", "Quinn",
         "Priya", "Chen", "Mateo", "Sofia", "Liam", "Noah", "Emma", "Olivia", "Yuki", "Hans"]  # fmt: skip
LAST = ["Smith", "Johnson", "Brown", "Garcia", "Miller", "Davis", "Patel", "Kim", "Nguyen", "Muller",
        "Rossi", "Silva", "Sato", "Dubois", "Khan", "Lopez", "Wilson", "Anderson", "Clark", "Young"]  # fmt: skip

PRODUCTS = [
    ("Notebook Computer 14in", "Notebook Computers", 899.0),
    ("Notebook Computer 16in", "Notebook Computers", 1299.0),
    ("Ultrabook Pro", "Notebook Computers", 1599.0),
    ("Gaming Laptop X", "Notebook Computers", 1899.0),
    ("Wireless Mouse", "Computer Accessories", 29.0),
    ("Mechanical Keyboard", "Computer Accessories", 89.0),
    ("USB-C Hub", "Computer Accessories", 49.0),
    ("Laptop Stand", "Computer Accessories", 39.0),
    ("Webcam HD", "Computer Accessories", 59.0),
    ("27in Monitor", "Displays", 329.0),
    ("32in 4K Monitor", "Displays", 549.0),
    ("Portable Monitor", "Displays", 199.0),
    ("Noise Cancelling Headphones", "Audio", 249.0),
    ("Bluetooth Speaker", "Audio", 79.0),
    ("Earbuds", "Audio", 129.0),
    ("Studio Microphone", "Audio", 159.0),
    ("Smartphone Pro", "Mobile Phones", 999.0),
    ("Smartphone Lite", "Mobile Phones", 499.0),
    ("Phone Case", "Mobile Phones", 19.0),
    ("Wireless Charger", "Mobile Phones", 35.0),
    ("Tablet 10in", "Tablets", 429.0),
    ("Tablet Mini", "Tablets", 329.0),
    ("Stylus Pen", "Tablets", 69.0),
    ("Smart Watch", "Wearables", 299.0),
    ("Fitness Band", "Wearables", 99.0),
    ("Router AX", "Networking", 139.0),
    ("Mesh Wi-Fi 3-pack", "Networking", 279.0),
    ("Ethernet Switch 8-port", "Networking", 45.0),
    ("External SSD 1TB", "Storage", 109.0),
    ("External SSD 2TB", "Storage", 189.0),
    ("USB Flash Drive 128GB", "Storage", 19.0),
    ("Network Storage 4-bay", "Storage", 449.0),
]
STATUSES = [("completed", 0.82), ("shipped", 0.07), ("cancelled", 0.07), ("refunded", 0.04)]


def weighted(options):
    r, acc = rng.random(), 0.0
    for value, weight in options:
        acc += weight
        if r <= acc:
            return value
    return options[-1][0]


def write(name, header, rows):
    with open(OUT / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main():
    start = date(2025, 1, 1)
    customers = []
    for cid in range(1, 201):
        country, region, _ = weighted([((c, r, w), w) for c, r, w in COUNTRIES])
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        signup = start + timedelta(days=rng.randint(0, 540))
        customers.append(
            [cid, name, f"user{cid}@example.com", country, region, rng.choice(SEGMENTS), signup]
        )
    write(
        "customers",
        ["id", "name", "email", "country", "region", "segment", "signup_date"],
        customers,
    )

    products = [
        [i, n, c, p, round(p * rng.uniform(0.5, 0.7), 2)] for i, (n, c, p) in enumerate(PRODUCTS, 1)
    ]
    write("products", ["id", "name", "category", "price", "cost"], products)

    orders, items = [], []
    item_id = 1
    for oid in range(1, 1501):
        cust = rng.choice(customers)
        signup = cust[6]
        order_date = signup + timedelta(days=rng.randint(0, 600))
        order_date = min(order_date, date(2026, 9, 30))
        if order_date < date(2025, 1, 1):
            order_date = date(2025, 1, 1)
        status = weighted(STATUSES)
        total = 0.0
        for _ in range(rng.choices([1, 2, 3, 4], [0.5, 0.3, 0.15, 0.05])[0]):
            prod = rng.choice(products)
            qty = rng.choices([1, 2, 3, 5], [0.65, 0.2, 0.1, 0.05])[0]
            items.append([item_id, oid, prod[0], qty, prod[3]])
            total += qty * prod[3]
            item_id += 1
        orders.append([oid, cust[0], order_date, status, round(total, 2)])
    write("orders", ["id", "customer_id", "order_date", "status", "total_amount"], orders)
    write("order_items", ["id", "order_id", "product_id", "quantity", "unit_price"], items)


if __name__ == "__main__":
    main()
