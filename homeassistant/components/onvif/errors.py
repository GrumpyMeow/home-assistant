"""Errors for the Onvif component."""
from homeassistant.exceptions import HomeAssistantError


class OnvifException(HomeAssistantError):
    """Base class for Onvif exceptions."""


class AlreadyConfigured(OnvifException):
    """Device is already configured."""


class AuthenticationRequired(OnvifException):
    """Unknown error occurred."""


class CannotConnect(OnvifException):
    """Unable to connect to the device."""


class UserLevel(OnvifException):
    """User level too low."""
