from unittest.mock import patch

from django.db import DatabaseError, connection
from django.test import TestCase
from rest_framework.test import APIClient


class HealthViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_reports_database_connection(self):
        self.assertEqual(
            connection.settings_dict["ENGINE"],
            "django.contrib.gis.db.backends.postgis",
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            postgis_version = cursor.fetchone()[0]

        self.assertTrue(postgis_version)
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "service": "ftms-backend", "database": "ok"},
        )

    def test_health_returns_503_when_database_is_unavailable(self):
        with patch("health.views.connection.cursor", side_effect=DatabaseError):
            response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "status": "error",
                "service": "ftms-backend",
                "database": "unavailable",
            },
        )
