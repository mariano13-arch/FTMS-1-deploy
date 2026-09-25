from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import ModuleActionAccess, StaffAccess

from .maintenance import model_info, predict, readiness


class ModelInfoView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "MAINTENANCE"
    permission_action = "VIEW"

    def get(self, request):
        return Response(model_info())


class ReadinessView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "MAINTENANCE"
    permission_action = "VIEW"

    def get(self, request):
        return Response(readiness())


class PredictView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "MAINTENANCE"
    permission_action = "VIEW"

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        return Response(predict(body.get("inputs"), body.get("source_mode")))
