"""Business logic for the Smart Store backend MVP.

Rule-based only, on purpose: ML forecasting is intentionally out of scope
for this MVP (see app.py's /api/v1/ml/* routes).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any

SESSION_LIFETIME_HOURS = 12
VALID_ROLES = {"admin", "manager", "employee", "worker"}


class ServiceError(Exception):
    """Base class for errors that get turned into a JSON error response."""

    status = 400

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status


class ValidationError(ServiceError):
    status = 400


class NotFoundError(ServiceError):
    status = 404


def _require(body: dict, field: str) -> Any:
    value = body.get(field)
    if value is None or value == "":
        raise ValidationError(f"'{field}' is required.")
    return value


def _to_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"'{label}' must be an integer.")


def _to_number(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"'{label}' must be a number.")


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return digest.hex(), salt


def _verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = _hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


class StoreService:
    def __init__(self, db) -> None:
        self.db = db

    # ---- products ---------------------------------------------------
    def list_products(self) -> list[dict]:
        return self.db.query("SELECT * FROM products ORDER BY name")

    def update_product(self, product_id: int, body: dict) -> dict:
        existing = self.get_product(product_id)
        if not existing:
            raise NotFoundError(f"Product {product_id} not found.")
        fields, vals = [], []
        if "sale_price" in body:
            price = float(body["sale_price"])
            if price <= 0:
                raise ValidationError("sale_price must be greater than 0.")
            fields.append("sale_price = ?"); vals.append(price)
        if "reorder_point" in body:
            rp = int(body["reorder_point"])
            if rp < 0:
                raise ValidationError("reorder_point cannot be negative.")
            fields.append("reorder_point = ?"); vals.append(rp)
        if "name" in body:
            fields.append("name = ?"); vals.append(str(body["name"]).strip())
        if "category" in body:
            fields.append("category = ?"); vals.append(str(body["category"]).strip())
        if not fields:
            raise ValidationError("Nothing to update.")
        vals.append(product_id)
        self.db.execute(f"UPDATE products SET {', '.join(fields)} WHERE id = ?", vals)
        return self.get_product(product_id)

    def get_product(self, product_id: int) -> dict:
        product = self.db.query_one("SELECT * FROM products WHERE id = ?", (product_id,))
        if not product:
            raise NotFoundError(f"Product {product_id} not found.")
        return product

    def create_product(self, body: dict) -> dict:
        sku = _require(body, "sku")
        name = _require(body, "name")
        category = body.get("category") or None
        sale_price = _to_number(body.get("sale_price", 0), "sale_price")
        reorder_point = _to_int(body.get("reorder_point", 0), "reorder_point")
        if sale_price < 0:
            raise ValidationError("'sale_price' cannot be negative.")
        if reorder_point < 0:
            raise ValidationError("'reorder_point' cannot be negative.")
        try:
            cursor = self.db.execute(
                "INSERT INTO products (sku, name, category, sale_price, reorder_point) "
                "VALUES (?,?,?,?,?)",
                (sku, name, category, sale_price, reorder_point),
            )
        except sqlite3.IntegrityError as error:
            raise ValidationError(f"A product with SKU '{sku}' already exists.") from error
        return self.get_product(cursor.lastrowid)

    # ---- locations ----------------------------------------------------
    def list_locations(self) -> list[dict]:
        return self.db.query("SELECT * FROM locations ORDER BY name")

    def _get_location(self, location_id: int) -> dict:
        location = self.db.query_one("SELECT * FROM locations WHERE id = ?", (location_id,))
        if not location:
            raise NotFoundError(f"Location {location_id} not found.")
        return location

    def create_location(self, body: dict) -> dict:
        name = _require(body, "name")
        location_type = str(body.get("location_type") or "store").strip().lower()
        if location_type not in ("store", "warehouse"):
            raise ValidationError("'location_type' must be 'store' or 'warehouse'.")
        address = body.get("address") or None
        cursor = self.db.execute(
            "INSERT INTO locations (name, location_type, address) VALUES (?,?,?)",
            (name, location_type, address),
        )
        return self._get_location(cursor.lastrowid)

    # ---- stock ----------------------------------------------------------
    def list_stock(self, product_id: int | None = None, location_id: int | None = None) -> list[dict]:
        sql = (
            "SELECT s.product_id, s.location_id, s.quantity, l.location_type, "
            "l.name AS location_name, p.name AS product_name "
            "FROM stock s "
            "JOIN locations l ON l.id = s.location_id "
            "JOIN products p ON p.id = s.product_id "
            "WHERE 1=1"
        )
        params: list[Any] = []
        if product_id is not None:
            sql += " AND s.product_id = ?"
            params.append(product_id)
        if location_id is not None:
            sql += " AND s.location_id = ?"
            params.append(location_id)
        sql += " ORDER BY p.name, l.name"
        return self.db.query(sql, params)

    def adjust_stock(self, body: dict) -> dict:
        product_id = _to_int(_require(body, "product_id"), "product_id")
        location_id = _to_int(_require(body, "location_id"), "location_id")
        quantity = _to_int(_require(body, "quantity"), "quantity")
        if quantity < 0:
            raise ValidationError("'quantity' cannot be negative.")
        self.get_product(product_id)
        self._get_location(location_id)
        self.db.execute(
            "INSERT INTO stock (product_id, location_id, quantity) VALUES (?,?,?) "
            "ON CONFLICT(product_id, location_id) DO UPDATE SET quantity = excluded.quantity",
            (product_id, location_id, quantity),
        )
        self._refresh_stock_alerts(product_id)
        return self.db.query_one(
            "SELECT product_id, location_id, quantity FROM stock WHERE product_id = ? AND location_id = ?",
            (product_id, location_id),
        )

    # ---- sales ------------------------------------------------------------
    def list_sales(self, limit: int = 100) -> list[dict]:
        return self.db.query(
            "SELECT s.id, s.product_id, s.location_id, s.quantity, s.unit_price, s.total, s.created_at "
            "FROM sales s ORDER BY s.id DESC LIMIT ?", (limit,)
        )

    def record_sale(self, body: dict) -> dict:
        product_id = _to_int(_require(body, "product_id"), "product_id")
        location_id = _to_int(_require(body, "location_id"), "location_id")
        quantity = _to_int(_require(body, "quantity"), "quantity")
        if quantity <= 0:
            raise ValidationError("'quantity' must be positive.")
        product = self.get_product(product_id)
        location = self._get_location(location_id)
        if location["location_type"] != "store":
            raise ValidationError("Sales can only be recorded at a store location.")
        unit_price = _to_number(body.get("unit_price", product["sale_price"]), "unit_price")
        if unit_price < 0:
            raise ValidationError("'unit_price' cannot be negative.")
        current = self.db.query_one(
            "SELECT quantity FROM stock WHERE product_id = ? AND location_id = ?",
            (product_id, location_id),
        )
        available = current["quantity"] if current else 0
        if available < quantity:
            raise ValidationError(
                f"Only {available} unit(s) of '{product['name']}' available at this location."
            )
        self.db.execute(
            "UPDATE stock SET quantity = quantity - ? WHERE product_id = ? AND location_id = ?",
            (quantity, product_id, location_id),
        )
        total = round(unit_price * quantity, 2)
        cursor = self.db.execute(
            "INSERT INTO sales (product_id, location_id, quantity, unit_price, total) VALUES (?,?,?,?,?)",
            (product_id, location_id, quantity, unit_price, total),
        )
        self._refresh_stock_alerts(product_id)
        return self.db.query_one("SELECT * FROM sales WHERE id = ?", (cursor.lastrowid,))

    # ---- transfers --------------------------------------------------------
    def list_transfers(self) -> list[dict]:
        return self.db.query(
            "SELECT t.*, p.name AS product_name, "
            "sl.name AS source_location_name, dl.name AS destination_location_name "
            "FROM transfers t "
            "JOIN products p ON p.id = t.product_id "
            "JOIN locations sl ON sl.id = t.source_location_id "
            "JOIN locations dl ON dl.id = t.destination_location_id "
            "ORDER BY t.created_at DESC"
        )

    def create_transfer(self, body: dict) -> dict:
        product_id = _to_int(_require(body, "product_id"), "product_id")
        source_id = _to_int(_require(body, "source_location_id"), "source_location_id")
        destination_id = _to_int(_require(body, "destination_location_id"), "destination_location_id")
        quantity = _to_int(_require(body, "quantity"), "quantity")
        if quantity <= 0:
            raise ValidationError("'quantity' must be positive.")
        if source_id == destination_id:
            raise ValidationError("Source and destination locations must be different.")
        self.get_product(product_id)
        self._get_location(source_id)
        self._get_location(destination_id)
        current = self.db.query_one(
            "SELECT quantity FROM stock WHERE product_id = ? AND location_id = ?",
            (product_id, source_id),
        )
        available = current["quantity"] if current else 0
        if available < quantity:
            raise ValidationError(f"Only {available} unit(s) available at the source location.")
        cursor = self.db.execute(
            "INSERT INTO transfers (product_id, source_location_id, destination_location_id, quantity) "
            "VALUES (?,?,?,?)",
            (product_id, source_id, destination_id, quantity),
        )
        return self.db.query_one("SELECT * FROM transfers WHERE id = ?", (cursor.lastrowid,))

    def complete_transfer(self, transfer_id: int) -> dict:
        transfer = self.db.query_one("SELECT * FROM transfers WHERE id = ?", (transfer_id,))
        if not transfer:
            raise NotFoundError(f"Transfer {transfer_id} not found.")
        if transfer["status"] != "pending":
            raise ValidationError(f"Transfer {transfer_id} is already {transfer['status']}.")
        current = self.db.query_one(
            "SELECT quantity FROM stock WHERE product_id = ? AND location_id = ?",
            (transfer["product_id"], transfer["source_location_id"]),
        )
        available = current["quantity"] if current else 0
        if available < transfer["quantity"]:
            raise ValidationError("Source location no longer has enough stock to complete this transfer.")
        self.db.execute(
            "UPDATE stock SET quantity = quantity - ? WHERE product_id = ? AND location_id = ?",
            (transfer["quantity"], transfer["product_id"], transfer["source_location_id"]),
        )
        self.db.execute(
            "INSERT INTO stock (product_id, location_id, quantity) VALUES (?,?,?) "
            "ON CONFLICT(product_id, location_id) DO UPDATE SET quantity = quantity + excluded.quantity",
            (transfer["product_id"], transfer["destination_location_id"], transfer["quantity"]),
        )
        self.db.execute(
            "UPDATE transfers SET status = 'completed', completed_at = datetime('now') WHERE id = ?",
            (transfer_id,),
        )
        self._refresh_stock_alerts(transfer["product_id"])
        return self.db.query_one("SELECT * FROM transfers WHERE id = ?", (transfer_id,))

    # ---- suppliers ------------------------------------------------------
    def list_suppliers(self) -> list[dict]:
        return self.db.query("SELECT * FROM suppliers ORDER BY name")

    def create_supplier(self, body: dict) -> dict:
        name = _require(body, "name")
        contact_name = body.get("contact_name") or None
        email = body.get("email") or None
        lead_time_days = _to_int(body.get("lead_time_days", 3), "lead_time_days")
        if lead_time_days < 0:
            raise ValidationError("'lead_time_days' cannot be negative.")
        cursor = self.db.execute(
            "INSERT INTO suppliers (name, contact_name, email, lead_time_days) VALUES (?,?,?,?)",
            (name, contact_name, email, lead_time_days),
        )
        return self.db.query_one("SELECT * FROM suppliers WHERE id = ?", (cursor.lastrowid,))

    # ---- purchase requests ------------------------------------------------
    def list_purchase_requests(self) -> list[dict]:
        return self.db.query(
            "SELECT pr.*, s.name AS supplier_name, p.name AS product_name, "
            "l.name AS destination_location_name "
            "FROM purchase_requests pr "
            "JOIN suppliers s ON s.id = pr.supplier_id "
            "JOIN products p ON p.id = pr.product_id "
            "JOIN locations l ON l.id = pr.destination_location_id "
            "ORDER BY pr.created_at DESC"
        )

    def create_purchase_request(self, body: dict) -> dict:
        supplier_id = _to_int(_require(body, "supplier_id"), "supplier_id")
        product_id = _to_int(_require(body, "product_id"), "product_id")
        destination_id = _to_int(_require(body, "destination_location_id"), "destination_location_id")
        quantity = _to_int(_require(body, "quantity"), "quantity")
        if quantity <= 0:
            raise ValidationError("'quantity' must be positive.")
        supplier = self.db.query_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        if not supplier:
            raise NotFoundError(f"Supplier {supplier_id} not found.")
        self.get_product(product_id)
        self._get_location(destination_id)
        cursor = self.db.execute(
            "INSERT INTO purchase_requests (supplier_id, product_id, destination_location_id, quantity) "
            "VALUES (?,?,?,?)",
            (supplier_id, product_id, destination_id, quantity),
        )
        return self.db.query_one("SELECT * FROM purchase_requests WHERE id = ?", (cursor.lastrowid,))

    # ---- alerts -------------------------------------------------------------
    def list_alerts(self, status: str = "open") -> list[dict]:
        sql = (
            "SELECT a.*, p.name AS product_name, COALESCE(l.name, 'All Stores') AS location_name "
            "FROM alerts a "
            "JOIN products p ON p.id = a.product_id "
            "LEFT JOIN locations l ON l.id = a.location_id "
        )
        params: list[Any] = []
        if status and status != "all":
            sql += "WHERE a.status = ? "
            params.append(status)
        sql += "ORDER BY a.created_at DESC"
        return self.db.query(sql, params)

    def resolve_alert(self, alert_id: int) -> dict:
        alert = self.db.query_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        if not alert:
            raise NotFoundError(f"Alert {alert_id} not found.")
        self.db.execute(
            "UPDATE alerts SET status = 'resolved', resolved_at = datetime('now') WHERE id = ?",
            (alert_id,),
        )
        return self.db.query_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))

    def _refresh_stock_alerts(self, product_id: int) -> None:
        """Auto-open/resolve low-stock & out-of-stock alerts for a product's store stock."""
        product = self.get_product(product_id)
        store_total = self.db.query_one(
            "SELECT COALESCE(SUM(s.quantity), 0) AS total FROM stock s "
            "JOIN locations l ON l.id = s.location_id "
            "WHERE s.product_id = ? AND l.location_type = 'store'",
            (product_id,),
        )["total"]
        open_alert = self.db.query_one(
            "SELECT * FROM alerts WHERE product_id = ? AND alert_type IN ('low_stock','out_of_stock') "
            "AND status = 'open'",
            (product_id,),
        )

        def _resolve_open() -> None:
            if open_alert:
                self.db.execute(
                    "UPDATE alerts SET status = 'resolved', resolved_at = datetime('now') WHERE id = ?",
                    (open_alert["id"],),
                )

        if store_total <= 0:
            if open_alert and open_alert["alert_type"] == "out_of_stock":
                return
            _resolve_open()
            self.db.execute(
                "INSERT INTO alerts (product_id, alert_type, severity, message) VALUES (?,?,?,?)",
                (product_id, "out_of_stock", "critical", f"{product['name']} is out of stock in-store."),
            )
        elif store_total <= product["reorder_point"]:
            if open_alert and open_alert["alert_type"] == "low_stock":
                return
            _resolve_open()
            self.db.execute(
                "INSERT INTO alerts (product_id, alert_type, severity, message) VALUES (?,?,?,?)",
                (
                    product_id,
                    "low_stock",
                    "warning",
                    f"{product['name']} is low in-store ({store_total} left, reorder at {product['reorder_point']}).",
                ),
            )
        else:
            _resolve_open()

    # ---- dashboard / analytics / recommendations ---------------------------
    def dashboard(self) -> dict:
        product_count = self.db.query_one("SELECT COUNT(*) AS n FROM products")["n"]
        sales_today = self.db.query_one(
            "SELECT COALESCE(SUM(total), 0) AS total FROM sales WHERE date(created_at) = date('now')"
        )["total"]
        low_stock_count = self.db.query_one(
            "SELECT COUNT(*) AS n FROM ("
            "  SELECT p.id, "
            "    COALESCE(SUM(CASE WHEN l.location_type = 'store' THEN s.quantity ELSE 0 END), 0) AS total "
            "  FROM products p "
            "  LEFT JOIN stock s ON s.product_id = p.id "
            "  LEFT JOIN locations l ON l.id = s.location_id "
            "  GROUP BY p.id "
            "  HAVING total > 0 AND total <= p.reorder_point"
            ")"
        )["n"]
        critical_alert_count = self.db.query_one(
            "SELECT COUNT(*) AS n FROM alerts WHERE status = 'open' AND severity = 'critical'"
        )["n"]
        return {
            "product_count": product_count,
            "sales_today": round(sales_today, 2),
            "low_stock_count": low_stock_count,
            "critical_alert_count": critical_alert_count,
        }

    def sales_trend(self, days: int = 7) -> list[dict]:
        """Real daily sales totals for the last N days, zero-filled for days with no sales."""
        days = max(1, min(int(days), 90))
        rows = self.db.query(
            "SELECT date(created_at) AS day, SUM(total) AS total FROM sales "
            "WHERE created_at >= datetime('now', ?) GROUP BY day",
            (f"-{days} days",),
        )
        by_day = {r["day"]: r["total"] for r in rows}
        today = datetime.utcnow().date()
        result = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            result.append({"date": key, "total": round(by_day.get(key) or 0, 2)})
        return result

    def best_sellers(self, days: int = 30) -> list[dict]:
        return self.db.query(
            "SELECT p.id AS product_id, p.name, SUM(s.quantity) AS units_sold, SUM(s.total) AS revenue "
            "FROM sales s JOIN products p ON p.id = s.product_id "
            "WHERE s.created_at >= datetime('now', ?) "
            "GROUP BY p.id ORDER BY units_sold DESC LIMIT 10",
            (f"-{int(days)} days",),
        )

    def slow_movers(self, days: int = 30) -> list[dict]:
        return self.db.query(
            "SELECT p.id AS product_id, p.name, COALESCE(SUM(s.quantity), 0) AS units_sold "
            "FROM products p LEFT JOIN sales s "
            "  ON s.product_id = p.id AND s.created_at >= datetime('now', ?) "
            "GROUP BY p.id ORDER BY units_sold ASC LIMIT 10",
            (f"-{int(days)} days",),
        )

    def stock_health(self) -> list[dict]:
        rows = self.db.query(
            "SELECT p.id AS product_id, p.name, p.reorder_point, "
            "COALESCE(SUM(CASE WHEN l.location_type = 'store' THEN s.quantity ELSE 0 END), 0) AS store_quantity, "
            "COALESCE(SUM(CASE WHEN l.location_type = 'warehouse' THEN s.quantity ELSE 0 END), 0) AS warehouse_quantity "
            "FROM products p "
            "LEFT JOIN stock s ON s.product_id = p.id "
            "LEFT JOIN locations l ON l.id = s.location_id "
            "GROUP BY p.id ORDER BY p.name"
        )
        for row in rows:
            if row["store_quantity"] <= 0:
                row["status"] = "out_of_stock"
            elif row["store_quantity"] <= row["reorder_point"]:
                row["status"] = "low_stock"
            else:
                row["status"] = "normal"
        return rows

    def recommendations(self) -> list[dict]:
        items = []
        for row in self.stock_health():
            if row["status"] == "normal":
                continue
            needed = max(row["reorder_point"] - row["store_quantity"], row["reorder_point"] or 1)
            if row["warehouse_quantity"] > 0 and row["warehouse_quantity"] >= needed:
                items.append(
                    {
                        "action": "transfer",
                        "product_id": row["product_id"],
                        "product_name": row["name"],
                        "reason": (
                            f"Store has {row['store_quantity']} left; warehouse has "
                            f"{row['warehouse_quantity']} available to transfer."
                        ),
                    }
                )
            else:
                items.append(
                    {
                        "action": "purchase",
                        "product_id": row["product_id"],
                        "product_name": row["name"],
                        "reason": (
                            f"Store has {row['store_quantity']} left and warehouse stock is "
                            "insufficient; reorder recommended."
                        ),
                    }
                )
        return items

    # ---- users & authentication -------------------------------------------
    def list_users(self) -> list[dict]:
        return self.db.query(
            "SELECT id, username, full_name, role, created_at FROM users ORDER BY username"
        )

    def create_user(self, body: dict) -> dict:
        username = str(_require(body, "username")).strip().lower()
        password = str(_require(body, "password"))
        role = str(body.get("role") or "employee").strip().lower()
        full_name = body.get("full_name") or None
        if role not in VALID_ROLES:
            raise ValidationError("'role' must be one of: admin, manager, employee, worker.")
        if len(password) < 6:
            raise ValidationError("Password must be at least 6 characters.")
        password_hash, salt = _hash_password(password)
        try:
            cursor = self.db.execute(
                "INSERT INTO users (username, full_name, role, password_hash, password_salt) "
                "VALUES (?,?,?,?,?)",
                (username, full_name, role, password_hash, salt),
            )
        except sqlite3.IntegrityError as error:
            raise ValidationError(f"Username '{username}' is already taken.") from error
        return self.db.query_one(
            "SELECT id, username, full_name, role, created_at FROM users WHERE id = ?",
            (cursor.lastrowid,),
        )

    def authenticate(self, username: str, password: str) -> dict:
        username = (username or "").strip().lower()
        if not username or not password:
            raise ValidationError("Username and password are required.", status=400)
        user = self.db.query_one("SELECT * FROM users WHERE username = ?", (username,))
        if not user or not _verify_password(password, user["password_hash"], user["password_salt"]):
            raise ValidationError("Invalid username or password.", status=401)
        token = secrets.token_hex(32)
        expires_at = (datetime.utcnow() + timedelta(hours=SESSION_LIFETIME_HOURS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.db.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
            (token, user["id"], expires_at),
        )
        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
            },
        }

    def current_user(self, token: str | None) -> dict | None:
        if not token:
            return None
        row = self.db.query_one(
            "SELECT u.id, u.username, u.full_name, u.role, s.expires_at FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        )
        if not row:
            return None
        if row["expires_at"] < datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
            self.db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        return row

    def logout(self, token: str | None) -> None:
        if token:
            self.db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        user = self.db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if not user:
            raise NotFoundError("User not found.")
        if not _verify_password(current_password, user["password_hash"], user["password_salt"]):
            raise ValidationError("Current password is incorrect.", status=401)
        if len(new_password) < 6:
            raise ValidationError("New password must be at least 6 characters.")
        password_hash, salt = _hash_password(new_password)
        self.db.execute(
            "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
            (password_hash, salt, user_id),
        )
        # Invalidate other sessions so old password can no longer be used anywhere.
        self.db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def ensure_default_admin(self) -> None:
        """Seed starter accounts for all 4 roles the first time the database is empty."""
        count = self.db.query_one("SELECT COUNT(*) AS n FROM users")["n"]
        if count == 0:
            defaults = [
                {"username": "admin",    "password": "admin123",    "role": "admin",    "full_name": "Administrator"},
                {"username": "manager",  "password": "manager123",  "role": "manager",  "full_name": "Store Manager"},
                {"username": "employee", "password": "employee123", "role": "employee", "full_name": "Sales Employee"},
                {"username": "worker",   "password": "worker123",   "role": "worker",   "full_name": "Warehouse Worker"},
            ]
            for u in defaults:
                self.create_user(u)
