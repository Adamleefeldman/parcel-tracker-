"""Guard against SQLAlchemy/Postgres enum-binding drift.

`SAEnum(MyEnum)` defaults to binding `m.name`, but the Postgres labels for
a few of our enum types are lowercase (matching `m.value`). Mixing those up
yields runtime `InvalidTextRepresentationError`s that the integration suite
misses, because `Base.metadata.create_all` synthesises the test-DB enum
type from the SA model (so test labels always equal whatever the bind
expression resolves to).

This test pins the per-column bind expression so future edits cannot quietly
revert `lowercase_enum(...)` back to `SAEnum(...)` for an enum whose prod
labels are lowercase.
"""

from app.core.enums import (
    ContainerLifecycleStatus,
    CustomerPaymentMethod,
    DeliveryType,
    UKPort,
)
from app.db.models import BillOfLading, Container, CustomerPayment, DeliveryPoint, PortTemplate


def _enum_type(model, attr):
    return model.__table__.c[attr].type


def test_ukport_binds_lowercase_value():
    col_type = _enum_type(BillOfLading, "port_of_discharge")
    assert col_type._db_value_for_elem(UKPort.LONDON_GATEWAY) == "london_gateway"
    assert col_type._db_value_for_elem(UKPort.FELIXSTOWE) == "felixstowe"

    pt_type = _enum_type(PortTemplate, "port")
    assert pt_type._db_value_for_elem(UKPort.TILBURY) == "tilbury"


def test_container_lifecycle_status_binds_lowercase_value():
    col_type = _enum_type(Container, "lifecycle_status")
    assert col_type._db_value_for_elem(ContainerLifecycleStatus.ORDERED) == "ordered"
    assert col_type._db_value_for_elem(ContainerLifecycleStatus.IMPORT_CLEARED) == "import_cleared"
    assert col_type._db_value_for_elem(ContainerLifecycleStatus.DISPUTED) == "disputed"


def test_customer_payment_method_binds_lowercase_value():
    col_type = _enum_type(CustomerPayment, "method")
    assert col_type._db_value_for_elem(CustomerPaymentMethod.CASH) == "cash"
    assert col_type._db_value_for_elem(CustomerPaymentMethod.TRANSFER) == "transfer"


def test_delivery_type_binds_lowercase_value():
    container_type = _enum_type(Container, "delivery_type")
    assert container_type._db_value_for_elem(DeliveryType.DIRECT) == "direct"
    assert container_type._db_value_for_elem(DeliveryType.VIA_WAREHOUSE) == "via_warehouse"

    dp_type = _enum_type(DeliveryPoint, "delivery_type")
    assert dp_type._db_value_for_elem(DeliveryType.DIRECT) == "direct"
