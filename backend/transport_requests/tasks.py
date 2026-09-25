from celery import shared_task

from .flight_tracking import refresh_flight_context
from .models import TransportRequest, TransportRequestFlightContext


@shared_task
def refresh_active_airport_pickup_flights():
    contexts = TransportRequestFlightContext.objects.filter(
        transport_request__request_type=TransportRequest.RequestType.AIRPORT_PICKUP,
        transport_request__status__in=(
            TransportRequest.Status.FOR_APPROVAL,
            TransportRequest.Status.APPROVED,
            TransportRequest.Status.READY_FOR_DISPATCH,
        ),
    )
    refreshed = 0
    for context in contexts.iterator():
        refresh_flight_context(context)
        refreshed += 1
    return {"considered": refreshed}
