"""Domain-specific LightWeave errors."""


class LightWeaveError(Exception):
    """Base class for expected LightWeave failures."""


class EnvelopeError(LightWeaveError):
    """The `.lwv` container is invalid or unsupported."""


class IntegrityError(EnvelopeError):
    """The payload digest does not match the envelope."""


class ModelMismatchError(LightWeaveError):
    """The decoder model does not match the encoder model fingerprint."""


class PayloadTooLargeError(LightWeaveError):
    """The encoded artifact exceeds the configured link budget."""


class NPUExecutionError(LightWeaveError):
    """Strict QNN NPU execution could not be completed or proven."""
