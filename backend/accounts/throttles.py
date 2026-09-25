from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class TwoFactorVerifyThrottle(AnonRateThrottle):
    scope = "two_factor_verify"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class PasswordResetCompletionThrottle(AnonRateThrottle):
    scope = "password_reset_completion"
