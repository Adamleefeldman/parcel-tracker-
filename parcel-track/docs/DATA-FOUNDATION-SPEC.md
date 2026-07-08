# Data-Foundation Spec (Phase 1A)

**The master-data + multi-currency backbone that unblocks the v4 platform.**
Target codebase: `parcel-track` (FastAPI + SQLAlchemy 2.0 async + Alembic + Postgres/Supabase).
Companion to `ALIGNMENT-AND-PROGRESS.md` (repo root) and the v4 briefing gap analysis.

> **Why this comes first.** Almost everything missing in the v4 vision — multi-SKU, multi-supplier, multi-currency, multi-warehouse, the portals, Document AI auto-mapping, landed cost, investor consolidation — points at reference data we don't have yet. This spec defines that reference data **once**, so parallel work doesn't invent five incompatible versions of it.

---

## 0. Design principles (read first)

1. **Additive, non-breaking migrations.** The current vertical slice (PO → Booking → Container → payments) works and is tested. Every change here is *additive*: new tables, new nullable FKs, backfilled then tightened. We do **not** rewrite the booking/container/lifecycle engine. New columns land nullable → backfill → set `NOT NULL` in a follow-up migration.
2. **Config over code.** Reference values (currencies, categories, incoterms, warehouses, partners, products) become **rows in tables**, not Python enums. Adding one is a form submission, not a deploy.
3. **Follow existing conventions exactly.** Use the `uuid_pk()`, `now_utc()`, `updated_at()`, and `lowercase_enum()` helpers in `app/db/models.py`. Money is `Numeric`. All logic in the service layer (never in routes). All responses via Pydantic `response_model`.
4. **Every new table gets RLS.** Postgres deny-all RLS is enabled on every public table (migration `5ab45b2e1574`). **Each new table MUST be added to a `ALTER TABLE … ENABLE ROW LEVEL SECURITY` migration** or it silently becomes readable via the Supabase anon key. This is easy to forget — it's in the acceptance checklist below.
5. **Avoid the `entity_id` name collision.** `Document` and `AuditLog` already have a *polymorphic* `entity_id` / `entity_type` (meaning "which row this doc points at"). The new legal-entity tag is **`legal_entity_id`** — never reuse `entity_id` for it.
6. **Tag, don't fork.** Multi-entity / multi-currency are *columns on existing rows*, not parallel table trees.

---

## 1. Build order & dependency graph

Build in this order — each layer is referenced by the next:

```
1. Currency + FX        (currencies, fx_rates, +AED, money-capture columns)
2. Legal Entity         (legal_entities, legal_entity_id on transactions)
3. Party master         (parties, party_bank_accounts) — supplier/FF/haulier/warehouse-op
4. Product / SKU        (product_categories, products, supplier_products, pack_specs)
        ├── purchase_order_lines   (multi-SKU POs)
        └── container_contents     (SKU mix per container → stock-by-SKU)
5. Supporting masters   (warehouses, incoterms) + container sale-type/title-transfer
```

Migrations chain off the current Alembic head. **Do not hand-author revision hashes from this doc** — generate each with `uv run alembic revision -m "…"`, set `down_revision` to the prior head, and keep one logical table-group per migration. Suggested file labels (mirroring the `pX_Y_` convention):

| Order | Migration label | Adds |
|---|---|---|
| 1a | `p1a_1_currency_master_and_aed` | `currencies` table + seed; add `AED` to `currency` enum |
| 1b | `p1a_2_fx_rates` | `fx_rates` table |
| 1c | `p1a_3_money_usd_capture` | `fx_rate_to_usd` + `amount_usd` on money rows (nullable) |
| 2  | `p1a_4_legal_entities` | `legal_entities` + seed default; `legal_entity_id` (nullable) on transaction tables |
| 3  | `p1a_5_party_master` | `parties`, `party_bank_accounts` |
| 4a | `p1a_6_product_master` | `product_categories`, `products`, `supplier_products`, `pack_specs` |
| 4b | `p1a_7_po_lines` | `purchase_order_lines`; `product_id` backfill path |
| 4c | `p1a_8_container_contents` | `container_contents` |
| 5  | `p1a_9_warehouses_incoterms` | `warehouses`, `incoterms`; container sale-type/title fields |
| RLS | `p1a_10_enable_rls_new_tables` | `ENABLE ROW LEVEL SECURITY` on all of the above |
| tighten | `p1a_11_backfill_not_null` | flip backfilled FKs to `NOT NULL` (run after data backfill) |

---

## 2. Pillar 1 — Currency & FX

**Problem today:** `Currency` is a 4-value Python enum (`USD/GBP/EUR/MAD`) — **`AED` is missing entirely** — baked into ~6 money columns. There is no exchange-rate data, no USD-equivalent on any transaction, and no locked historical rate. (`app/core/enums.py:276`, money columns across `models.py`.)

**Target:** a `currencies` reference table, an `fx_rates` table (live cache + history), and a **money-capture pattern** that records the locked rate and USD-equivalent on every transaction.

### 2.1 Immediate fix — add AED to the enum

Small, unblocks AED transactions today. Postgres enum alter:

```python
# migration p1a_1 (upgrade)
op.execute("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AED'")
```
…and add `AED = "AED"` to `Currency` in `app/core/enums.py`. (Note: `Currency` uses default name-binding — name == value — so no `lowercase_enum` needed. `ADD VALUE` cannot run inside a transaction block on older PG; if Alembic wraps it, split into its own migration with `op.get_bind().execution_options(isolation_level="AUTOCOMMIT")` or mark `transactional_ddl = False`.)

### 2.2 `currencies` — the config table

```python
class CurrencyRef(Base):
    """Reference list of supported currencies. Config-over-code: a new
    currency is a row here, not an enum edit. The legacy `Currency` enum
    columns stay valid (they still constrain to ISO codes); NEW columns
    reference `currencies.code` so the list is data-driven going forward."""

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)        # ISO-4217, e.g. "USD"
    name: Mapped[str] = mapped_column(String(60), nullable=False)         # "US Dollar"
    symbol: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "$"
    minor_units: Mapped[int] = mapped_column(Integer, default=2, nullable=False)  # decimal places
    is_base: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False) # USD = true
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()
```

**Seed** (in the migration): `USD (base), GBP, EUR, MAD, AED`. Exactly one `is_base=true`.

> **Migration strategy decision (important).** Converting existing enum columns to `CHAR(3)` FKs across 6 tables in one shot is risky. **Recommendation:** keep the existing `Currency` enum columns as-is for now (they already constrain to valid codes), seed `currencies` from the enum, and have all *new* columns reference `currencies.code`. Schedule the full enum→FK convergence as a separate, later migration once the new model is proven. State this tradeoff to the team so no one "half-migrates."

### 2.3 `fx_rates` — live cache + locked history

```python
class FxRate(Base):
    """One observed FX rate at a point in time. The XE poller inserts rows
    (append-only); `get_rate(quote, as_of)` reads the latest row at/under
    `as_of`. Base is always USD (the reporting base). Storing history is what
    makes 'locked historical rate' possible — past transactions reference the
    rate that was live when they were written, never a re-fetched value."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        Index("ix_fx_rates_quote_asof", "quote_code", "as_of"),
        CheckConstraint("rate > 0", name="ck_fx_rates_rate_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    base_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=False)   # "USD"
    quote_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=False)  # "GBP"
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)  # 1 base = `rate` quote
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), default="xe", nullable=False)  # "xe" | "manual"
    created_at: Mapped[datetime] = now_utc()
```

- **Provider:** XE API via the existing resilience layer (`app/integrations/_http.py`, provider `"xe"`), behind a `XE_ENABLED` Settings kill-switch mirroring `VESSELFINDER_ENABLED`. Celery beat job (default every 30 min, configurable) inserts the latest rates; on provider failure, reads fall back to the last cached row (that's automatic — we read the latest row regardless of age, and surface its `as_of` so staleness is visible).
- **Precision:** `Numeric(18, 8)` for rates. Never use floats for money or rates anywhere.

### 2.4 Money-capture pattern (the "locked rate" requirement)

On **every transaction that holds money**, add two nullable columns:

```python
fx_rate_to_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)  # locked at write time
amount_usd:     Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # = amount × rate, stored
```

Apply to: `PurchaseOrder.total_value`, `Invoice.value`, `SupplierPayment.amount`, `CustomerPayment.amount_received`, `Container.sale_price_total`. (Add per-row; backfill `fx_rate_to_usd`/`amount_usd` from `fx_rates` at the transaction date where possible, else leave null and flag.)

**Service rule:** when a money row is created, the service looks up the live rate (`FxService.rate_to_usd(currency, at=tx_date)`), writes both the native amount and the **frozen** `fx_rate_to_usd` + computed `amount_usd`. Reports read `amount_usd` directly — they never re-convert historical rows. This is what keeps reconciliation honest.

**Unblocks:** landed cost per container, multi-currency cashflow ledger, investor USD/GBP/EUR toggle, the FX header strip, and the A/R-aging currency bug (Section 2.2 of the alignment doc — aging can now sum `amount_usd`).

---

## 3. Pillar 2 — Legal Entity (multi-entity tagging)

**Problem today:** the platform silently assumes one company. No transaction carries an owning legal entity, so per-entity reporting and the consolidated investor view are impossible.

```python
class LegalEntity(Base):
    """A legal trading entity that owns transactions. Today: one UAE Free-Zone
    entity (WT Trading LLC / The FMCG Hub). Future: a Morocco sister entity.
    Every money/transaction row is tagged with one. Reports filter by entity;
    the investor view consolidates across them."""

    __tablename__ = "legal_entities"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)   # "FMCG_HUB"
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)         # "WT Trading LLC"
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)       # "The FMCG Hub"
    jurisdiction: Mapped[str | None] = mapped_column(String(80), nullable=True)  # "UAE Free Zone"
    base_currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), default="USD", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()
```

**Seed:** one default entity (`is_default=true`) for the current business.

**Tag the transactions.** Add a **nullable** `legal_entity_id` FK to: `PurchaseOrder`, `Invoice`, `SupplierPayment`, `CustomerPayment`, `Booking`, `Container`. Backfill all existing rows to the default entity, then a later migration sets them `NOT NULL`.

```python
legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("legal_entities.id"), nullable=True, index=True
)
```

- **Watch-out flag (briefing requirement):** add a service-level check that flags any transaction whose parties are both UAE-domestic (would risk Free-Zone status) — start with a simple boolean/notes surface; it's a report, not enforcement.
- **Inter-entity transfers** (Morocco sub paying the factory) are out of scope for 1A but the `legal_entity_id` makes them modellable later without a reshape.

**Unblocks:** per-entity reporting, consolidated investor portal, Morocco sister-entity readiness, Free-Zone compliance flags.

---

## 4. Pillar 3 — Party master (supplier + all partners)

**Problem today:** no supplier entity exists — the supplier is a free-text `PurchaseOrder.supplier_ref` and a hard-wired "SCDB". The only party tables (`Broker`, `Company`) are customer-side and carry no bank/terms/currency/rate-card fields.

**Target:** one `parties` master for every non-customer counterparty (supplier, freight forwarder, haulier, warehouse operator), with bank details and default terms. This is also the backbone the **partner portal** scopes against.

```python
class PartyType(str, Enum):  # noqa: UP042
    SUPPLIER = "supplier"
    FREIGHT_FORWARDER = "freight_forwarder"
    HAULIER = "haulier"
    WAREHOUSE_OPERATOR = "warehouse_operator"
    CUSTOMS_BROKER = "customs_broker"


class Party(Base):
    """A counterparty we transact with (not the end-buyer customer — that's
    `Company`/`Broker`). Holds default currency + payment terms; bank accounts
    are child rows. A partner-portal user is linked to exactly one Party and
    sees only its data."""

    __tablename__ = "parties"
    __table_args__ = (UniqueConstraint("party_type", "code", name="uq_parties_type_code"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    party_type: Mapped[PartyType] = mapped_column(lowercase_enum(PartyType), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)          # "SCDB"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True) # "Morocco"
    default_currency_code: Mapped[str | None] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=True)
    default_payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "Net 30", "CAD"
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()


class PartyBankAccount(Base):
    __tablename__ = "party_bank_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)   # "USD operating"
    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(40), nullable=True)
    swift_bic: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()
```

**Wire-in (additive):** add nullable `supplier_party_id` FK to `PurchaseOrder` (alongside the existing `supplier_ref`, which becomes legacy/derived). Backfill the single existing supplier ("SCDB") to one `Party` row.

> **Broker/Company convergence — deliberate non-goal for 1A.** `Broker`/`Company` are customer-side and power the working customer-payment flow. **Do not fold them into `Party` now** — it would destabilise a tested path for no immediate gain. Note the future option (a `customer`/`broker` `PartyType`) and move on.

**Unblocks:** multi-supplier POs, supplier bank/terms, rate cards (hang off `party_id`), supplier payments with beneficiary detail, and the partner portal's per-party scoping.

---

## 5. Pillar 4 — Product / SKU master

**Problem today:** products are free-text `PurchaseOrder.product_description`. No SKU, no dual-code mapping, no categories, no pack hierarchy, no multi-SKU support.

### 5.1 Category + Product + dual-code mapping

```python
class ProductCategory(Base):
    """Configurable FMCG category. A row, not an enum — soft drink, snacks,
    grocery, confectionery, personal care, beverage, …"""

    __tablename__ = "product_categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # "SOFT_DRINK"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()


class ProductStatus(str, Enum):  # noqa: UP042
    ACTIVE = "active"
    PLANNED = "planned"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


class Product(Base):
    """OUR canonical product (the FH-XXX-XXX taxonomy). Used for reporting,
    pricing, customer invoicing, brand. Supplier codes map to this via
    `supplier_products`."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = uuid_pk()
    our_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)  # "FH-PEP-330"
    name: Mapped[str] = mapped_column(String(200), nullable=False)                              # "Pepsi 330ml can"
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_categories.id"), nullable=False, index=True
    )
    base_unit: Mapped[str] = mapped_column(String(30), default="can", nullable=False)  # the atomic sellable unit
    status: Mapped[ProductStatus] = mapped_column(
        lowercase_enum(ProductStatus), default=ProductStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()


class SupplierProduct(Base):
    """Maps a supplier's internal code to our Product. The auto-map target on
    document ingest: a CI/packing list arrives with the supplier's code, the
    system resolves it to our Product via this table."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_party_id", "supplier_code", name="uq_supplier_products_code"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_code: Mapped[str] = mapped_column(String(80), nullable=False)        # "PEPSI 33 MID CL CAN"
    supplier_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()
```

### 5.2 Pack-spec (cases / trays / units)

```python
class PackSpec(Base):
    """Per-product pack hierarchy. Generic ratios so any category fits:
    units → tray → pallet → container. Decouples 'how it's packed' from the
    sale-price-per-tray/pallet columns already on Container."""

    __tablename__ = "pack_specs"

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    units_per_tray: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trays_per_pallet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pallets_per_container: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_label: Mapped[str] = mapped_column(String(30), default="can", nullable=False)
    tray_label: Mapped[str] = mapped_column(String(30), default="tray", nullable=False)
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()
```

### 5.3 Multi-SKU support — PO lines + container contents

The PDF shows multi-SKU POs and "SKU mix 7+7+7" containers. The single `product_description` on `PurchaseOrder` can't hold that.

```python
class PurchaseOrderLine(Base):
    """One product line on a PO. Replaces the single free-text product/qty.
    `PurchaseOrder.product_description` stays as a legacy/derived summary; new
    POs populate lines."""

    __tablename__ = "purchase_order_lines"

    id: Mapped[uuid.UUID] = uuid_pk()
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(30), nullable=False)   # "tray" | "pallet" | "can"
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=True)
    created_at: Mapped[datetime] = now_utc()


class ContainerContent(Base):
    """What SKUs (and how many pallets/trays) are physically in a container.
    Enables 'SKU mix' on the container detail and 'available stock by SKU +
    warehouse' for the customer portal."""

    __tablename__ = "container_contents"

    id: Mapped[uuid.UUID] = uuid_pk()
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("containers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    pallets: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    trays: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    units: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = now_utc()
```

**Backfill:** existing POs keep `product_description`; optionally seed `products` from the distinct descriptions and create one matching line per PO. Lines/contents are additive — current screens keep working on the legacy field until the UI is updated.

**Unblocks:** SKU catalogue screen, supplier-code auto-mapping on ingest, multi-SKU POs, container SKU mix, stock-by-SKU for the customer portal, category reporting, pack-spec-driven quantity math.

---

## 6. Pillar 5 — Supporting masters (warehouse, incoterm) + legal sale-type

These are small, high-leverage, and fix two Section-2 problems from the alignment doc.

### 6.1 Warehouse master

```python
class WarehouseStatus(str, Enum):  # noqa: UP042
    ACTIVE = "active"
    PLANNED = "planned"
    FUTURE = "future"


class Warehouse(Base):
    """Bonded (or future) warehouse. Replaces free-text DeliveryPoint.warehouse_name."""

    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)   # "MISTLEY"
    name: Mapped[str] = mapped_column(String(200), nullable=False)              # "Mistley Quay"
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_entities.id"), nullable=True
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_bonded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[WarehouseStatus] = mapped_column(
        lowercase_enum(WarehouseStatus), default=WarehouseStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = now_utc()
    updated_at: Mapped[datetime] = updated_at()
```
Add nullable `warehouse_id` FK to `DeliveryPoint` (keep `warehouse_name` as legacy). Seed Mistley Quay + the planned secondary.

### 6.2 Incoterm + the legal "sale type" capture

This fixes alignment-doc §2.3 (delivery_type ≠ sale type) and seeds §3.9 (legal/customs).

```python
class Incoterm(Base):
    """Reference list of trade terms used per deal."""

    __tablename__ = "incoterms"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)  # "FOB","DAP","DDP","EXW"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SaleType(str, Enum):  # noqa: UP042
    """The COMMERCIAL axis the legal structure depends on — distinct from
    DeliveryType (the routing axis)."""

    EX_BOND = "ex_bond"     # customer collects from bond, becomes UK Importer of Record
    DELIVERED = "delivered" # we arrange haulage; customer still IoR at clearance
```

Add to `Container` (all nullable, additive):
```python
sale_type: Mapped[SaleType | None] = mapped_column(lowercase_enum(SaleType), nullable=True)
incoterm_code: Mapped[str | None] = mapped_column(String(10), ForeignKey("incoterms.code"), nullable=True)
title_transfer_point: Mapped[str | None] = mapped_column(String(120), nullable=True)  # e.g. "at bond release"
```

> **Do not overload `delivery_type`.** `DIRECT`/`VIA_WAREHOUSE` answers "does it pass through a warehouse." `sale_type` answers "ex-bond vs delivered" — the legal/tax question. They are orthogonal; keep both.

**Unblocks:** multi-warehouse stock, the ex-bond/delivered customer choice, importer-of-record recording, incoterm-driven landed cost and invoice line items, the whole legal backbone.

---

## 7. Cross-cutting requirements (the acceptance checklist)

Every table/column above must satisfy:

- [ ] **RLS enabled.** New tables added to a `ENABLE ROW LEVEL SECURITY` migration. No allow-all policies. (Forgetting this = anon-key data leak.)
- [ ] **Async-safe.** No lazy relationship access; callers use `selectinload`. `expire_on_commit=False` already set.
- [ ] **Service layer only.** New masters get a `*_service.py`; routes validate + delegate. No business logic in routes.
- [ ] **Pydantic schemas.** Every endpoint uses `response_model=`; never return ORM objects.
- [ ] **Audit on writes.** Master-data create/update/deactivate writes an `AuditLog` row (route them through the central audit helper recommended in the alignment doc — and add it if not yet built).
- [ ] **Idempotency** on any new money-creating POST (reuse `app/middleware/idempotency.py`).
- [ ] **Two migrations for NOT NULL FKs.** Add nullable → backfill (data migration) → set `NOT NULL`. Never add a non-null FK to a populated table in one step.
- [ ] **Seeds are idempotent.** Use `ON CONFLICT DO NOTHING` / existence checks so re-running is safe.
- [ ] **Tests.** Unit tests for each service (CRUD + the SKU auto-map resolver + the FX `rate_to_usd` locking). Target parity with the existing suite's rigor (`uv run pytest tests/ -q`).
- [ ] **mypy + ruff clean** (both blocking in CI).

---

## 8. Service & API surface (admin-gated)

Minimal, RESTful, all under `/api/v1`, all `require_admin` for writes (reads can widen later for portals):

| Resource | Endpoints |
|---|---|
| Currencies | `GET /currencies`, `POST /currencies`, `PATCH /currencies/{code}` |
| FX rates | `GET /fx-rates?quote=GBP`, `GET /fx-rates/latest`, (writes via the XE beat job) |
| Legal entities | `GET /legal-entities`, `POST`, `PATCH /{id}` |
| Parties | `GET /parties?type=supplier`, `POST`, `PATCH /{id}`, `POST /{id}/bank-accounts` |
| Categories | `GET /product-categories`, `POST`, `PATCH /{id}` |
| Products | `GET /products`, `POST`, `PATCH /{id}`, `GET /products/{id}/supplier-codes`, `POST /products/{id}/supplier-codes` |
| Pack specs | `PUT /products/{id}/pack-spec` |
| Warehouses | `GET /warehouses`, `POST`, `PATCH /{id}` |
| Incoterms | `GET /incoterms`, `POST` |

New services: `fx_service.py`, `currency_service.py`, `legal_entity_service.py`, `party_service.py`, `product_service.py` (incl. the supplier-code → product resolver), `warehouse_service.py`. The mobile Admin tab already has the pattern (People/Operations/System menus) to host these as new admin screens.

---

## 9. Traceability — what each pillar unblocks

| Foundation pillar | Gap-analysis items it unblocks |
|---|---|
| Currency + FX | `fx-1..fx-7`, `co-6` landed cost, `cu-1` A/R currency bug, investor toggle |
| Legal Entity | `da-6`, investor consolidation, `le-7` Free-Zone flag, Morocco sister entity |
| Party master | `da-2` multi-supplier, `su-2/su-3` supplier-payment detail, `op-2` rate cards, partner portal scoping |
| Product / SKU | `da-1` dual-code, `da-3` categories, `da-4` pack-spec, `do-5` ingest auto-map, customer-portal stock-by-SKU |
| Warehouse + Incoterm + sale_type | `da-5` warehouse config, `co-5`/`wa-2` sale type, `le-1..le-5` legal/customs, multi-warehouse |

---

## 10. Open decisions to confirm before building

1. **Currency model depth:** ship the pragmatic "enum stays + `currencies` table for new columns" path (recommended), or commit now to the full enum→FK convergence across all money columns?
2. **Party vs Supplier scope:** unified `Party` master for all partner types now (recommended), or a narrower `Supplier`-only table for 1A?
3. **Multi-SKU rollout:** introduce `purchase_order_lines` + `container_contents` in 1A (recommended — the UI can lag), or defer container_contents to when the customer portal is built?
4. **Coordination:** if a second team is building any of this, **which pillars do they own?** Currency/entity/party/product must have exactly one owner each — these are the tables most dangerous to build twice.
5. **Backfill ownership:** who provides the real seed data (the SKU list with supplier codes, the supplier bank details, the warehouse list)? The schema is cheap; clean seed data is the long pole.

---

*This spec is intentionally additive and reversible. Build pillar 1 → 5 in order, keep each migration small, and the existing vertical slice keeps passing its tests the whole way.*
