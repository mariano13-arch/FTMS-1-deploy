from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
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

from .models import VALID_MODULE_ACTIONS, RolePermission, StaffProfile
from .permissions import DriverAccess, StaffAccess
from .roles import SUPER_ADMIN, resolve_role, user_data
from .serializers import (
    DriverPasswordSetupSerializer,
    LoginSerializer,
    ManagedStaffCreateSerializer,
    ManagedStaffRoleSerializer,
    ManagedStaffStatusSerializer,
    RolePermissionReplaceSerializer,
    StaffPasswordSetupSerializer,
)
from .staff_invitations import (
    INVITATION_NOT_SENT,
    INVITATION_SENT,
    send_staff_setup_email,
)
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


def managed_staff_data(user):
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.staff_profile.role,
        "is_active": user.is_active,
        "setup_status": "complete" if user.has_usable_password() else "pending",
        "date_joined": user.date_joined,
        "last_login": user.last_login,
    }


class SuperAdminManagedStaffMixin:
    permission_classes = [StaffAccess]

    def require_super_admin(self, request):
        if resolve_role(request.user) != SUPER_ADMIN:
            self.permission_denied(
                request, message="Only a Super Admin can manage staff accounts."
            )

    @staticmethod
    def get_managed_user(user_id):
        user = get_object_or_404(
            get_user_model().objects.select_related("staff_profile"), pk=user_id
        )
        if user.is_superuser:
            raise serializers.ValidationError(
                {"user": ["Django superusers cannot be modified here."]}
            )
        if not user.is_staff:
            raise serializers.ValidationError({"user": ["User is not a staff account."]})
        try:
            staff_profile = user.staff_profile
        except StaffProfile.DoesNotExist as error:
            raise serializers.ValidationError(
                {"user": ["Staff account has no valid StaffProfile."]}
            ) from error
        del staff_profile
        return user


class ManagedStaffListCreateView(SuperAdminManagedStaffMixin, APIView):
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        self.require_super_admin(request)
        users = (
            get_user_model()
            .objects.filter(
                is_staff=True, is_superuser=False, staff_profile__isnull=False
            )
            .select_related("staff_profile")
            .order_by("username", "pk")
        )
        return Response({"results": [managed_staff_data(user) for user in users]})

    def post(self, request):
        self.require_super_admin(request)
        serializer = ManagedStaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        user_model = get_user_model()
        username = user_model.normalize_username(values["username"].strip())
        if user_model.objects.filter(username=username).exists():
            raise serializers.ValidationError(
                {"username": ["A user with that username already exists."]}
            )
        user = user_model(
            username=username,
            email=values.get("email", ""),
            first_name=values.get("first_name", ""),
            last_name=values.get("last_name", ""),
            is_active=True,
            is_staff=True,
            is_superuser=False,
        )
        user.set_unusable_password()
        try:
            user.full_clean(exclude=["password"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        with transaction.atomic():
            user.save()
            StaffProfile.objects.create(user=user, role=values["role"])
        user = user_model.objects.select_related("staff_profile").get(pk=user.pk)
        return Response(
            {
                **managed_staff_data(user),
                "invitation_delivery": send_staff_setup_email(user),
            },
            status=status.HTTP_201_CREATED,
        )


class ManagedStaffRoleView(SuperAdminManagedStaffMixin, APIView):
    http_method_names = ["patch", "options"]

    def patch(self, request, user_id):
        self.require_super_admin(request)
        serializer = ManagedStaffRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_managed_user(user_id)
        user.staff_profile.role = serializer.validated_data["role"]
        user.staff_profile.save(update_fields=["role"])
        return Response(managed_staff_data(user))


class ManagedStaffStatusView(SuperAdminManagedStaffMixin, APIView):
    http_method_names = ["patch", "options"]

    def patch(self, request, user_id):
        self.require_super_admin(request)
        serializer = ManagedStaffStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_managed_user(user_id)
        user.is_active = serializer.validated_data["is_active"]
        user.save(update_fields=["is_active"])
        return Response(managed_staff_data(user))


class ManagedStaffInvitationView(SuperAdminManagedStaffMixin, APIView):
    http_method_names = ["post", "options"]

    def post(self, request, user_id):
        self.require_super_admin(request)
        if request.data:
            raise serializers.ValidationError(
                {"non_field_errors": ["Request body must be empty."]}
            )
        user = self.get_managed_user(user_id)
        if not user.is_active:
            raise serializers.ValidationError(
                {"user": ["Invitation cannot be sent to an inactive account."]}
            )
        if user.has_usable_password():
            raise serializers.ValidationError(
                {"user": ["Staff account setup is already complete."]}
            )
        delivery = send_staff_setup_email(user)
        if delivery != INVITATION_SENT:
            return Response(
                {
                    "invitation_delivery": INVITATION_NOT_SENT,
                    "detail": "Invitation email could not be delivered.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"invitation_delivery": INVITATION_SENT})


def permission_matrix_data():
    roles = {
        role: {module: [] for module in VALID_MODULE_ACTIONS}
        for role in StaffProfile.Role.values
    }
    for permission in RolePermission.objects.all():
        roles[permission.role][permission.module].append(permission.action)
    return {
        "roles": roles,
        "definitions": {
            module: list(actions) for module, actions in VALID_MODULE_ACTIONS.items()
        },
    }


class RolePermissionListView(SuperAdminManagedStaffMixin, APIView):
    http_method_names = ["get", "options"]

    def get(self, request):
        self.require_super_admin(request)
        return Response(permission_matrix_data())


class RolePermissionReplaceView(SuperAdminManagedStaffMixin, APIView):
    http_method_names = ["put", "options"]

    def put(self, request, role):
        self.require_super_admin(request)
        if role not in StaffProfile.Role.values:
            raise serializers.ValidationError({"role": ["Unsupported managed role."]})
        serializer = RolePermissionReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        permissions = serializer.validated_data["permissions"]
        with transaction.atomic():
            RolePermission.objects.filter(role=role).delete()
            RolePermission.objects.bulk_create(
                RolePermission(role=role, **permission) for permission in permissions
            )
        return Response(permission_matrix_data())


@method_decorator(csrf_protect, name="dispatch")
class StaffPasswordSetupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = StaffPasswordSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            user_id = force_str(urlsafe_base64_decode(values["uid"]))
            user = get_user_model().objects.select_related("staff_profile").get(pk=user_id)
        except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
            return self.invalid_link_response()
        try:
            staff_profile = user.staff_profile
        except StaffProfile.DoesNotExist:
            return self.invalid_link_response()
        del staff_profile
        if (
            not user.is_active
            or not user.is_staff
            or user.is_superuser
            or user.has_usable_password()
            or not default_token_generator.check_token(user, values["token"])
        ):
            return self.invalid_link_response()
        try:
            validate_password(values["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"new_password": error.messages}
            ) from error
        user.set_password(values["new_password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def invalid_link_response():
        return Response(
            {"detail": "Invalid or expired setup link."},
            status=status.HTTP_400_BAD_REQUEST,
        )


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
