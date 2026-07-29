from django.db import DatabaseError, connection
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return Response(
            {"status": "error", "service": "ftms-backend", "database": "unavailable"},
            status=503,
        )
    return Response({"status": "ok", "service": "ftms-backend", "database": "ok"})
