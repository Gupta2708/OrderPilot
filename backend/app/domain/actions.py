from enum import StrEnum


class BusinessAction(StrEnum):
    """The exact five simulated business actions from the assignment."""

    MESSAGE_FULFILLMENT_TEAM = "message_fulfillment_team"
    MESSAGE_PAYMENTS_TEAM = "message_payments_team"
    MESSAGE_LOGISTICS_TEAM = "message_logistics_team"
    MESSAGE_CUSTOMER = "message_customer"
    CREATE_INTERNAL_NOTE = "create_internal_note"


ALL_ACTIONS: tuple[str, ...] = tuple(str(member) for member in BusinessAction)
