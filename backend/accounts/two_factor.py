import hashlib
import json
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from redis.exceptions import RedisError

from .models import TwoFactorCredential, TwoFactorRecoveryCode

CHALLENGE_TTL_SECONDS = 300
CHALLENGE_MAX_ATTEMPTS = 5
CHALLENGE_CLAIM_TTL_SECONDS = 60
TOTP_VALID_WINDOW = 1
RECOVERY_CODE_COUNT = 8


class TwoFactorConfigurationError(Exception):
    pass


class InvalidSecondFactor(Exception):
    pass


class ReplayedTotp(Exception):
    pass


class ChallengeCacheUnavailable(Exception):
    pass


def _fernet():
    key = settings.TWO_FACTOR_ENCRYPTION_KEY
    if not key:
        raise TwoFactorConfigurationError
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (TypeError, ValueError) as error:
        raise TwoFactorConfigurationError from error


def encrypt_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(encrypted_secret):
    try:
        return _fernet().decrypt(encrypted_secret.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as error:
        raise TwoFactorConfigurationError from error


def provisioning_data(user, secret):
    account_name = user.email or user.username
    totp = pyotp.TOTP(secret, digits=6, interval=30, digest=hashlib.sha1)
    return {
        "provisioning_uri": totp.provisioning_uri(name=account_name, issuer_name="FTMS"),
        "manual_setup_key": secret,
        "issuer": "FTMS",
        "account_label": account_name,
    }


def generate_recovery_codes():
    return [secrets.token_urlsafe(9).upper() for _ in range(RECOVERY_CODE_COUNT)]


def issue_recovery_codes(credential):
    codes = generate_recovery_codes()
    TwoFactorRecoveryCode.objects.filter(credential=credential).delete()
    TwoFactorRecoveryCode.objects.bulk_create(
        TwoFactorRecoveryCode(credential=credential, code_hash=make_password(code))
        for code in codes
    )
    return codes


def matched_totp_time_step(secret, code, now=None):
    timestamp = time.time() if now is None else now
    totp = pyotp.TOTP(secret, digits=6, interval=30, digest=hashlib.sha1)
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        candidate_time = timestamp + offset * totp.interval
        if totp.verify(code, for_time=candidate_time, valid_window=0):
            return int(candidate_time // totp.interval)
    return None


def verify_totp(credential_id, code):
    with transaction.atomic():
        credential = TwoFactorCredential.objects.select_for_update().get(pk=credential_id)
        if not credential.is_enabled:
            raise InvalidSecondFactor
        time_step = matched_totp_time_step(decrypt_secret(credential.encrypted_secret), code)
        if time_step is None:
            raise InvalidSecondFactor
        if (
            credential.last_used_time_step is not None
            and time_step <= credential.last_used_time_step
        ):
            raise ReplayedTotp
        credential.last_used_time_step = time_step
        credential.save(update_fields=["last_used_time_step", "updated_at"])
    return credential


def verify_recovery_code(credential_id, code):
    with transaction.atomic():
        credential = TwoFactorCredential.objects.select_for_update().get(pk=credential_id)
        if not credential.is_enabled:
            raise InvalidSecondFactor
        recovery_codes = TwoFactorRecoveryCode.objects.select_for_update().filter(
            credential=credential, used_at__isnull=True
        )
        for recovery_code in recovery_codes:
            if check_password(code, recovery_code.code_hash):
                recovery_code.used_at = timezone.now()
                recovery_code.save(update_fields=["used_at"])
                return credential
    raise InvalidSecondFactor


def challenge_key(token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    return f"accounts:two-factor-challenge:{digest}"


def _challenge_attempt_key(token):
    return f"{challenge_key(token)}:attempts"


def _challenge_claim_key(token):
    return f"{challenge_key(token)}:claim"


def _redis_client():
    backend = getattr(cache, "_cache", None)
    get_client = getattr(backend, "get_client", None)
    if get_client is None:
        raise ChallengeCacheUnavailable
    try:
        return get_client(write=True)
    except (AttributeError, OSError, RedisError, TypeError) as error:
        raise ChallengeCacheUnavailable from error


def _cache_operation(operation):
    try:
        return operation(_redis_client())
    except (OSError, RedisError, TypeError, ValueError) as error:
        raise ChallengeCacheUnavailable from error


def _decode_challenge(raw):
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        value = json.loads(raw)
        if not isinstance(value, dict):
            return None
        if not isinstance(value.get("user_id"), int):
            return None
        if value.get("purpose", "verify") not in {"verify", "enroll"}:
            return None
        if not isinstance(value.get("expires_at"), (int, float)):
            return None
        return value
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def create_challenge(user_id, purpose="verify"):
    token = secrets.token_urlsafe(32)
    state = json.dumps(
        {
            "user_id": user_id,
            "purpose": purpose,
            "expires_at": time.time() + CHALLENGE_TTL_SECONDS,
        }
    )
    if not _cache_operation(
        lambda client: client.set(challenge_key(token), state, ex=CHALLENGE_TTL_SECONDS)
    ):
        raise ChallengeCacheUnavailable
    return token


def load_challenge(token):
    key = challenge_key(token)
    value = _cache_operation(lambda client: _decode_challenge(client.get(key)))
    if value is None or value["expires_at"] <= time.time():
        _cache_operation(lambda client: client.delete(key))
        return None
    return value


def claim_challenge(token):
    claim_id = secrets.token_urlsafe(16)
    claimed = _cache_operation(
        lambda client: client.set(
            _challenge_claim_key(token),
            claim_id,
            nx=True,
            ex=CHALLENGE_CLAIM_TTL_SECONDS,
        )
    )
    return claim_id if claimed else None


def _release_claim(client, token, claim_id):
    return client.eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) end return 0",
        1,
        _challenge_claim_key(token),
        claim_id,
    )


def release_challenge_claim(token, claim_id):
    _cache_operation(lambda client: _release_claim(client, token, claim_id))


def record_challenge_failure(token, claim_id, ttl_seconds):
    result = _cache_operation(
        lambda client: client.eval(
            "if redis.call('get', KEYS[1]) ~= ARGV[1] or "
            "redis.call('exists', KEYS[2]) == 0 then return -1 end "
            "local attempts = redis.call('incr', KEYS[3]) "
            "if attempts == 1 then redis.call('expire', KEYS[3], ARGV[2]) end "
            "if attempts >= tonumber(ARGV[3]) then "
            "redis.call('del', KEYS[1], KEYS[2], KEYS[3]) else "
            "redis.call('del', KEYS[1]) end return attempts",
            3,
            _challenge_claim_key(token),
            challenge_key(token),
            _challenge_attempt_key(token),
            claim_id,
            str(max(1, int(ttl_seconds))),
            str(CHALLENGE_MAX_ATTEMPTS),
        )
    )
    return None if result == -1 else int(result)


def consume_challenge(token, claim_id):
    return bool(
        _cache_operation(
            lambda client: client.eval(
                "if redis.call('get', KEYS[1]) ~= ARGV[1] or "
                "redis.call('exists', KEYS[2]) == 0 then return 0 end "
                "redis.call('del', KEYS[1], KEYS[2], KEYS[3]) return 1",
                3,
                _challenge_claim_key(token),
                challenge_key(token),
                _challenge_attempt_key(token),
                claim_id,
            )
        )
    )
