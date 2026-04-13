"""
Workflow State Machine Tests

Three test classes covering the shipment lifecycle state machine:

  TestSequentialWalkthrough  — happy-path through all 7 transitions in order
  TestPreconditions          — every blocked transition raises the correct error
  TestRoleEnforcement        — every transition gate enforces the correct roles

The state machine:

  DRAFT → PO_SUBMITTED → INVOICE_RECEIVED → PAYMENT_CONFIRMED
        → BL_ISSUED → IN_TRANSIT → CLEARED → COMPLETE

All transitions are driven through the HTTP API exactly as a real client
would use it.  Infrastructure (S3) is mocked globally in conftest.py.
"""

import uuid
from datetime import date

from httpx import AsyncClient

from tests.integration.conftest import _add_member


class TestSequentialWalkthrough:
    """
    A single test drives one shipment through every state in the correct order.

    Each step:
      1. Satisfies the preconditions for the next state
      2. Calls the endpoint that triggers the transition
      3. Asserts the shipment status has advanced exactly one step

    Only the admin actor is used here — role enforcement is covered in
    TestRoleEnforcement.  The focus is purely on the state machine logic.
    """

    async def _get_status(self, client: AsyncClient, shipment_id: str, headers: dict) -> str:
        """
        Fetch the current shipment status via the detail endpoint.

        Using the full GET /shipments/{id} rather than trusting the response
        of the mutating endpoint means we are reading the persisted value that
        other users would see — not just what the last write returned.
        """
        r = await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)
        assert r.status_code == 200, f"Could not fetch shipment: {r.json()}"
        return r.json()["status"]

    async def test_full_lifecycle(self, client: AsyncClient, admin_token: str):
        """
        Walk shipment WALK-001 through every transition from DRAFT to COMPLETE.

        Assertions are placed immediately after each transition so a failure
        names the exact step that broke, rather than only at the end.
        """
        h = {"Authorization": f"Bearer {admin_token}"}

        # ── STEP 1: Create shipment ───────────────────────────────────────────
        # POST /shipments creates the record with status=DRAFT and
        # automatically adds the acting admin as the first ShipmentUser.
        # No preconditions — this is the entry point to the state machine.
        r = await client.post(
            "/api/v1/shipments",
            json={"reference": "WALK-001"},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        sid = r.json()["id"]
        assert r.json()["status"] == "draft"

        # ── STEP 2: Create Purchase Order ─────────────────────────────────────
        # A PO is the commercial agreement that starts the trade.
        # At this point it is still in DRAFT status — it has not been formally
        # submitted yet.  The route only creates the DB record.
        r = await client.post(
            f"/api/v1/shipments/{sid}/po",
            json={
                "po_number": "PO-2026-001",
                "po_date": "2026-01-10",
                "product_description": "Ceramic floor tiles",
                "quantity": "500",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        po_id = r.json()["id"]

        # ── STEP 3: Upload the PO document ────────────────────────────────────
        # The precondition for PO_SUBMITTED requires a Document record linked
        # to this PO (entity_type=purchase_order, entity_id=po_id).
        #
        # Real clients: get_upload_url → PUT to S3 → POST /confirm
        # Tests: skip the S3 step (mocked) and call /confirm directly.
        # This creates the exact same Document row the precondition checks for.
        r = await client.post(
            "/api/v1/documents/confirm",
            params={"entity_type": "purchase_order", "entity_id": po_id},
            json={
                "file_key": "test/uploads/fake-key.pdf",
                "file_name": "purchase_order.pdf",
                "mime_type": "application/pdf",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()

        # ── STEP 4: Submit PO → PO_SUBMITTED ─────────────────────────────────
        # PATCH /po/{id}/submit:
        #   1. Route checks a Document exists for this PO  (route-level guard)
        #   2. Route sets po.status = SUBMITTED
        #   3. Route calls ShipmentService.transition_status(PO_SUBMITTED)
        #   4. _check_preconditions confirms PO.status == SUBMITTED
        #   5. shipment.status is written and an AuditLog row is inserted
        r = await client.patch(
            f"/api/v1/shipments/{sid}/po/{po_id}/submit",
            headers=h,
        )
        assert r.status_code == 200, r.json()
        assert await self._get_status(client, sid, h) == "po_submitted"

        # ── STEP 5: Create Invoice → INVOICE_RECEIVED ────────────────────────
        # Creating the invoice triggers the transition automatically.
        # The route:
        #   1. Creates Invoice with status=RECEIVED
        #   2. Checks for value discrepancy vs PO (>2% → DISCREPANCY flag)
        #   3. Calls transition_status(INVOICE_RECEIVED)
        #   4. _check_preconditions confirms invoice.status in {RECEIVED, RECONCILED}
        #
        # We match the invoice value exactly to the PO total so the discrepancy
        # flag is NOT set.  That path is covered in TestPreconditions.
        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-01-15",  # must be >= po_date
                "value": "10000.00",  # exactly matches PO total
                "currency": "USD",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200, r.json()
        assert await self._get_status(client, sid, h) == "invoice_received"

        # ── STEP 6: Record payment → PAYMENT_CONFIRMED ───────────────────────
        # The route adds a Payment record then checks whether the running total
        # of CONFIRMED payments now covers the invoice value.  If it does, it
        # calls transition_status(PAYMENT_CONFIRMED) automatically.
        #
        # We pay the full £10 000 in one shot so the threshold is met
        # immediately.  A partial payment scenario is in TestPreconditions.
        r = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "SWIFT20260120",
                "payment_date": "2026-01-20",
                "amount": "10000.00",
                "currency": "USD",
                "payment_type": "full",
            },
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200, r.json()
        assert await self._get_status(client, sid, h) == "payment_confirmed"

        # ── STEP 7: Upload Bill of Lading → BL_ISSUED ────────────────────────
        # The BL is the legal document issued by the shipping line.
        # The route:
        #   1. Creates a BillOfLading record
        #   2. Auto-creates one Container row per entry in body.containers
        #   3. Calls transition_status(BL_ISSUED)
        #   4. _check_preconditions confirms a BillOfLading exists for shipment
        #
        # Container numbers must match ^[A-Z]{4}\d{7}$ (validated by schema).
        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-2026-001",
                "bl_date": "2026-01-25",
                "shipper_name": "Morocco Exports Ltd",
                "consignee_name": "UK Imports Ltd",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [
                    {"container_number": "TCKU1234567", "seal_number": "SEAL001"},
                    {"container_number": "MSCU7654321", "seal_number": "SEAL002"},
                ],
                "commodity_description": "Ceramic floor tiles",
                "gross_weight_kg": "12500.00",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()

        # Retrieve container IDs via GET — the POST response calls db.refresh()
        # which expires the relationship, so we fetch via the GET endpoint which
        # uses selectinload(BillOfLading.containers) to guarantee the data loads.
        r = await client.get(f"/api/v1/shipments/{sid}/bl", headers=h)
        assert r.status_code == 200, r.json()
        container_ids = [c["id"] for c in r.json()["containers"]]
        assert len(container_ids) == 2, "Expected 2 containers from BL upload"

        assert await self._get_status(client, sid, h) == "bl_issued"

        # ── STEP 8: Assign vessel ─────────────────────────────────────────────
        # The vessel is the physical ship.  Creating it does NOT trigger a
        # transition — it is setup data needed for the departure confirmation.
        # A BL must already exist before a vessel can be assigned.
        r = await client.post(
            f"/api/v1/shipments/{sid}/vessel",
            json={
                "vessel_name": "MSC Splendida",
                "shipping_line": "MSC Mediterranean",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()

        # ── STEP 9: Confirm departure → IN_TRANSIT ───────────────────────────
        # PATCH /vessel/depart confirms the vessel has physically left port.
        # The route:
        #   1. Sets vessel.atd (actual time of departure) and vessel.eta
        #   2. Sets vessel.status = DEPARTED
        #   3. Moves all containers to status IN_TRANSIT
        #   4. Calls transition_status(IN_TRANSIT)
        #   5. _check_preconditions confirms vessel.atd is not null
        #
        # Schema validates eta > atd.
        r = await client.patch(
            f"/api/v1/shipments/{sid}/vessel/depart",
            json={"atd": "2026-02-01", "eta": "2026-02-14"},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        assert await self._get_status(client, sid, h) == "in_transit"

        # ── STEP 10: Clear all containers through customs → CLEARED ───────────
        # Each container is independently cleared.  The transition fires only
        # when ALL containers have CustomsStatus.CLEARED.
        #
        # The route:
        #   1. Upserts a CustomsRecord for the container with status=CLEARED
        #   2. Sets container.status = CLEARED, container.port_status = RELEASED
        #   3. After each update, queries all containers for this shipment
        #   4. If all are CLEARED → calls transition_status(CLEARED)
        #
        # We clear container[0] first — status should remain IN_TRANSIT.
        # Then clear container[1] — the final one triggers the transition.
        clearance_date = date.today().isoformat()

        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{container_ids[0]}/customs",
            json={"status": "cleared", "clearance_date": clearance_date},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        # One container cleared — shipment must NOT have jumped to CLEARED yet
        assert await self._get_status(client, sid, h) == "in_transit"

        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{container_ids[1]}/customs",
            json={"status": "cleared", "clearance_date": clearance_date},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        # Both cleared — transition fires now
        assert await self._get_status(client, sid, h) == "cleared"

        # ── STEP 11: Create delivery point ────────────────────────────────────
        # A DeliveryPoint represents a physical drop-off location.
        # It links one or more containers to a recipient address.
        # Creating it does NOT trigger a transition.
        r = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points",
            json={
                "recipient_name": "Customer A Warehouse",
                "address": "123 Industrial Park, Tilbury, Essex, TS1 1AA",
                "contact_name": "Jane Doe",
                "contact_phone": "+44 7700 900000",
                "container_ids": container_ids,
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        point_id = r.json()["id"]

        # ── STEP 12: Mark delivery as delivered → COMPLETE ───────────────────
        # PATCH /delivery/points/{id}/status with status=delivered.
        # The route:
        #   1. Sets delivery_point.status = DELIVERED
        #   2. Checks if ALL delivery points for this shipment are now DELIVERED
        #   3. If so → calls transition_status(COMPLETE)
        #   4. _check_preconditions confirms all DeliveryPoints are DELIVERED
        #
        # We only have one delivery point, so this immediately triggers COMPLETE.
        r = await client.patch(
            f"/api/v1/shipments/{sid}/delivery/points/{point_id}/status",
            json={"status": "delivered"},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        assert await self._get_status(client, sid, h) == "complete"


# ── Module-level state-advance helper ────────────────────────────────────────


async def _advance_to(
    client: AsyncClient,
    h: dict,
    target: str,
    ref: str = "PREC-001",
) -> tuple[str, dict]:
    """
    Drive a freshly created shipment to `target` state and return (sid, ctx).

    ctx holds IDs needed by tests that manipulate specific sub-resources:
      po_id         — available from po_submitted onwards
      container_ids — available from bl_issued onwards

    All HTTP calls mirror those in test_full_lifecycle exactly.  This keeps the
    two in sync: if a route changes its request format, both the walkthrough and
    the precondition tests fail at the same step, making it easy to diagnose.

    Valid target values:
      "draft", "po_submitted", "invoice_received", "payment_confirmed",
      "bl_issued", "in_transit", "cleared"
    """
    r = await client.post("/api/v1/shipments", json={"reference": ref}, headers=h)
    assert r.status_code == 200, f"_advance_to({target!r}): create shipment failed: {r.json()}"
    sid = r.json()["id"]
    if target == "draft":
        return sid, {}

    r = await client.post(
        f"/api/v1/shipments/{sid}/po",
        json={
            "po_number": "PO-001",
            "po_date": "2026-01-10",
            "product_description": "Tiles",
            "quantity": "100",
            "quantity_unit": "boxes",
            "total_value": "10000.00",
            "currency": "USD",
        },
        headers=h,
    )
    assert r.status_code == 200, f"_advance_to({target!r}): create PO failed: {r.json()}"
    po_id = r.json()["id"]

    r = await client.post(
        "/api/v1/documents/confirm",
        params={"entity_type": "purchase_order", "entity_id": po_id},
        json={"file_key": "k.pdf", "file_name": "po.pdf", "mime_type": "application/pdf"},
        headers=h,
    )
    assert r.status_code == 200, f"_advance_to({target!r}): confirm doc failed: {r.json()}"

    r = await client.patch(f"/api/v1/shipments/{sid}/po/{po_id}/submit", headers=h)
    assert r.status_code == 200, f"_advance_to({target!r}): submit PO failed: {r.json()}"
    if target == "po_submitted":
        return sid, {"po_id": po_id}

    r = await client.post(
        f"/api/v1/shipments/{sid}/invoice",
        json={
            "invoice_number": "INV-001",
            "invoice_date": "2026-01-15",
            "value": "10000.00",
            "currency": "USD",
        },
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, f"_advance_to({target!r}): create invoice failed: {r.json()}"
    if target == "invoice_received":
        return sid, {"po_id": po_id}

    r = await client.post(
        f"/api/v1/shipments/{sid}/payments",
        json={
            "swift_ref": "SW001",
            "payment_date": "2026-01-20",
            "amount": "10000.00",
            "currency": "USD",
            "payment_type": "full",
        },
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, f"_advance_to({target!r}): add payment failed: {r.json()}"
    if target == "payment_confirmed":
        return sid, {"po_id": po_id}

    r = await client.post(
        f"/api/v1/shipments/{sid}/bl",
        json={
            "bl_number": "BL-001",
            "bl_date": "2026-01-25",
            "shipper_name": "Shipper",
            "consignee_name": "Consignee",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
            "containers": [
                {"container_number": "TCKU1234567"},
                {"container_number": "MSCU7654321"},
            ],
            "commodity_description": "Tiles",
            "gross_weight_kg": "5000.00",
        },
        headers=h,
    )
    assert r.status_code == 200, f"_advance_to({target!r}): upload BL failed: {r.json()}"
    r2 = await client.get(f"/api/v1/shipments/{sid}/bl", headers=h)
    assert r2.status_code == 200, f"_advance_to({target!r}): get BL failed: {r2.json()}"
    container_ids = [c["id"] for c in r2.json()["containers"]]
    if target == "bl_issued":
        return sid, {"po_id": po_id, "container_ids": container_ids}

    r = await client.post(
        f"/api/v1/shipments/{sid}/vessel",
        json={
            "vessel_name": "Test Vessel",
            "shipping_line": "TestLine",
            "port_of_loading": "Casablanca",
            "port_of_discharge": "Felixstowe",
        },
        headers=h,
    )
    assert r.status_code == 200, f"_advance_to({target!r}): create vessel failed: {r.json()}"
    r = await client.patch(
        f"/api/v1/shipments/{sid}/vessel/depart",
        json={"atd": "2026-02-01", "eta": "2026-02-14"},
        headers=h,
    )
    assert r.status_code == 200, f"_advance_to({target!r}): confirm departure failed: {r.json()}"
    if target == "in_transit":
        return sid, {"po_id": po_id, "container_ids": container_ids}

    clearance_date = date.today().isoformat()
    for cid in container_ids:
        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{cid}/customs",
            json={"status": "cleared", "clearance_date": clearance_date},
            headers=h,
        )
        assert r.status_code == 200, f"_advance_to({target!r}): upsert customs failed: {r.json()}"
    if target == "cleared":
        return sid, {"po_id": po_id, "container_ids": container_ids}

    raise ValueError(f"_advance_to: unknown target state {target!r}")


class TestPreconditions:
    """
    Every blocked or prematurely attempted transition raises the correct error.

    Tests are grouped by the failure mode they probe, not by state order.
    The _advance_to helper puts a fresh shipment into the required starting state
    so that each test can isolate exactly one precondition failure.

    The two categories covered here:
      A. State-machine guard failures — transition not in VALID_TRANSITIONS
      B. Precondition failures       — transition allowed by graph but data missing
    """

    async def _get_status(self, client: AsyncClient, shipment_id: str, headers: dict) -> str:
        r = await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)
        assert r.status_code == 200
        return r.json()["status"]

    # ── A. State-machine graph violations ────────────────────────────────────

    async def test_skip_to_invoice_from_draft(self, client: AsyncClient, admin_token: str):
        """
        Jumping directly from DRAFT to INVOICE_RECEIVED is blocked.

        VALID_TRANSITIONS[DRAFT] = [PO_SUBMITTED].  Calling the invoice endpoint
        while still in DRAFT tries to fire PO_SUBMITTED → INVOICE_RECEIVED, which
        fails because the current state is not PO_SUBMITTED.

        The state machine's first check is always "is this transition in the
        allowed list?", so this fails before any precondition logic runs.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await _advance_to(client, h, "draft", ref="SKIP-001")

        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-SKIP",
                "invoice_date": "2026-01-15",
                "value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 400
        assert "Cannot transition from 'ShipmentStatus.DRAFT'" in r.json()["detail"]

    async def test_backward_transition_blocked(self, client: AsyncClient, admin_token: str):
        """
        Re-firing a transition that has already succeeded is blocked.

        Once the shipment is in PO_SUBMITTED, calling submit_po again tries to
        fire DRAFT → PO_SUBMITTED from the wrong current state.  The guard sees
        that PO_SUBMITTED is not in VALID_TRANSITIONS[PO_SUBMITTED] and rejects it.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await _advance_to(client, h, "po_submitted", ref="BACK-001")
        po_id = ctx["po_id"]

        r = await client.patch(f"/api/v1/shipments/{sid}/po/{po_id}/submit", headers=h)
        assert r.status_code == 400
        assert "Cannot transition from 'ShipmentStatus.PO_SUBMITTED'" in r.json()["detail"]

    async def test_terminal_state_blocked(self, client: AsyncClient, admin_token: str):
        """
        No transition is accepted from the COMPLETE terminal state.

        VALID_TRANSITIONS[COMPLETE] = [], so any call that internally invokes
        transition_status() raises 400 immediately.  We verify this by driving
        the shipment all the way to COMPLETE and then attempting a new invoice.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await _advance_to(client, h, "cleared", ref="TERM-001")

        # Complete the lifecycle: one delivery point → mark delivered
        r = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points",
            json={
                "recipient_name": "Final Customer",
                "address": "1 End Street, London, EC1A 1BB",
                "contact_name": "Terminal Test",
                "contact_phone": "+44 7700 900001",
                "container_ids": ctx["container_ids"],
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        point_id = r.json()["id"]

        r = await client.patch(
            f"/api/v1/shipments/{sid}/delivery/points/{point_id}/status",
            json={"status": "delivered"},
            headers=h,
        )
        assert r.status_code == 200
        assert await self._get_status(client, sid, h) == "complete"

        # Now attempt any transition from the terminal state.
        # We re-submit the existing PO: the PO and its document both exist,
        # so all pre-state-machine guards pass, and the rejection comes purely
        # from the state machine's empty VALID_TRANSITIONS[COMPLETE] list.
        # (Creating a second invoice would fail earlier at the DB UNIQUE constraint
        # on invoices.shipment_id, which would mask the state machine guard.)
        po_id = ctx["po_id"]
        r = await client.patch(f"/api/v1/shipments/{sid}/po/{po_id}/submit", headers=h)
        assert r.status_code == 400
        assert "Cannot transition from 'ShipmentStatus.COMPLETE'" in r.json()["detail"]

    # ── B. Precondition data failures ────────────────────────────────────────

    async def test_submit_po_without_document(self, client: AsyncClient, admin_token: str):
        """
        A PO cannot be submitted until its document has been uploaded.

        The submit_po route explicitly checks for a Document row before calling
        transition_status().  Skipping the /documents/confirm step means no
        Document exists, so the route raises 400 before the state machine is
        consulted at all.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await _advance_to(client, h, "draft", ref="NODOC-001")

        # Create PO but deliberately skip the /documents/confirm step
        r = await client.post(
            f"/api/v1/shipments/{sid}/po",
            json={
                "po_number": "PO-NODOC",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "100",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 200
        po_id = r.json()["id"]

        r = await client.patch(f"/api/v1/shipments/{sid}/po/{po_id}/submit", headers=h)
        assert r.status_code == 400
        assert "Document must be uploaded before submitting PO" in r.json()["detail"]

    async def test_submit_po_without_po_record(self, client: AsyncClient, admin_token: str):
        """
        Submitting a non-existent PO returns 404.

        The route looks up the PO by ID as its very first action.  A fake UUID
        yields no row, so the route raises 404 before reaching the document check
        or the state machine.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await _advance_to(client, h, "draft", ref="NOPO-001")

        fake_po_id = "00000000-0000-0000-0000-000000000000"
        r = await client.patch(f"/api/v1/shipments/{sid}/po/{fake_po_id}/submit", headers=h)
        assert r.status_code == 404
        assert "PO not found" in r.json()["detail"]

    async def test_invoice_with_discrepancy_blocks_transition(
        self, client: AsyncClient, admin_token: str
    ):
        """
        An invoice whose value deviates >2% from the PO is flagged DISCREPANCY
        and the transition to INVOICE_RECEIVED is blocked.

        Flow inside the route:
          1. Invoice row is created with status=RECEIVED
          2. The 50% deviation (10000 → 15000) triggers status=DISCREPANCY
          3. transition_status(INVOICE_RECEIVED) is called
          4. _check_preconditions rejects DISCREPANCY status with 400
          5. The whole request rolls back — no invoice is persisted

        The shipment must stay in PO_SUBMITTED after the failed attempt.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await _advance_to(client, h, "po_submitted", ref="DISC-001")

        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-DISC",
                "invoice_date": "2026-01-15",
                "value": "15000.00",  # 50% over the 10000 PO total — well beyond the 2% threshold
                "currency": "USD",
            },
            headers=h,
        )
        assert r.status_code == 400
        assert "Invoice must be uploaded before proceeding" in r.json()["detail"]
        assert await self._get_status(client, sid, h) == "po_submitted"

    async def test_partial_payment_does_not_trigger_transition(
        self, client: AsyncClient, admin_token: str
    ):
        """
        A payment that only partially covers the invoice is recorded but does
        not advance the shipment state.

        The add_payment route checks whether cumulative confirmed payments ≥ invoice
        value.  Paying 5000 of a 10000 invoice keeps the running total below the
        threshold, so transition_status() is never called.  The response is 200
        (payment was accepted) but the status stays INVOICE_RECEIVED.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await _advance_to(client, h, "invoice_received", ref="PART-001")

        r = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "PART-SW001",
                "payment_date": "2026-01-20",
                "amount": "5000.00",  # exactly half — insufficient to trigger transition
                "currency": "USD",
                "payment_type": "partial",
            },
            headers=h,
        )
        assert r.status_code == 200, r.json()
        assert await self._get_status(client, sid, h) == "invoice_received"

    async def test_in_transit_without_vessel_blocked(self, client: AsyncClient, admin_token: str):
        """
        Confirming departure without an assigned vessel is rejected.

        _advance_to("bl_issued") leaves the shipment with a BL and containers
        but no Vessel row.  The confirm_departure route checks for a vessel
        before calling transition_status() and raises 400 when none is found.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, _ = await _advance_to(client, h, "bl_issued", ref="NOVEL-001")

        # Intentionally skip POST /vessel — attempt departure immediately
        r = await client.patch(
            f"/api/v1/shipments/{sid}/vessel/depart",
            json={"atd": "2026-02-01", "eta": "2026-02-14"},
            headers=h,
        )
        assert r.status_code == 400
        assert "Vessel not assigned yet" in r.json()["detail"]

    async def test_cleared_requires_all_containers(self, client: AsyncClient, admin_token: str):
        """
        The CLEARED transition only fires when every container is customs-cleared.

        After clearing container[0] the route queries all containers, finds
        container[1] still IN_TRANSIT, and does not call transition_status().
        The shipment must remain IN_TRANSIT after the partial clear.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await _advance_to(client, h, "in_transit", ref="PARTCLR-001")
        container_ids = ctx["container_ids"]
        clearance_date = date.today().isoformat()

        # Clear only the first container
        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{container_ids[0]}/customs",
            json={"status": "cleared", "clearance_date": clearance_date},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        # Second container still pending — state must not advance
        assert await self._get_status(client, sid, h) == "in_transit"

    async def test_complete_requires_all_delivery_points(
        self, client: AsyncClient, admin_token: str
    ):
        """
        The COMPLETE transition only fires when every delivery point is delivered.

        Two delivery points are created, each assigned one container.  After
        marking only the first as delivered, the route finds the second still
        pending and does not call transition_status().  The shipment stays CLEARED.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sid, ctx = await _advance_to(client, h, "cleared", ref="PARTDEL-001")
        container_ids = ctx["container_ids"]

        # Create two delivery points — one container each
        r1 = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points",
            json={
                "recipient_name": "Customer A",
                "address": "1 Alpha Road, London, EC1A 1AA",
                "contact_name": "Alice",
                "contact_phone": "+44 7700 900001",
                "container_ids": [container_ids[0]],
            },
            headers=h,
        )
        assert r1.status_code == 200, r1.json()
        point_id_0 = r1.json()["id"]

        r2 = await client.post(
            f"/api/v1/shipments/{sid}/delivery/points",
            json={
                "recipient_name": "Customer B",
                "address": "2 Beta Lane, Birmingham, B1 1BB",
                "contact_name": "Bob",
                "contact_phone": "+44 7700 900002",
                "container_ids": [container_ids[1]],
            },
            headers=h,
        )
        assert r2.status_code == 200, r2.json()

        # Mark only the first point as delivered
        r = await client.patch(
            f"/api/v1/shipments/{sid}/delivery/points/{point_id_0}/status",
            json={"status": "delivered"},
            headers=h,
        )
        assert r.status_code == 200, r.json()
        # Second point still pending — state must not advance
        assert await self._get_status(client, sid, h) == "cleared"


class TestRoleEnforcement:
    """
    Every transition gate enforces the correct role requirements.

    Two-layer RBAC model:
      Layer 1 — require_shipment_member: user must have a ShipmentUser row
      Layer 2 — inline role check: user must hold the required role

    Test strategy:
      - Admin-only routes (require_admin dependency): no member setup needed —
        any non-admin is rejected before reaching route body logic.
      - Member-gated routes: user is added as a member first so the membership
        gate passes, isolating the role check as the only failure point.

    Positive tests (expect 200) are included alongside negative tests to confirm
    that the allowed role actually works end-to-end, not just that forbidden
    roles are blocked.
    """

    async def _get_status(self, client: AsyncClient, shipment_id: str, headers: dict) -> str:
        r = await client.get(f"/api/v1/shipments/{shipment_id}", headers=headers)
        assert r.status_code == 200
        return r.json()["status"]

    # ── Admin-only routes ─────────────────────────────────────────────────────

    async def test_only_admin_can_submit_po(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        """
        submit_po uses require_admin — non-admin roles are rejected with 403.

        We set up a PO and document as admin (so the route would succeed for an
        admin) then call it as a Morocco agent to confirm the role gate fires.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        ma_h = {"Authorization": f"Bearer {morocco_agent_token}"}

        sid, _ = await _advance_to(client, h, "draft", ref="ROLE-PO-001")

        r = await client.post(
            f"/api/v1/shipments/{sid}/po",
            json={
                "po_number": "PO-ROLE",
                "po_date": "2026-01-10",
                "product_description": "Tiles",
                "quantity": "100",
                "quantity_unit": "boxes",
                "total_value": "10000.00",
                "currency": "USD",
            },
            headers=h,
        )
        po_id = r.json()["id"]

        await client.post(
            "/api/v1/documents/confirm",
            params={"entity_type": "purchase_order", "entity_id": po_id},
            json={"file_key": "k.pdf", "file_name": "po.pdf", "mime_type": "application/pdf"},
            headers=h,
        )

        r = await client.patch(f"/api/v1/shipments/{sid}/po/{po_id}/submit", headers=ma_h)
        assert r.status_code == 403

    async def test_only_admin_can_create_invoice(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """
        create_invoice uses require_admin — non-admin roles are rejected with 403.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        uk_h = {"Authorization": f"Bearer {uk_agent_token}"}

        sid, _ = await _advance_to(client, h, "po_submitted", ref="ROLE-INV-001")

        r = await client.post(
            f"/api/v1/shipments/{sid}/invoice",
            json={
                "invoice_number": "INV-ROLE",
                "invoice_date": "2026-01-15",
                "value": "10000.00",
                "currency": "USD",
            },
            headers=uk_h,
        )
        assert r.status_code == 403

    async def test_only_admin_can_add_payment(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """
        add_payment uses require_admin — non-admin roles are rejected with 403.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        uk_h = {"Authorization": f"Bearer {uk_agent_token}"}

        sid, _ = await _advance_to(client, h, "invoice_received", ref="ROLE-PAY-001")

        r = await client.post(
            f"/api/v1/shipments/{sid}/payments",
            json={
                "swift_ref": "ROLE-SW001",
                "payment_date": "2026-01-20",
                "amount": "10000.00",
                "currency": "USD",
                "payment_type": "full",
            },
            headers=uk_h,
        )
        assert r.status_code == 403

    # ── Bill of Lading upload ─────────────────────────────────────────────────

    async def test_morocco_agent_can_upload_bl(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        """
        Morocco agents are permitted to upload BL (positive role test).

        The user is added as a shipment member so the membership gate passes,
        then the inline check `actor.role in (ADMIN, MOROCCO_AGENT)` also passes.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        ma_h = {"Authorization": f"Bearer {morocco_agent_token}"}

        sid, _ = await _advance_to(client, h, "payment_confirmed", ref="ROLE-BL-MA-001")
        await _add_member(client, admin_token, sid, morocco_agent_token)

        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-ROLE-001",
                "bl_date": "2026-01-25",
                "shipper_name": "Shipper",
                "consignee_name": "Consignee",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [{"container_number": "TCKU1234567"}],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=ma_h,
        )
        assert r.status_code == 200, r.json()

    async def test_uk_agent_cannot_upload_bl(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """
        UK agents are not permitted to upload BL — only admin and Morocco agent.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        uk_h = {"Authorization": f"Bearer {uk_agent_token}"}

        sid, _ = await _advance_to(client, h, "payment_confirmed", ref="ROLE-BL-UK-001")
        await _add_member(client, admin_token, sid, uk_agent_token)

        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-ROLE-002",
                "bl_date": "2026-01-25",
                "shipper_name": "Shipper",
                "consignee_name": "Consignee",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [{"container_number": "TCKU1234567"}],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=uk_h,
        )
        assert r.status_code == 403

    async def test_customer_cannot_upload_bl(
        self, client: AsyncClient, admin_token: str, customer_token: str
    ):
        """
        Customers are not permitted to upload BL — read-only role.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        cust_h = {"Authorization": f"Bearer {customer_token}"}

        sid, _ = await _advance_to(client, h, "payment_confirmed", ref="ROLE-BL-CUST-001")
        await _add_member(client, admin_token, sid, customer_token)

        r = await client.post(
            f"/api/v1/shipments/{sid}/bl",
            json={
                "bl_number": "BL-ROLE-003",
                "bl_date": "2026-01-25",
                "shipper_name": "Shipper",
                "consignee_name": "Consignee",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
                "containers": [{"container_number": "TCKU1234567"}],
                "commodity_description": "Tiles",
                "gross_weight_kg": "5000.00",
            },
            headers=cust_h,
        )
        assert r.status_code == 403

    # ── Vessel departure confirmation ─────────────────────────────────────────

    async def test_morocco_agent_can_confirm_departure(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        """
        Morocco agents can confirm vessel departure (positive role test).

        We advance to bl_issued, create the vessel as admin (admin-only route),
        add the Morocco agent as a member, then confirm departure as that agent.
        The inline role check `actor.role in (ADMIN, MOROCCO_AGENT)` passes.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        ma_h = {"Authorization": f"Bearer {morocco_agent_token}"}

        sid, _ = await _advance_to(client, h, "bl_issued", ref="ROLE-DEP-MA-001")
        await _add_member(client, admin_token, sid, morocco_agent_token)

        # Vessel is created by admin (Morocco agent cannot create vessel on its own here)
        await client.post(
            f"/api/v1/shipments/{sid}/vessel",
            json={
                "vessel_name": "Role Test Vessel",
                "shipping_line": "TestLine",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
            },
            headers=h,
        )

        r = await client.patch(
            f"/api/v1/shipments/{sid}/vessel/depart",
            json={"atd": "2026-02-01", "eta": "2026-02-14"},
            headers=ma_h,
        )
        assert r.status_code == 200, r.json()

    async def test_uk_agent_cannot_confirm_departure(
        self, client: AsyncClient, admin_token: str, uk_agent_token: str
    ):
        """
        UK agents cannot confirm vessel departure — only admin and Morocco agent.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        uk_h = {"Authorization": f"Bearer {uk_agent_token}"}

        sid, _ = await _advance_to(client, h, "bl_issued", ref="ROLE-DEP-UK-001")
        await _add_member(client, admin_token, sid, uk_agent_token)

        await client.post(
            f"/api/v1/shipments/{sid}/vessel",
            json={
                "vessel_name": "Role Test Vessel",
                "shipping_line": "TestLine",
                "port_of_loading": "Casablanca",
                "port_of_discharge": "Felixstowe",
            },
            headers=h,
        )

        r = await client.patch(
            f"/api/v1/shipments/{sid}/vessel/depart",
            json={"atd": "2026-02-01", "eta": "2026-02-14"},
            headers=uk_h,
        )
        assert r.status_code == 403

    # ── Customs status updates ────────────────────────────────────────────────

    async def test_morocco_agent_cannot_update_customs(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        """
        Morocco agents cannot update customs status — only admin and UK agent.

        Customs clearance is a UK-side port operation managed by UK agents.
        The route checks `actor.role in (ADMIN, UK_AGENT)` before any mutation.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        ma_h = {"Authorization": f"Bearer {morocco_agent_token}"}

        sid, ctx = await _advance_to(client, h, "in_transit", ref="ROLE-CUST-MA-001")
        container_ids = ctx["container_ids"]
        await _add_member(client, admin_token, sid, morocco_agent_token)

        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{container_ids[0]}/customs",
            json={"status": "cleared", "clearance_date": date.today().isoformat()},
            headers=ma_h,
        )
        assert r.status_code == 403

    async def test_customer_cannot_update_customs(
        self, client: AsyncClient, admin_token: str, customer_token: str
    ):
        """
        Customers cannot update customs status — read-only role.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        cust_h = {"Authorization": f"Bearer {customer_token}"}

        sid, ctx = await _advance_to(client, h, "in_transit", ref="ROLE-CUST-CUST-001")
        container_ids = ctx["container_ids"]
        await _add_member(client, admin_token, sid, customer_token)

        r = await client.put(
            f"/api/v1/shipments/{sid}/containers/{container_ids[0]}/customs",
            json={"status": "cleared", "clearance_date": date.today().isoformat()},
            headers=cust_h,
        )
        assert r.status_code == 403

    # ── Shipment membership bypass ────────────────────────────────────────────

    async def test_non_member_blocked_from_shipment(
        self, client: AsyncClient, admin_token: str, morocco_agent_token: str
    ):
        """
        A user who is not a shipment member receives 403 on any member-gated route.

        require_shipment_member looks up ShipmentUser for (shipment_id, user_id).
        When no row exists, it returns 403 immediately — the route body is never
        reached.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        ma_h = {"Authorization": f"Bearer {morocco_agent_token}"}

        sid, _ = await _advance_to(client, h, "draft", ref="ROLE-NONMEM-001")
        # Deliberately do NOT add morocco agent as member

        r = await client.get(f"/api/v1/shipments/{sid}", headers=ma_h)
        assert r.status_code == 403

    async def test_admin_bypasses_membership_check(
        self, client: AsyncClient, admin_token: str, second_admin_token: str
    ):
        """
        Admin users can access any shipment without a ShipmentUser row.

        require_shipment_member returns a synthetic _AdminMembership object when
        the actor is ADMIN, bypassing the database lookup entirely.  This ensures
        admins always have full visibility without needing to be manually added
        to every shipment in the system.
        """
        h = {"Authorization": f"Bearer {admin_token}"}
        sa_h = {"Authorization": f"Bearer {second_admin_token}"}

        sid, _ = await _advance_to(client, h, "draft", ref="ROLE-ADMIN-001")
        # second_admin is NOT added as a member — admin bypass must grant access

        r = await client.get(f"/api/v1/shipments/{sid}", headers=sa_h)
        assert r.status_code == 200
