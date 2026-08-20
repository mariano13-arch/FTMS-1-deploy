from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from fleet.models import Driver
from fleet.serializers import driver_eligibility

from .permissions import DriverAccess, StaffAccess
from .roles import resolve_role, user_data
from .serializers import DriverPasswordSetupSerializer, LoginSerializer
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


def driver_data(user, driver):
    full_name = " ".join(
        part for part in (driver.first_name, driver.middle_name, driver.last_name) if part
    )
    eligibility_status, eligibility_reasons = driver_eligibility(driver)
    return {
        "user_id": user.pk,
        "username": user.username,
        "driver_id": driver.pk,
        "driver_code": driver.driver_code,
        "display_name": full_name,
        "email": driver.email,
        "employment_status": driver.employment_status,
        "employment_status_label": driver.get_employment_status_display(),
        "license_number": driver.license_number,
        "license_expiry_date": driver.license_expiry_date,
        "medical_certificate_expiry_date": driver.medical_certificate_expiry_date,
        "eligibility_status": eligibility_status,
        "eligibility_reasons": eligibility_reasons,
    }


@method_decorator(csrf_protect, name="dispatch")
class DriverLoginView(APIView):
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
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        driver = None
        if user is not None and user.is_active:
            driver = Driver.objects.filter(linked_user=user).first()
        if driver is None:
            return Response(
                {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )
        login(request, user)
        return Response(
            {"driver": driver_data(user, driver), "csrf_token": get_token(request)}
        )


class DriverMeView(APIView):
    permission_classes = [DriverAccess]

    def get(self, request):
        return Response({"driver": driver_data(request.user, request.driver)})


class DriverLogoutView(APIView):
    permission_classes = [DriverAccess]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class DriverPasswordSetupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = DriverPasswordSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            user_id = force_str(urlsafe_base64_decode(values["uid"]))
            user = get_user_model().objects.select_related("driver_record").get(pk=user_id)
        except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
            return self.invalid_link_response()

        if (
            not user.is_active
            or user.has_usable_password()
            or not hasattr(user, "driver_record")
            or not default_token_generator.check_token(user, values["token"])
        ):
            return self.invalid_link_response()

        try:
            validate_password(values["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error

        user.set_password(values["new_password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def invalid_link_response():
        return Response(
            {"detail": "Invalid or expired setup link."},
            status=status.HTTP_400_BAD_REQUEST,
        )
