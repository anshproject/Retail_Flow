"""Dependency-free JSON HTTP API for the Smart Store backend MVP."""

from __future__ import annotations

import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:  # Works when run as part of a package: `python -m backend.app`
    from .database import Database
    from .services import NotFoundError, ServiceError, StoreService, ValidationError
except ImportError:  # Works when run directly: `python app.py`
    from database import Database
    from services import NotFoundError, ServiceError, StoreService, ValidationError


MAX_BODY_BYTES = 1_000_000


def _find_static_dir() -> Path:
    """Locate the folder containing index.html, trying common layouts.

    Falls back to the directory next to app.py if nothing else matches,
    so a misconfigured layout fails with a clear 404 instead of a silent
    'every page 404s' bug.
    """
    here = Path(__file__).resolve().parent
    env_override = os.getenv("SMART_STORE_FRONTEND")
    candidates = [
        Path(env_override) if env_override else None,
        here.parent / "frontend",  # project/backend/app.py + project/frontend/
        here / "frontend",         # app.py + ./frontend/
        here,                       # index.html next to app.py
    ]
    for candidate in candidates:
        if candidate and (candidate / "index.html").is_file():
            return candidate.resolve()
    # Nothing found; default to parent/frontend so the error is obvious in logs.
    return (here.parent / "frontend").resolve()


STATIC_DIR = _find_static_dir()
WRITE_ROLES = {
    "products":  {"admin", "manager"},
    "locations": {"admin", "manager"},
    "stock":     {"admin", "manager", "employee"},
    "sales":     {"admin", "manager", "employee"},
    "transfers": {"admin", "manager"},
    "suppliers": {"admin", "manager"},
    "purchases": {"admin", "manager"},
    "alerts":    {"admin", "manager"},
    "users":     {"admin"},
}
# Roles allowed to READ each area (worker = read-only stock views)
READ_ROLES = {
    "stock":   {"admin", "manager", "employee", "worker"},
    "default": {"admin", "manager", "employee"},
}
PUBLIC_API_PATHS = {"/api/v1", "/api/v1/auth/login"}


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SmartStoreAPI/1.0"

    @property
    def service(self) -> StoreService:
        return self.server.service  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, status: int, body: object) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_frontend(self, path: str) -> None:
        """Serve the bundled single-page application without exposing other files."""
        requested = "index.html" if path == "/" else unquote(path.lstrip("/"))
        candidate = (STATIC_DIR / requested).resolve()
        static_root = STATIC_DIR.resolve()
        if not candidate.is_relative_to(static_root) or not candidate.is_file():
            raise NotFoundError("Page or asset not found.")
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            raise ValidationError("Request body is too large.")
        if length == 0:
            return {}
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("Request body must be valid JSON.") from error
        if not isinstance(body, dict):
            raise ValidationError("Request body must be a JSON object.")
        return body

    def _current_user(self) -> dict | None:
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        return self.service.current_user(token)

    def _require_role(self, capability: str, user: dict | None) -> dict:
        if not user:
            raise ServiceError("Authentication required. Please log in.", status=401)
        if user["role"] not in WRITE_ROLES[capability]:
            raise ServiceError(f"Role '{user['role']}' cannot perform this action.", status=403)
        return user

    @staticmethod
    def _integer(value: str | None, label: str) -> int:
        try:
            parsed = int(value or "")
        except ValueError as error:
            raise ValidationError(f"'{label}' must be an integer.") from error
        if parsed <= 0:
            raise ValidationError(f"'{label}' must be positive.")
        return parsed

    def _handle(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            if path == "/health":
                return self._send_json(200, {"status": "ok"})
            if path == "/api/v1":
                return self._send_json(200, {"message": "Smart Store backend API", "ml": "Coming Soon"})
            if self.command == "GET" and (path == "/" or not path.startswith("/api/")):
                return self._serve_frontend(path)
            if not path.startswith("/api/v1/"):
                raise NotFoundError("Route not found.")

            user = None
            if path not in PUBLIC_API_PATHS:
                user = self._current_user()
                if not user:
                    raise ServiceError("Authentication required. Please log in.", status=401)

            if path == "/api/v1/auth/login" and self.command == "POST":
                body = self._body()
                return self._send_json(200, self.service.authenticate(body.get("username", ""), body.get("password", "")))

            if path == "/api/v1/auth/logout" and self.command == "POST":
                auth = self.headers.get("Authorization", "")
                token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
                self.service.logout(token)
                return self._send_json(200, {"status": "logged_out"})

            if path == "/api/v1/auth/change-password" and self.command == "POST":
                body = self._body()
                self.service.change_password(
                    user["id"], body.get("current_password", ""), body.get("new_password", "")
                )
                return self._send_json(200, {"status": "password_changed"})

            if path == "/api/v1/auth/me" and self.command == "GET":
                return self._send_json(200, {"user": {k: user[k] for k in ("id", "username", "full_name", "role")}})

            if path == "/api/v1/users":
                if self.command == "GET":
                    self._require_role("users", user)
                    return self._send_json(200, {"items": self.service.list_users()})
                self._require_role("users", user)
                return self._send_json(201, self.service.create_user(self._body()))

            if path == "/api/v1/products":
                if self.command == "GET":
                    return self._send_json(200, {"items": self.service.list_products()})
                self._require_role("products", user)
                return self._send_json(201, self.service.create_product(self._body()))

            product_match = re.fullmatch(r"/api/v1/products/(\d+)", path)
            if product_match and self.command == "GET":
                return self._send_json(200, self.service.get_product(int(product_match.group(1))))
            if product_match and self.command == "POST":
                self._require_role("products", user)
                return self._send_json(200, self.service.update_product(int(product_match.group(1)), self._body()))

            if path == "/api/v1/locations":
                if self.command == "GET":
                    return self._send_json(200, {"items": self.service.list_locations()})
                self._require_role("locations", user)
                return self._send_json(201, self.service.create_location(self._body()))

            if path == "/api/v1/stock":
                if self.command == "GET":
                    product_id = int(query["product_id"][0]) if "product_id" in query else None
                    location_id = int(query["location_id"][0]) if "location_id" in query else None
                    return self._send_json(200, {"items": self.service.list_stock(product_id, location_id)})
                self._require_role("stock", user)
                return self._send_json(200, self.service.adjust_stock(self._body()))

            if path == "/api/v1/sales":
                if self.command == "GET":
                    limit = int(query.get("limit", ["100"])[0])
                    return self._send_json(200, {"items": self.service.list_sales(limit)})
                self._require_role("sales", user)
                return self._send_json(201, self.service.record_sale(self._body()))

            if path == "/api/v1/transfers":
                if self.command == "GET":
                    return self._send_json(200, {"items": self.service.list_transfers()})
                self._require_role("transfers", user)
                return self._send_json(201, self.service.create_transfer(self._body()))

            transfer_match = re.fullmatch(r"/api/v1/transfers/(\d+)/complete", path)
            if transfer_match and self.command == "POST":
                self._require_role("transfers", user)
                return self._send_json(200, self.service.complete_transfer(int(transfer_match.group(1))))

            if path == "/api/v1/suppliers":
                if self.command == "GET":
                    return self._send_json(200, {"items": self.service.list_suppliers()})
                self._require_role("suppliers", user)
                return self._send_json(201, self.service.create_supplier(self._body()))

            if path == "/api/v1/purchase-requests":
                if self.command == "GET":
                    return self._send_json(200, {"items": self.service.list_purchase_requests()})
                self._require_role("purchases", user)
                return self._send_json(201, self.service.create_purchase_request(self._body()))

            if path == "/api/v1/alerts" and self.command == "GET":
                return self._send_json(200, {"items": self.service.list_alerts(query.get("status", ["open"])[0])})

            alert_match = re.fullmatch(r"/api/v1/alerts/(\d+)/resolve", path)
            if alert_match and self.command == "POST":
                self._require_role("alerts", user)
                return self._send_json(200, self.service.resolve_alert(int(alert_match.group(1))))

            if path == "/api/v1/dashboard" and self.command == "GET":
                return self._send_json(200, self.service.dashboard())

            if path == "/api/v1/analytics/best-sellers" and self.command == "GET":
                days = int(query.get("days", ["30"])[0])
                return self._send_json(200, {"items": self.service.best_sellers(days)})

            if path == "/api/v1/analytics/sales-trend" and self.command == "GET":
                days = int(query.get("days", ["7"])[0])
                return self._send_json(200, {"items": self.service.sales_trend(days)})

            if path == "/api/v1/analytics/slow-movers" and self.command == "GET":
                days = int(query.get("days", ["30"])[0])
                return self._send_json(200, {"items": self.service.slow_movers(days)})

            if path == "/api/v1/analytics/stock-health" and self.command == "GET":
                return self._send_json(200, {"items": self.service.stock_health()})

            if path == "/api/v1/recommendations" and self.command == "GET":
                return self._send_json(200, {"items": self.service.recommendations(), "engine": "rule-based"})

            if path in {"/api/v1/ml/status", "/api/v1/ml/forecast", "/api/v1/ml/stockout-prediction"}:
                return self._send_json(501, {
                    "status": "coming_soon",
                    "message": "ML forecasting and stockout prediction are planned for a future release. This MVP uses transparent rule-based recommendations only.",
                })
            raise NotFoundError("Route not found.")
        except ServiceError as error:
            self._send_json(error.status, {"error": str(error)})
        except ValueError:
            self._send_json(400, {"error": "Query parameters must use valid values."})
        except Exception:  # Keep internal details out of client responses.
            self.log_error("Unhandled server error", exc_info=True)
            self._send_json(500, {"error": "Internal server error."})


def run() -> None:
    database_path = Path(os.getenv("SMART_STORE_DB", "smart_store.sqlite3"))
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), ApiHandler)
    server.service = StoreService(Database(database_path))  # type: ignore[attr-defined]
    server.service.ensure_default_admin()  # type: ignore[attr-defined]
    if not (STATIC_DIR / "index.html").is_file():
        print(f"WARNING: no index.html found under {STATIC_DIR} — the frontend will 404.")
    print(f"Smart Store backend running at http://127.0.0.1:{port}")
    print(f"Serving frontend from {STATIC_DIR}")
    print("Default admin login (change after first sign-in): admin / admin123")
    print("ML endpoints are intentionally Coming Soon.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
