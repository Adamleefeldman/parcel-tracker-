"""Per-resource route modules. Import routers from here."""

from app.api.routes.admin import admin_router
from app.api.routes.auth import auth_router
from app.api.routes.bl import bl_router
from app.api.routes.bookings import booking_router
from app.api.routes.clearing import clearing_router
from app.api.routes.containers import container_router
from app.api.routes.currencies import currency_router
from app.api.routes.customer_payments import customer_payment_router
from app.api.routes.customs import customs_router
from app.api.routes.delivery import delivery_router
from app.api.routes.documents import doc_router
from app.api.routes.fx_rates import fx_rate_router
from app.api.routes.invoices import invoice_router
from app.api.routes.money_risk import money_risk_router
from app.api.routes.notifications import notif_router
from app.api.routes.parties import broker_router, company_router
from app.api.routes.po import po_router
from app.api.routes.port_templates import port_template_router
from app.api.routes.shipment_legs import shipment_leg_router
from app.api.routes.supplier_payments import payment_router
from app.api.routes.vessels import vessel_router

__all__ = [
    "admin_router",
    "auth_router",
    "bl_router",
    "booking_router",
    "broker_router",
    "clearing_router",
    "company_router",
    "container_router",
    "currency_router",
    "customer_payment_router",
    "customs_router",
    "delivery_router",
    "doc_router",
    "fx_rate_router",
    "invoice_router",
    "money_risk_router",
    "notif_router",
    "payment_router",
    "po_router",
    "port_template_router",
    "shipment_leg_router",
    "vessel_router",
]
