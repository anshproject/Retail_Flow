#!/usr/bin/env python3
"""
Smart Store — Dataset Import Script
=====================================
CSV files ki zaroorat NAHI hai — data already embedded hai.
(Source: OnlineRetail dataset top-60 products + Walmart weekly seasonality)

Run:
    python3 import_data.py

What it does:
  1. 60 real retail products create karta hai (INR prices mein)
  2. Store + Warehouse locations banata hai
  3. Realistic opening stock set karta hai
  4. 365 days ka sales history generate karta hai (Walmart seasonality se)
  5. Users/sessions ko touch nahi karta

SAFE TO RE-RUN: products/stock/sales/alerts clear karke fresh import karta hai.
"""

import sqlite3, os, sys, random
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH      = os.environ.get("SMART_STORE_DB", "smart_store.sqlite3")
DAYS_HISTORY = 365
RANDOM_SEED  = 42
GBP_TO_INR   = 107

# ── Embedded Product Data (from OnlineRetail dataset, top 60 by units sold) ──
# Format: (name, avg_price_gbp, total_units_sold_in_dataset)
RETAIL_PRODUCTS = [
    ('Paper Craft , Little Birdie',          2.08, 80995),
    ('Medium Ceramic Top Storage Jar',        1.47, 78033),
    ('Jumbo Bag Red Retrospot',               2.49, 48474),
    ('White Hanging Heart T-Light Holder',    3.22, 37891),
    ('Popcorn Holder',                        1.02, 36761),
    ('Assorted Colour Bird Ornament',         1.72, 36461),
    ('Rabbit Night Light',                    2.38, 30788),
    ('Mini Paint Set Vintage',                0.79, 26633),
    ('Victorian Glass Hanging T-Light',       1.64, 24304),
    ('Assorted Colours Silk Fan',             1.07, 23826),
    ('Red Harmonica In Box',                  1.42, 21933),
    ('Jumbo Bag Pink Polkadot',               2.60, 21465),
    ('Pack Of 72 Retrospot Cake Cases',       0.78, 20315),
    ('Small Popcorn Holder',                  1.07, 20160),
    ('Paper Chain Kit Christmas',             3.36, 19355),
    ('Lunch Bag Red Retrospot',               2.13, 19353),
    ('Party Bunting',                         5.79, 18295),
    ('Charlotte Bag Suki Design',             1.21, 18152),
    ('Heart Of Wicker Small',                 1.96, 17971),
    ('Red Retrospot Charlotte Bag',           1.15, 17765),
    ('Jumbo Bag Strawberry',                  2.41, 17319),
    ('Colour Glass T-Light Holder Hanging',   0.73, 16449),
    ('Jam Making Set Printed',                1.90, 16412),
    ('Grow A Flytrap Or Sunflower In Tin',    1.49, 16244),
    ('Jumbo Bag Apples',                      2.57, 14920),
    ('Antique Silver T-Light Glass',          1.50, 14688),
    ('Vintage Snap Cards',                    1.01, 14528),
    ('Spaceboy Lunch Box',                    2.19, 14260),
    ('Red Toadstool Led Night Light',         2.38, 14009),
    ('Jumbo Bag Baroque Black White',         2.60, 13922),
    ('Regency Cakestand 3 Tier',             13.98, 13879),
    ('Jumbo Storage Bag Suki',                2.74, 13654),
    ('Jumbo Bag Alphabet',                    2.39, 13379),
    ('Woodland Charlotte Bag',                1.21, 13308),
    ('Set Of 20 Red Retrospot Paper Napkins', 1.09, 13210),
    ('Set Of 4 Pantry Jelly Moulds',          1.50, 12672),
    ('Jumbo Shopper Vintage Red Paisley',     2.68, 12602),
    ('Homemade Jam Scented Candles',          1.79, 12532),
    ('Hanging Heart Jar T-Light Holder',      1.48, 12512),
    ('Please One Person Metal Sign',          2.42, 12305),
    ('Lunch Bag Black Skull',                 2.10, 12240),
    ('Lunch Bag Apple Design',                2.05, 12183),
    ('Pack Of 60 Pink Paisley Cake Cases',    0.76, 11834),
    ('Lunch Bag Cars Blue',                   2.06, 11817),
    ('Dolly Girl Lunch Box',                  2.33, 11793),
    ('Gin And Tonic Diet Metal Sign',         2.74, 11727),
    ('Black Record Cover Frame',              4.21, 11656),
    ('Lunch Box I Love London',               2.31, 11523),
    ('Jumbo Bag Vintage Doily',               2.30, 11464),
    ('Jumbo Bag Owls',                        2.77, 11444),
    ('Jumbo Bag Pink Vintage Paisley',        2.68, 11007),
    ('Pink Blue Felt Craft Trinket Box',      1.42, 11001),
    ('Jumbo Bag Vintage Leaf',                2.30, 10962),
    ('Hanging Jam Jar T-Light Holder',        0.91, 10792),
    ('60 Cake Cases Vintage Christmas',       0.78, 10775),
    ('Paper Chain Kit Vintage Christmas',     3.36, 10604),
    ('Aged Glass Silver T-Light Holder',      0.82, 10583),
    ('Multi Colour Silver T-Light Holder',    0.95, 10557),
    ('Lunch Bag Pink Polkadot',               2.03, 10515),
    ('Strawberry Ceramic Trinket Box',        1.66, 10483),
]

# ── Embedded Walmart Weekly Seasonality (Store 1, normalized multipliers) ─────
# week 0 = first week of year, multiplier > 1 = above-average sales week
WALMART_WEEKLY = {
     0:0.9705,  1:0.9536,  2:0.9417,  3:1.1352,  4:1.0121,
     5:0.9631,  6:0.9875,  7:0.9659,  8:1.1786,  9:0.9862,
    10:0.9789, 11:1.0032, 12:0.9602, 13:1.0877, 14:0.9808,
    15:1.0012, 16:0.9868, 17:0.9792, 18:1.1424, 19:0.9493,
    20:0.9586, 21:0.9869, 22:1.0697, 23:1.0332, 24:0.9429,
    25:1.0565, 26:0.9638, 27:1.0944, 28:1.0175, 29:0.9777,
    30:0.9756, 31:0.9750, 32:1.0331, 33:0.9969, 34:0.9734,
    35:0.9559, 36:0.9674, 37:1.0162, 38:0.9231, 39:0.9862,
    40:0.9544, 41:1.0602, 42:1.0659, 43:0.9376, 44:0.9619,
    45:0.9688, 46:1.0240, 47:1.0334, 48:0.9905, 49:0.9670,
    50:0.9285, 51:0.9985,
}

# ── Category mapping ──────────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    'Home Decor':    ['T-LIGHT','CANDLE','HEART','FRAME','LAMP','LIGHT','ORNAMENT','BUNTING','SIGN','WICKER'],
    'Bags & Storage':['BAG','STORAGE','BOX','TIN','BASKET','SHOPPER'],
    'Kitchen':       ['JAR','CAKE','JAM','MUG','TEACUP','CAKESTAND','MOULD','NAPKIN'],
    'Stationery':    ['CARD','BOOK','PAPER','NOTEBOOK','CHAIN KIT','SNAP'],
    'Toys & Games':  ['TOY','GAME','DOLL','PAINT','HARMONICA','FLYTRAP'],
    'Lunch & Bags':  ['LUNCH','LUNCH BAG','LUNCH BOX'],
}

def guess_category(name):
    n = name.upper()
    for cat, keys in CATEGORY_KEYWORDS.items():
        if any(k in n for k in keys):
            return cat
    return 'General'

def round_inr(gbp):
    return max(15, round(gbp * GBP_TO_INR / 5) * 5)

# ── Build product list ────────────────────────────────────────────────────────
def build_products():
    random.seed(RANDOM_SEED)
    products = []
    max_qty = max(p[2] for p in RETAIL_PRODUCTS)
    for i, (name, gbp, total_qty) in enumerate(RETAIL_PRODUCTS):
        sale = round_inr(gbp)
        reorder = max(10, 60 - i)
        products.append({
            'sku': f'SKU{i+1:04d}',
            'name': name,
            'category': guess_category(name),
            'sale_price': sale,
            'reorder_point': reorder,
            'total_qty': total_qty,
            'max_qty': max_qty,
        })
    return products

# ── Generate daily sales ──────────────────────────────────────────────────────
def generate_sales(products):
    random.seed(RANDOM_SEED)
    start = datetime.today() - timedelta(days=DAYS_HISTORY)
    sales = []
    max_qty = products[0]['max_qty']

    for pid_idx, prod in enumerate(products):
        base_rate = max(0.3, (prod['total_qty'] / max_qty) * 40)
        for day in range(DAYS_HISTORY):
            date = start + timedelta(days=day)
            week_num = (date.timetuple().tm_yday // 7) % 52
            season   = WALMART_WEEKLY.get(week_num, 1.0)
            weekend  = 1.4 if date.weekday() >= 5 else 1.0
            noise    = random.gauss(1.0, 0.25)
            qty      = max(0, round(base_rate * season * weekend * noise))
            if qty > 0:
                if random.random() < 0.04:
                    qty *= random.randint(3, 8)
                sales.append((pid_idx, qty, date.strftime('%Y-%m-%d 10:00:00')))
    return sales

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print("  Smart Store — Embedded Dataset Import")
    print(f"{'='*55}")

    if not os.path.exists(DB_PATH):
        print(f"\n❌ Database not found: {DB_PATH}")
        print("   Pehle server ek baar chalao: python3 app.py")
        print("   Phir Ctrl+C se band karo, aur phir ye script chalao.")
        sys.exit(1)

    print(f"\n🔧 Building product catalog ({len(RETAIL_PRODUCTS)} products)...")
    products = build_products()
    from collections import Counter
    cats = Counter(p['category'] for p in products)
    for cat, cnt in sorted(cats.items()):
        print(f"   {cat}: {cnt} products")

    print(f"\n📊 Generating {DAYS_HISTORY} days of sales history...")
    sales = generate_sales(products)
    print(f"   ✓ {len(sales):,} sales transactions ready")

    print(f"\n💾 Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    print("\n🗑️  Clearing existing product/stock/sales/alert data...")
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM sales")
    conn.execute("DELETE FROM stock")
    conn.execute("DELETE FROM products")
    conn.execute("DELETE FROM locations WHERE name IN ('Store','Warehouse')")
    conn.commit()

    print("\n📍 Creating locations (Store + Warehouse)...")
    conn.execute("INSERT OR IGNORE INTO locations (name, location_type) VALUES ('Store','store')")
    conn.execute("INSERT OR IGNORE INTO locations (name, location_type) VALUES ('Warehouse','warehouse')")
    conn.commit()
    store_id = conn.execute("SELECT id FROM locations WHERE name='Store'").fetchone()['id']
    wh_id    = conn.execute("SELECT id FROM locations WHERE name='Warehouse'").fetchone()['id']
    print(f"   ✓ Store (id={store_id}), Warehouse (id={wh_id})")

    print(f"\n📦 Importing {len(products)} products...")
    prod_ids = []
    for p in products:
        cur = conn.execute(
            "INSERT INTO products (sku, name, category, sale_price, reorder_point) VALUES (?,?,?,?,?)",
            (p['sku'], p['name'], p['category'], p['sale_price'], p['reorder_point'])
        )
        prod_ids.append(cur.lastrowid)
    conn.commit()
    print(f"   ✓ Done")

    print("\n📦 Setting opening stock (Store + Warehouse)...")
    random.seed(RANDOM_SEED + 1)
    max_qty = products[0]['max_qty']
    for i, (prod, pid) in enumerate(zip(products, prod_ids)):
        rate = max(1, round((prod['total_qty'] / max_qty) * 40))
        # Every 4th product: low stock; every 7th: out of stock
        if i % 7 == 6:
            store_qty = 0                          # out of stock
        elif i % 4 == 3:
            store_qty = max(1, prod['reorder_point'] - random.randint(1, 5))  # below reorder
        else:
            store_qty = rate * random.randint(25, 45)
        wh_qty    = rate * random.randint(50, 120)
        conn.execute(
            "INSERT INTO stock (product_id, location_id, quantity) VALUES (?,?,?) "
            "ON CONFLICT(product_id, location_id) DO UPDATE SET quantity=excluded.quantity",
            (pid, store_id, store_qty)
        )
        conn.execute(
            "INSERT INTO stock (product_id, location_id, quantity) VALUES (?,?,?) "
            "ON CONFLICT(product_id, location_id) DO UPDATE SET quantity=excluded.quantity",
            (pid, wh_id, wh_qty)
        )
    conn.commit()
    print(f"   ✓ Stock set for {len(prod_ids)} products")

    print(f"\n💰 Importing {len(sales):,} sales transactions...")
    batch, total_rev = [], 0
    for (pid_idx, qty, created_at) in sales:
        pid   = prod_ids[pid_idx]
        price = products[pid_idx]['sale_price']
        total = qty * price
        total_rev += total
        batch.append((pid, store_id, qty, price, total, created_at))
        if len(batch) >= 5000:
            conn.executemany(
                "INSERT INTO sales (product_id,location_id,quantity,unit_price,total,created_at) VALUES (?,?,?,?,?,?)",
                batch
            )
            conn.commit(); batch.clear()
    if batch:
        conn.executemany(
            "INSERT INTO sales (product_id,location_id,quantity,unit_price,total,created_at) VALUES (?,?,?,?,?,?)",
            batch
        )
        conn.commit()
    print(f"   ✓ Done — Total revenue: ₹{total_rev:,.0f}")

    print("\n🔔 Generating stock alerts...")
    alert_count = 0
    for prod, pid in zip(products, prod_ids):
        sq = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) AS q FROM stock WHERE product_id=? AND location_id=?",
            (pid, store_id)
        ).fetchone()['q']
        if sq == 0:
            # Out of stock → alert_type = 'out_of_stock', severity = 'critical'
            conn.execute(
                "INSERT INTO alerts (product_id,alert_type,severity,message,status) VALUES (?,?,?,?,'open')",
                (pid, 'out_of_stock', 'critical',
                 f"Out of stock at Store: 0 units (min: {prod['reorder_point']})")
            )
            alert_count += 1
        elif sq <= prod['reorder_point']:
            # Low stock → alert_type = 'low_stock', severity = 'high'
            conn.execute(
                "INSERT INTO alerts (product_id,alert_type,severity,message,status) VALUES (?,?,?,?,'open')",
                (pid, 'low_stock', 'high',
                 f"Low stock at Store: {sq} units (min: {prod['reorder_point']})")
            )
            alert_count += 1
    conn.commit()
    conn.close()

    print(f"\n{'='*55}")
    print("  ✅ Import Complete!")
    print(f"{'='*55}")
    print(f"  Products  : {len(products)}")
    print(f"  Locations : Store + Warehouse")
    print(f"  Sales     : {len(sales):,} transactions ({DAYS_HISTORY} days)")
    print(f"  Revenue   : ₹{total_rev:,.0f}")
    print(f"  Alerts    : {alert_count}")
    print(f"\n  ▶  Server chalao : python3 app.py")
    print(f"  ▶  Login         : admin / admin123")
    print(f"{'='*55}\n")

if __name__ == '__main__':
    main()
