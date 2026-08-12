PASSENGER_TRANSPORT = "PASSENGER_TRANSPORT"
DELIVERY_LOGISTICS = "DELIVERY_LOGISTICS"

PASSENGER_REQUEST_TYPES = frozenset(
    {
        "AIRPORT_PICKUP",
        "AIRPORT_DROPOFF",
        "GUEST_TRANSFER",
        "VIP_TRANSPORT",
        "STAFF_SHUTTLE",
    }
)
DELIVERY_REQUEST_TYPES = frozenset(
    {
        "SUPPLIER_PICKUP",
        "FOOD_DELIVERY",
        "CATERING_DELIVERY",
        "BANQUET_LOGISTICS",
    }
)
AMBIGUOUS_REQUEST_TYPES = frozenset({"BRANCH_TRANSFER", "OTHER"})


def category_for_request_type(request_type):
    if request_type in PASSENGER_REQUEST_TYPES:
        return PASSENGER_TRANSPORT
    if request_type in DELIVERY_REQUEST_TYPES:
        return DELIVERY_LOGISTICS
    return None


def validate_request_semantics(values):
    """Return the resolved category and field errors for one complete request state."""
    request_type = values.get("request_type")
    supplied_category = values.get("request_category")
    derived_category = category_for_request_type(request_type)
    errors = {}

    if derived_category:
        if supplied_category and supplied_category != derived_category:
            errors["request_category"] = f"{request_type} must use {derived_category}."
        category = derived_category
    else:
        category = supplied_category
        if request_type in AMBIGUOUS_REQUEST_TYPES and not category:
            errors["request_category"] = "This request type requires an explicit request category."

    passenger_count = values.get("passenger_count")
    if category == PASSENGER_TRANSPORT and passenger_count is not None and passenger_count < 1:
        errors["passenger_count"] = "Passenger transport requires at least one passenger."
    if category == DELIVERY_LOGISTICS:
        if not str(values.get("load_description") or "").strip():
            errors["load_description"] = "Delivery/logistics requires a load description."
        if values.get("load_quantity") is None and values.get("estimated_weight_kg") is None:
            message = "Provide load quantity or estimated weight in kilograms."
            errors["load_quantity"] = message
            errors["estimated_weight_kg"] = message

    return category, errors
