from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import StaffAccess
from .roles import resolve_role, user_data
from .serializers import LoginSerializer
from .throttles import LoginThrottle


class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response(
                {"non_field_errors": ["Expected a JSON object."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request, username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None or resolve_role(user) is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response({"user": user_data(user), "csrf_token": get_token(request)})


class MeView(APIView):
    permission_classes = [StaffAccess]

    def get(self, request):
        return Response({"user": user_data(request.user)})


class LogoutView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
