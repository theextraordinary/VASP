class VASPError(Exception):
    """Base error type for VASP."""


class ModelAPIError(VASPError):
    """Raised when Gemma endpoint calls fail or return invalid output."""
