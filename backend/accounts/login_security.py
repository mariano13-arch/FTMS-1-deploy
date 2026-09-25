from datetime import timedelta
from dataclasses import dataclass

from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.utils import timezone

from .models import StaffLoginSecurityState
from .roles import resolve_role

FAILED_LOGIN_THRESHOLD = 5
LOCKOUT_DURATION = timedelta(minutes=15)
LOCKOUT_DETAIL = "Too many failed sign-in attempts. Please wait before trying again."


@dataclass(frozen=True)
class AuthenticationResult:
    user: object | None = None
    temporarily_locked: bool = False
    retry_after_seconds: int | None = None
    account_locked: bool = False
    lock_expired: bool = False


def _retry_after_seconds(locked_until, now):
    return max(0, int((locked_until - now).total_seconds()))


def authenticate_staff_password(request, username, password):
    """Authenticate staff and atomically maintain account-level lockout state."""
    user_model = get_user_model()
    with transaction.atomic():
        user = (
            user_model.objects.select_for_update()
            .filter(username=username)
            .first()
        )
        if user is None:
            # Keep the normal password-hasher timing work for unknown identities.
            authenticate(request, username=username, password=password)
            return AuthenticationResult()

        state, _ = StaffLoginSecurityState.objects.select_for_update().get_or_create(user=user)
        now = timezone.now()
        if state.locked_until is not None:
            if state.locked_until > now:
                return AuthenticationResult(
                    temporarily_locked=True,
                    retry_after_seconds=_retry_after_seconds(state.locked_until, now),
                )
            state.failed_login_attempts = 0
            state.locked_until = None
            state.save(update_fields=("failed_login_attempts", "locked_until", "updated_at"))
            lock_expired = True
        else:
            lock_expired = False

        authenticated = authenticate(request, username=username, password=password)
        if authenticated is None or resolve_role(authenticated) is None:
            state.failed_login_attempts += 1
            if state.failed_login_attempts >= FAILED_LOGIN_THRESHOLD:
                state.locked_until = now + LOCKOUT_DURATION
            state.save(update_fields=("failed_login_attempts", "locked_until", "updated_at"))
            if state.locked_until is not None:
                return AuthenticationResult(
                    temporarily_locked=True,
                    retry_after_seconds=_retry_after_seconds(state.locked_until, now),
                    account_locked=True,
                )
            return AuthenticationResult()

        if state.failed_login_attempts or state.locked_until is not None:
            state.failed_login_attempts = 0
            state.locked_until = None
            state.save(update_fields=("failed_login_attempts", "locked_until", "updated_at"))
        return AuthenticationResult(user=authenticated, lock_expired=lock_expired)
