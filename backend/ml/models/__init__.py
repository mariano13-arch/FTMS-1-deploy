from django.db import models


class FuelPrediction(models.Model):
    vehicle = models.ForeignKey(
        "fleet.Vehicle",
        on_delete=models.PROTECT,
        related_name="fuel_predictions",
    )
    input_timestamp = models.DateTimeField()
    predicted_at = models.DateTimeField(auto_now_add=True)
    estimated_fuel_lph = models.DecimalField(max_digits=10, decimal_places=4)
    model_name = models.CharField(max_length=160)
    model_version = models.CharField(max_length=80)
    source_mode = models.CharField(max_length=40, default="explicit_validated_api")
    validated_inputs = models.JSONField()

    class Meta:
        ordering = ("-input_timestamp", "-predicted_at", "-pk")
        indexes = [
            models.Index(
                fields=["vehicle", "-input_timestamp"],
                name="fuel_pred_vehicle_time_idx",
            ),
            models.Index(fields=["input_timestamp"], name="fuel_pred_time_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle", "input_timestamp", "model_version"],
                name="fuel_prediction_source_unique",
            )
        ]

    def __str__(self):
        return f"{self.vehicle.device_id} {self.input_timestamp} {self.estimated_fuel_lph} L/h"
