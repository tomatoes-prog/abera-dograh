"""One guard for the optional upstream managed-service integration."""

from api import constants


class MPSDisabledError(ValueError):
    def __init__(self):
        super().__init__(
            "Los servicios administrados de Dograh están desactivados. "
            "Configura tu proveedor de IA en Modelos."
        )


def require_mps_enabled() -> None:
    if not constants.ENABLE_DOGRAH_MPS:
        raise MPSDisabledError()
