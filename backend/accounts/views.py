import time

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from fleet.models import Driver
from fleet.serializers import driver_eligibility

from .audit import permission_diff, record_audit_event
from .login_security import LOCKOUT_DETAIL, authenticate_staff_password
from .models import (
    AuditEvent,
    VALID_MODULE_ACTIONS,
    RolePermission,
    StaffProfile,
    TwoFactorCredential,
    TwoFactorRecoveryCode,
    UserNotification,
)
from .password_recovery import send_password_reset_email
from .permissions import DriverAccess, StaffAccess
from .roles import (
    has_module_permission,
    is_driver_identity,
    requires_mfa,
    resolve_role,
    user_data,
)
from .serializers import (
    AuditEventSerializer,
    ChangePasswordSerializer,
    DriverPasswordSetupSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    ManagedStaffCreateSerializer,
    ManagedStaffRoleSerializer,
    ManagedStaffStatusSerializer,
    ResetPasswordSerializer,
    RolePermissionReplaceSerializer,
    StaffPasswordSetupSerializer,
    TwoFactorCodeSerializer,
    TwoFactorDisableSerializer,
    TwoFactorEnrollmentConfirmSerializer,
    TwoFactorVerifySerializer,
)
from .session_security import (
    end_authenticated_session,
    establish_authenticated_session,
    invalidate_authenticated_sessions,
    record_meaningful_activity,
)
from .staff_invitations import (
    INVITATION_NOT_SENT,
    INVITATION_SENT,
    send_staff_setup_email,
)
from .throttles import (
    LoginThrottle,
    PasswordResetCompletionThrottle,
    PasswordResetThrottle,
    TwoFactorVerifyThrottle,
)
from .two_factor import (
    CHALLENGE_MAX_ATTEMPTS,
    ChallengeCacheUnavailable,
    InvalidSecondFactor,
    ReplayedTotp,
    TwoFactorConfigurationError,
    claim_challenge,
    consume_challenge,
    create_challenge,
    decrypt_secret,
    encrypt_secret,
    issue_recovery_codes,
    load_challenge,
    matched_totp_time_step,
    provisioning_data,
    record_challenge_failure,
    release_challenge_claim,
    verify_recovery_code,
    verify_totp,
)


class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


def notification_data(notification):
    return {
        "id": notification.pk,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "target_url": notification.target_url,
        "is_read": notification.is_read,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class AuditEventPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class FleetAdminAuditAccess(StaffAccess):
    def has_permission(self, request, view):
        return (
            super().has_permission(request, view)
            and resolve_role(request.user) == StaffProfile.Role.FLEET_ADMIN
        )


class AuditEventListView(APIView):
    permission_classes = [FleetAdminAuditAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        queryset = AuditEvent.objects.select_related("actor").order_by("-occurred_at", "-pk")
        filters = {
            "occurred_after": "occurred_at__gte",
            "occurred_before": "occurred_at__lte",
            "actor": "actor_id",
            "action": "action",
            "target_type": "target_type",
            "outcome": "outcome",
        }
        unknown = set(request.query_params) - set(filters) - {"page", "page_size"}
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        for param, lookup in filters.items():
            value = request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{lookup: value})
        paginator = AuditEventPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AuditEventSerializer(page, many=True).data)


class NotificationListView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        unknown = set(request.query_params) - {"unread_only", "page", "page_size"}
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        unread_only = request.query_params.get("unread_only", "false").lower()
        if unread_only not in {"true", "false"}:
            raise serializers.ValidationError({"unread_only": "Must be true or false."})
        queryset = UserNotification.objects.filter(recipient=request.user)
        if unread_only == "true":
            queryset = queryset.filter(is_read=False)
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([notification_data(item) for item in page])


class NotificationUnreadCountView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        count = UserNotification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({"unread_count": count})


class NotificationMarkReadView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["post", "options"]

    def post(self, request, notification_id):
        notification = get_object_or_404(
            UserNotification, pk=notification_id, recipient=request.user
        )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=("is_read", "read_at"))
        return Response(notification_data(notification))


class NotificationMarkAllReadView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["post", "options"]

    def post(self, request):
        updated = UserNotification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({"updated": updated})


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
        auth_result = authenticate_staff_password(
            request,
            serializer.validated_data["username"],
            serializer.validated_data["password"],
        )
        if auth_result.temporarily_locked:
            target_user = (
                get_user_model()
                .objects.filter(username=serializer.validated_data["username"])
                .first()
            )
            reason = (
                "failed_login_threshold"
                if auth_result.account_locked
                else "temporarily_locked"
            )
            record_audit_event(
                action="ACCOUNT_LOCKED" if auth_result.account_locked else "LOGIN_FAILURE",
                actor=target_user,
                target=target_user,
                outcome=AuditEvent.Outcome.DENIED,
                request=request,
                metadata={"reason": reason},
            )
            return Response(
                {
                    "detail": LOCKOUT_DETAIL,
                    "code": "temporarily_locked",
                    "retry_after_seconds": auth_result.retry_after_seconds,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user = auth_result.user
        if user is None or resolve_role(user) is None:
            record_audit_event(
                action="LOGIN_FAILURE",
                outcome=AuditEvent.Outcome.FAILURE,
                request=request,
                metadata={"reason": "invalid_credentials"},
            )
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        if auth_result.lock_expired:
            record_audit_event(
                action="ACCOUNT_LOCK_EXPIRED",
                actor=user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
            )
        credential = TwoFactorCredential.objects.filter(user=user, is_enabled=True).first()
        if credential:
            try:
                decrypt_secret(credential.encrypted_secret)
            except TwoFactorConfigurationError:
                return Response(
                    {"detail": "Two-factor authentication is temporarily unavailable."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            try:
                challenge_token = create_challenge(user.pk)
            except ChallengeCacheUnavailable:
                return self.two_factor_unavailable()
            return Response({"two_factor_required": True, "challenge_token": challenge_token})
        if requires_mfa(user):
            try:
                import pyotp

                secret = pyotp.random_base32()
                encrypted_secret = encrypt_secret(secret)
                challenge_token = create_challenge(user.pk, purpose="enroll")
            except (ChallengeCacheUnavailable, TwoFactorConfigurationError):
                return self.two_factor_unavailable()
            with transaction.atomic():
                enrollment, _ = TwoFactorCredential.objects.select_for_update().get_or_create(
                    user=user,
                    defaults={"encrypted_secret": encrypted_secret},
                )
                enrollment.encrypted_secret = encrypted_secret
                enrollment.is_enabled = False
                enrollment.enabled_at = None
                enrollment.last_used_time_step = None
                enrollment.save(
                    update_fields=(
                        "encrypted_secret",
                        "is_enabled",
                        "enabled_at",
                        "last_used_time_step",
                        "updated_at",
                    )
                )
                TwoFactorRecoveryCode.objects.filter(credential=enrollment).delete()
            return Response(
                {
                    "mfa_enrollment_required": True,
                    "challenge_token": challenge_token,
                    "setup": provisioning_data(user, secret),
                }
            )
        replaced_session = establish_authenticated_session(request, user)
        record_audit_event(
            action="LOGIN_SUCCESS",
            actor=user,
            target=user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
            metadata={"mfa": "not_required"},
        )
        if replaced_session:
            record_audit_event(
                action="SESSION_REVOKED",
                actor=user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                metadata={"reason": "new_login_replaced_previous_session"},
            )
        return Response({"user": user_data(user), "csrf_token": get_token(request)})

    @staticmethod
    def two_factor_unavailable():
        return Response(
            {"detail": "Two-factor authentication is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@method_decorator(csrf_protect, name="dispatch")
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users = get_user_model().objects.filter(
            email__iexact=serializer.validated_data["email"],
            is_active=True,
            is_staff=True,
        ).select_related("staff_profile")
        for user in users:
            if resolve_role(user) is not None and user.has_usable_password():
                send_password_reset_email(user)
        return Response(
            {
                "detail": (
                    "If an eligible account matches that email, "
                    "a password reset link has been sent."
                )
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetCompletionThrottle]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            user_id = force_str(urlsafe_base64_decode(values["uid"]))
            user = get_user_model().objects.select_related("staff_profile").get(pk=user_id)
        except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
            return self.invalid_link_response()
        if (
            resolve_role(user) is None
            or not user.has_usable_password()
            or not default_token_generator.check_token(user, values["token"])
        ):
            return self.invalid_link_response()
        try:
            validate_password(values["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error
        with transaction.atomic():
            user.set_password(values["new_password"])
            user.save(update_fields=["password"])
            revoked = invalidate_authenticated_sessions(user)
            record_audit_event(
                action="PASSWORD_RESET_COMPLETED",
                actor=user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                metadata={"sessions_revoked": revoked},
            )
            if revoked:
                record_audit_event(
                    action="SESSION_REVOKED",
                    actor=user,
                    target=user,
                    outcome=AuditEvent.Outcome.SUCCESS,
                    request=request,
                    metadata={"reason": "password_reset"},
                )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def invalid_link_response():
        return Response(
            {"detail": "Invalid or expired password reset link."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@method_decorator(csrf_protect, name="dispatch")
class ChangePasswordView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if not request.user.check_password(values["current_password"]):
            raise serializers.ValidationError(
                {"current_password": ["Current password is incorrect."]}
            )
        try:
            validate_password(values["new_password"], user=request.user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error
        request.user.set_password(values["new_password"])
        request.user.save(update_fields=["password"])
        record_audit_event(
            action="PASSWORD_CHANGED",
            actor=request.user,
            target=request.user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
        )
        end_authenticated_session(request, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffTwoFactorMixin:
    permission_classes = [StaffAccess]

    @staticmethod
    def service_unavailable():
        return Response(
            {"detail": "Two-factor authentication is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class TwoFactorStatusView(StaffTwoFactorMixin, APIView):
    def get(self, request):
        credential = TwoFactorCredential.objects.filter(user=request.user).first()
        enabled = bool(credential and credential.is_enabled)
        remaining = (
            TwoFactorRecoveryCode.objects.filter(
                credential=credential, used_at__isnull=True
            ).count()
            if enabled
            else 0
        )
        return Response(
            {
                "enabled": enabled,
                "required": requires_mfa(request.user),
                "recovery_codes_remaining": remaining,
                "enabled_at": credential.enabled_at if enabled else None,
            }
        )


class TwoFactorSetupView(StaffTwoFactorMixin, APIView):
    http_method_names = ["post", "options"]

    def post(self, request):
        if not isinstance(request.data, dict) or request.data:
            raise serializers.ValidationError({"non_field_errors": ["Request body must be empty."]})
        try:
            import pyotp

            secret = pyotp.random_base32()
            encrypted_secret = encrypt_secret(secret)
        except TwoFactorConfigurationError:
            return self.service_unavailable()
        with transaction.atomic():
            credential, created = TwoFactorCredential.objects.select_for_update().get_or_create(
                user=request.user,
                defaults={"encrypted_secret": encrypted_secret},
            )
            if not created and credential.is_enabled:
                return Response(
                    {"detail": "Two-factor authentication is already enabled."},
                    status=status.HTTP_409_CONFLICT,
                )
            if not created:
                credential.encrypted_secret = encrypted_secret
                credential.last_used_time_step = None
                credential.save(
                    update_fields=["encrypted_secret", "last_used_time_step", "updated_at"]
                )
                TwoFactorRecoveryCode.objects.filter(credential=credential).delete()
        return Response(provisioning_data(request.user, secret))


class TwoFactorConfirmView(StaffTwoFactorMixin, APIView):
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = TwoFactorCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                credential = TwoFactorCredential.objects.select_for_update().get(user=request.user)
                if credential.is_enabled:
                    return Response(
                        {"detail": "Two-factor authentication is already enabled."},
                        status=status.HTTP_409_CONFLICT,
                    )
                time_step = matched_totp_time_step(
                    decrypt_secret(credential.encrypted_secret),
                    serializer.validated_data["code"],
                )
                if time_step is None:
                    return Response(
                        {"detail": "Invalid authenticator code."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                credential.is_enabled = True
                credential.enabled_at = timezone.now()
                credential.last_used_time_step = time_step
                credential.save(
                    update_fields=["is_enabled", "enabled_at", "last_used_time_step", "updated_at"]
                )
                recovery_codes = issue_recovery_codes(credential)
                record_audit_event(
                    action="MFA_ENABLED",
                    actor=request.user,
                    target=request.user,
                    outcome=AuditEvent.Outcome.SUCCESS,
                    request=request,
                    metadata={"method": "totp", "recovery_codes_issued": len(recovery_codes)},
                )
        except TwoFactorCredential.DoesNotExist:
            return Response(
                {"detail": "No pending two-factor setup exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TwoFactorConfigurationError:
            return self.service_unavailable()
        return Response({"recovery_codes": recovery_codes})


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorEnrollmentConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TwoFactorVerifyThrottle]
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = TwoFactorEnrollmentConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        token = values["challenge_token"]
        try:
            challenge = load_challenge(token)
        except ChallengeCacheUnavailable:
            return TwoFactorVerifyView.service_unavailable()
        if not challenge or challenge.get("purpose") != "enroll":
            return TwoFactorVerifyView.invalid_challenge()
        try:
            claim_id = claim_challenge(token)
        except ChallengeCacheUnavailable:
            return TwoFactorVerifyView.service_unavailable()
        if not claim_id:
            return TwoFactorVerifyView.invalid_challenge()
        consumed = False
        try:
            with transaction.atomic():
                user = (
                    get_user_model()
                    .objects.select_related("staff_profile")
                    .get(pk=challenge["user_id"])
                )
                credential = TwoFactorCredential.objects.select_for_update().get(user=user)
                if not user.is_active or not requires_mfa(user) or credential.is_enabled:
                    return TwoFactorVerifyView.invalid_challenge()
                time_step = matched_totp_time_step(
                    decrypt_secret(credential.encrypted_secret), values["code"]
                )
                if time_step is None:
                    raise InvalidSecondFactor
                consumed = consume_challenge(token, claim_id)
                if not consumed:
                    return TwoFactorVerifyView.invalid_challenge()
                credential.is_enabled = True
                credential.enabled_at = timezone.now()
                credential.last_used_time_step = time_step
                credential.save(
                    update_fields=(
                        "is_enabled",
                        "enabled_at",
                        "last_used_time_step",
                        "updated_at",
                    )
                )
                recovery_codes = issue_recovery_codes(credential)
        except (get_user_model().DoesNotExist, TwoFactorCredential.DoesNotExist):
            return TwoFactorVerifyView.invalid_challenge()
        except InvalidSecondFactor:
            try:
                attempts = record_challenge_failure(
                    token, claim_id, challenge["expires_at"] - time.time()
                )
            except ChallengeCacheUnavailable:
                return TwoFactorVerifyView.service_unavailable()
            if attempts is None or attempts >= CHALLENGE_MAX_ATTEMPTS:
                return TwoFactorVerifyView.invalid_challenge()
            return Response(
                {"detail": "Invalid authenticator code."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (ChallengeCacheUnavailable, TwoFactorConfigurationError):
            return TwoFactorVerifyView.service_unavailable()
        finally:
            if not consumed:
                try:
                    release_challenge_claim(token, claim_id)
                except ChallengeCacheUnavailable:
                    pass
        replaced_session = establish_authenticated_session(request, user)
        record_audit_event(
            action="MFA_ENABLED",
            actor=user,
            target=user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
            metadata={"method": "totp", "recovery_codes_issued": len(recovery_codes)},
        )
        record_audit_event(
            action="LOGIN_SUCCESS",
            actor=user,
            target=user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
            metadata={"mfa": "enrolled"},
        )
        if replaced_session:
            record_audit_event(
                action="SESSION_REVOKED",
                actor=user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                metadata={"reason": "new_login_replaced_previous_session"},
            )
        return Response(
            {
                "user": user_data(user),
                "csrf_token": get_token(request),
                "recovery_codes": recovery_codes,
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TwoFactorVerifyThrottle]

    def post(self, request):
        serializer = TwoFactorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        token = values["challenge_token"]
        try:
            challenge = load_challenge(token)
        except ChallengeCacheUnavailable:
            return self.service_unavailable()
        if not challenge:
            return self.invalid_challenge()
        if challenge.get("purpose", "verify") != "verify":
            return self.invalid_challenge()
        try:
            claim_id = claim_challenge(token)
        except ChallengeCacheUnavailable:
            return self.service_unavailable()
        if not claim_id:
            return self.invalid_challenge()
        consumed = False
        try:
            user = (
                get_user_model()
                .objects.select_related("two_factor_credential")
                .get(pk=challenge["user_id"])
            )
            credential = user.two_factor_credential
            if not user.is_active or resolve_role(user) is None or not credential.is_enabled:
                return self.invalid_challenge()
            if values["method"] == "totp":
                verify_totp(credential.pk, values["code"])
            else:
                verify_recovery_code(credential.pk, values["code"])
                record_audit_event(
                    action="RECOVERY_CODE_USED",
                    actor=user,
                    target=user,
                    outcome=AuditEvent.Outcome.SUCCESS,
                    request=request,
                    metadata={
                        "remaining": TwoFactorRecoveryCode.objects.filter(
                            credential=credential, used_at__isnull=True
                        ).count()
                    },
                )
        except (get_user_model().DoesNotExist, TwoFactorCredential.DoesNotExist):
            return self.invalid_challenge()
        except TwoFactorConfigurationError:
            return Response(
                {"detail": "Two-factor authentication is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (InvalidSecondFactor, ReplayedTotp):
            try:
                attempts = record_challenge_failure(
                    token,
                    claim_id,
                    challenge["expires_at"] - time.time(),
                )
            except ChallengeCacheUnavailable:
                return self.service_unavailable()
            if attempts is None or attempts >= CHALLENGE_MAX_ATTEMPTS:
                return self.invalid_challenge()
            return Response(
                {"detail": "Invalid authenticator code."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except ChallengeCacheUnavailable:
            return self.service_unavailable()
        else:
            try:
                consumed = consume_challenge(token, claim_id)
            except ChallengeCacheUnavailable:
                return self.service_unavailable()
            if not consumed:
                return self.invalid_challenge()
            replaced_session = establish_authenticated_session(request, user)
            record_audit_event(
                action="LOGIN_SUCCESS",
                actor=user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                metadata={"mfa": values["method"]},
            )
            if replaced_session:
                record_audit_event(
                    action="SESSION_REVOKED",
                    actor=user,
                    target=user,
                    outcome=AuditEvent.Outcome.SUCCESS,
                    request=request,
                    metadata={"reason": "new_login_replaced_previous_session"},
                )
            return Response({"user": user_data(user), "csrf_token": get_token(request)})
        finally:
            if not consumed:
                try:
                    release_challenge_claim(token, claim_id)
                except ChallengeCacheUnavailable:
                    pass

    @staticmethod
    def service_unavailable():
        return Response(
            {"detail": "Two-factor authentication is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def invalid_challenge():
        return Response(
            {"detail": "Invalid or expired two-factor challenge."},
            status=status.HTTP_401_UNAUTHORIZED,
        )


class TwoFactorDisableView(StaffTwoFactorMixin, APIView):
    http_method_names = ["post", "options"]

    def post(self, request):
        if requires_mfa(request.user):
            record_audit_event(
                action="MFA_DISABLE_REJECTED",
                actor=request.user,
                target=request.user,
                outcome=AuditEvent.Outcome.DENIED,
                request=request,
                metadata={"reason": "role_requires_mfa"},
            )
            return Response(
                {"detail": "MFA is required for this role."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TwoFactorDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if not check_password(values["current_password"], request.user.password):
            return Response(
                {"detail": "Current password or second factor is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            credential = TwoFactorCredential.objects.get(user=request.user, is_enabled=True)
            if values["method"] == "totp":
                verify_totp(credential.pk, values["code"])
            else:
                verify_recovery_code(credential.pk, values["code"])
                record_audit_event(
                    action="RECOVERY_CODE_USED",
                    actor=request.user,
                    target=request.user,
                    outcome=AuditEvent.Outcome.SUCCESS,
                    request=request,
                    metadata={
                        "remaining": TwoFactorRecoveryCode.objects.filter(
                            credential=credential, used_at__isnull=True
                        ).count()
                    },
                )
        except TwoFactorCredential.DoesNotExist:
            return Response(
                {"detail": "Two-factor authentication is not enabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (InvalidSecondFactor, ReplayedTotp):
            return Response(
                {"detail": "Current password or second factor is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TwoFactorConfigurationError:
            return self.service_unavailable()
        credential.delete()
        record_audit_event(
            action="MFA_DISABLED",
            actor=request.user,
            target=request.user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
            metadata={"method": values["method"]},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [StaffAccess]

    def get(self, request):
        return Response({"user": user_data(request.user)})


class LogoutView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        record_audit_event(
            action="LOGOUT",
            actor=request.user,
            target=request.user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
        )
        end_authenticated_session(request, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionActivityView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["post", "options"]

    def post(self, request):
        if not isinstance(request.data, dict) or request.data:
            raise serializers.ValidationError({"non_field_errors": ["Request body must be empty."]})
        record_meaningful_activity(request)
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


class FleetAdminManagedStaffMixin:
    permission_classes = [StaffAccess]

    def require_fleet_admin(self, request, action):
        if not has_module_permission(request.user, "USERS_ACCESS", action):
            self.permission_denied(request, message="Only a Fleet Admin can manage staff accounts.")

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


class ManagedStaffListCreateView(FleetAdminManagedStaffMixin, APIView):
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        self.require_fleet_admin(request, "VIEW_USERS")
        users = (
            get_user_model()
            .objects.filter(is_staff=True, is_superuser=False, staff_profile__isnull=False)
            .select_related("staff_profile")
            .order_by("username", "pk")
        )
        return Response({"results": [managed_staff_data(user) for user in users]})

    def post(self, request):
        self.require_fleet_admin(request, "CREATE_USER")
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
            record_audit_event(
                action="STAFF_CREATED",
                actor=request.user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                changes={"role": {"old": None, "new": values["role"]}},
                metadata={"setup_status": "pending"},
            )
        user = user_model.objects.select_related("staff_profile").get(pk=user.pk)
        delivery = send_staff_setup_email(user)
        if delivery == INVITATION_SENT:
            record_audit_event(
                action="STAFF_INVITED",
                actor=request.user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
            )
        return Response(
            {
                **managed_staff_data(user),
                "invitation_delivery": delivery,
            },
            status=status.HTTP_201_CREATED,
        )


class ManagedStaffRoleView(FleetAdminManagedStaffMixin, APIView):
    http_method_names = ["patch", "options"]

    def patch(self, request, user_id):
        self.require_fleet_admin(request, "ASSIGN_ROLE")
        serializer = ManagedStaffRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_managed_user(user_id)
        old_role = user.staff_profile.role
        new_role = serializer.validated_data["role"]
        with transaction.atomic():
            user.staff_profile.role = new_role
            user.staff_profile.save(update_fields=["role"])
            record_audit_event(
                action="STAFF_ROLE_CHANGED",
                actor=request.user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                changes={"role": {"old": old_role, "new": new_role}},
            )
        return Response(managed_staff_data(user))


class ManagedStaffStatusView(FleetAdminManagedStaffMixin, APIView):
    http_method_names = ["patch", "options"]

    def patch(self, request, user_id):
        self.require_fleet_admin(request, "CHANGE_USER_STATUS")
        serializer = ManagedStaffStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_managed_user(user_id)
        old_active = user.is_active
        new_active = serializer.validated_data["is_active"]
        with transaction.atomic():
            user.is_active = new_active
            user.save(update_fields=["is_active"])
            record_audit_event(
                action="STAFF_STATUS_CHANGED",
                actor=request.user,
                target=user,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                changes={"is_active": {"old": old_active, "new": new_active}},
            )
        return Response(managed_staff_data(user))


class ManagedStaffInvitationView(FleetAdminManagedStaffMixin, APIView):
    http_method_names = ["post", "options"]

    def post(self, request, user_id):
        self.require_fleet_admin(request, "EDIT_USER")
        if request.data:
            raise serializers.ValidationError({"non_field_errors": ["Request body must be empty."]})
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
        record_audit_event(
            action="STAFF_INVITED",
            actor=request.user,
            target=user,
            outcome=AuditEvent.Outcome.SUCCESS,
            request=request,
        )
        return Response({"invitation_delivery": INVITATION_SENT})


def permission_matrix_data():
    managed_roles = [
        role for role in StaffProfile.Role.values if role != StaffProfile.Role.FLEET_ADMIN
    ]
    roles = {role: {module: [] for module in VALID_MODULE_ACTIONS} for role in managed_roles}
    for permission in RolePermission.objects.filter(role__in=managed_roles):
        roles[permission.role][permission.module].append(permission.action)
    return {
        "roles": roles,
        "definitions": {module: list(actions) for module, actions in VALID_MODULE_ACTIONS.items()},
    }


class RolePermissionListView(FleetAdminManagedStaffMixin, APIView):
    http_method_names = ["get", "options"]

    def get(self, request):
        self.require_fleet_admin(request, "MANAGE_ROLE_PERMISSIONS")
        return Response(permission_matrix_data())


class RolePermissionReplaceView(FleetAdminManagedStaffMixin, APIView):
    http_method_names = ["put", "options"]

    def put(self, request, role):
        self.require_fleet_admin(request, "MANAGE_ROLE_PERMISSIONS")
        if role not in StaffProfile.Role.values:
            raise serializers.ValidationError({"role": ["Unsupported managed role."]})
        if role == StaffProfile.Role.FLEET_ADMIN:
            raise serializers.ValidationError(
                {"role": ["Fleet Admin access is not managed through this matrix."]}
            )
        serializer = RolePermissionReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        permissions = serializer.validated_data["permissions"]
        with transaction.atomic():
            before = list(
                RolePermission.objects.filter(role=role).values_list("module", "action")
            )
            RolePermission.objects.filter(role=role).delete()
            RolePermission.objects.bulk_create(
                RolePermission(role=role, **permission) for permission in permissions
            )
            diff = permission_diff(
                before,
                [(item["module"], item["action"]) for item in permissions],
            )
            record_audit_event(
                action="ROLE_PERMISSIONS_REPLACED",
                actor=request.user,
                target_type="RolePermission",
                target_id=role,
                target_label=role,
                outcome=AuditEvent.Outcome.SUCCESS,
                request=request,
                metadata=diff,
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
        if is_driver_identity(user):
            driver = Driver.objects.filter(linked_user=user).first()
        if driver is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response({"driver": driver_data(user, driver), "csrf_token": get_token(request)})


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
            not is_driver_identity(user)
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
