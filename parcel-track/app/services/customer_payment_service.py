"""Customer payment service — inbound GBP payments against a Container.

Mirrors the trading-tracker spreadsheet's payment columns. Supports the
multi-tranche pattern (one container can take several deposits across days)
and the outbound-invoice-reference batch tag (one outbound invoice covering
multiple containers — full outbound invoice entity deferred).

Lifecycle hook: per the deferred P0.4 plan, when cumulative banked_total
covers the agreed container sale_price_total, the container's
lifecycle_status would advance to BANKED. P0.3 only writes the rows; the
lifecycle wiring lands in P0.4.
"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CustomerPaymentMethod, UserRole
from app.db.models import CustomerPayment, User
from app.middleware.auth import financial_fields_allowed
from app.schemas.pagination import PaginationParams, paginate
from app.schemas.schemas import CustomerPaymentCreate, CustomerPaymentOut
from app.services.container_lifecycle_service import ContainerLifecycleService
from app.services.container_service import ContainerService

# Money / bank-detail fields on a customer-payment record that only admins may
# see. These names are specific to CustomerPaymentOut, so we mask them here
# rather than in BookingService.mask_financials (whose hardcoded key set is
# shared with PO / Invoice / supplier-payment serialisation and must not grow
# field names that could accidentally null unrelated entities).
CUSTOMER_PAYMENT_FINANCIAL_FIELDS = frozenset(
    {
        "amount_received",
        "variance",
        "expense_courier",
        "expense_bank_charge",
        "banked_total",
        "sender_bank",
        "receiver_bank",
    }
)

# Aggregate money totals that roll up the per-tranche financial fields above.
CUSTOMER_PAYMENT_AGGREGATE_FINANCIAL_FIELDS = frozenset(
    {
        "total_received",
        "total_variance",
        "total_expenses",
        "total_banked",
    }
)


def _mask_payment_fields(obj: dict[str, Any], keys: frozenset[str], show: bool) -> dict[str, Any]:
    """Null the financial ``keys`` in ``obj`` when ``show`` is False (non-admin)."""
    if show:
        return obj
    return {k: (None if k in keys else v) for k, v in obj.items()}


class CustomerPaymentService:
    @staticmethod
    async def add(
        db: AsyncSession,
        booking_id: uuid.UUID,
        container_id: uuid.UUID,
        body: CustomerPaymentCreate,
        actor: User,
    ) -> CustomerPayment:
        if actor.role != UserRole.ADMIN:
            raise HTTPException(403, "Only admin can record customer payments")

        # Confirm the container exists AND belongs to the booking in the URL —
        # otherwise a payment could be recorded against an unrelated booking's
        # container (wrong ledger + wrong lifecycle recompute).
        await ContainerService.get_in_booking(db, booking_id, container_id)

        payload = body.model_dump()
        # The schema accepts the method as a string; convert to enum.
        payload["method"] = CustomerPaymentMethod(payload["method"])

        payment = CustomerPayment(container_id=container_id, **payload)
        db.add(payment)
        await db.flush()
        # Recompute lifecycle: the new tranche may advance the container to
        # INVOICED / PAID / BANKED depending on its fields and the cumulative
        # banked vs sale_price_total threshold.
        await ContainerLifecycleService.recompute(db, container_id)
        return payment

    @staticmethod
    async def aggregate_for_container(
        db: AsyncSession,
        booking_id: uuid.UUID,
        container_id: uuid.UUID,
        actor: User,
    ) -> dict[str, Any]:
        """Return totals across all tranches for one container.

        Used by the container detail view and any A/R aging logic that wants
        a clean "is this container paid?" signal. The money totals are masked
        to None for non-admins; ``tranche_count`` stays visible to everyone.
        """
        await ContainerService.get_in_booking(db, booking_id, container_id)
        rows_q = await db.execute(
            select(CustomerPayment)
            .where(CustomerPayment.container_id == container_id)
            .order_by(CustomerPayment.tranche_index, CustomerPayment.created_at)
        )
        tranches = list(rows_q.scalars().all())

        sum_q = await db.execute(
            select(
                func.coalesce(func.sum(CustomerPayment.amount_received), 0),
                func.coalesce(func.sum(CustomerPayment.variance), 0),
                func.coalesce(func.sum(CustomerPayment.expense_courier), 0)
                + func.coalesce(func.sum(CustomerPayment.expense_bank_charge), 0),
                func.coalesce(func.sum(CustomerPayment.banked_total), 0),
            ).where(CustomerPayment.container_id == container_id)
        )
        total_received, total_variance, total_expenses, total_banked = sum_q.one()

        agg: dict[str, Any] = {
            "total_received": Decimal(total_received),
            "total_variance": Decimal(total_variance),
            "total_expenses": Decimal(total_expenses),
            "total_banked": Decimal(total_banked),
            "tranche_count": len(tranches),
            "tranches": tranches,
        }
        return _mask_payment_fields(
            agg, CUSTOMER_PAYMENT_AGGREGATE_FINANCIAL_FIELDS, financial_fields_allowed(actor)
        )

    @staticmethod
    async def list(
        db: AsyncSession,
        booking_id: uuid.UUID,
        container_id: uuid.UUID,
        actor: User,
        pagination: PaginationParams,
    ) -> dict[str, Any]:
        await ContainerService.get_in_booking(db, booking_id, container_id)
        q = (
            select(CustomerPayment)
            .where(CustomerPayment.container_id == container_id)
            .order_by(CustomerPayment.tranche_index, CustomerPayment.created_at)
        )
        page = await paginate(db, q, pagination)
        show = financial_fields_allowed(actor)
        page["items"] = [
            _mask_payment_fields(
                CustomerPaymentOut.model_validate(p).model_dump(),
                CUSTOMER_PAYMENT_FINANCIAL_FIELDS,
                show,
            )
            for p in page["items"]
        ]
        return page
