"""Custom exception hierarchy for MyndLens."""


class MyndLensError(Exception):
    """Base error."""
    def __init__(self, message: str, code: str = "MYNDLENS_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class AuthError(MyndLensError):
    """Authentication / authorization failures."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTH_ERROR")


class SessionError(MyndLensError):
    """Session management failures."""
    def __init__(self, message: str = "Session error"):
        super().__init__(message, code="SESSION_ERROR")


class PresenceError(MyndLensError):
    """Heartbeat / presence violations."""
    def __init__(self, message: str = "Presence check failed"):
        super().__init__(message, code="PRESENCE_ERROR")


class EnvGuardError(MyndLensError):
    """Environment separation violations."""
    def __init__(self, message: str = "Environment guard violation"):
        super().__init__(message, code="ENV_GUARD_ERROR")


class DispatchBlockedError(MyndLensError):
    """Dispatch refused (heartbeat stale, wrong env, etc.)."""
    def __init__(self, message: str = "Dispatch blocked"):
        super().__init__(message, code="DISPATCH_BLOCKED")
