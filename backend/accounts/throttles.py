from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class TwoFactorVerifyThrottle(AnonRateThrottle):
    scope = "two_factor_verify"
