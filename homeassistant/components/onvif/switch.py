"""Support for Onvif switches."""

# from onvif.event_stream import CLASS_OUTPUT

from homeassistant.components.switch import SwitchDevice
from homeassistant.const import CONF_MAC
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN as ONVIF_DOMAIN
from .onvif_base import OnvifEventBase


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up a Onvif switch."""
    serial_number = config_entry.data[CONF_MAC]
    device = hass.data[ONVIF_DOMAIN][serial_number]

    @callback
    def async_add_switch(event_id):
        """Add switch from Onvif device."""
        event = device.api.event.events[event_id]

        async_add_entities([OnvifSwitch(event, device)], True)
        # if event.CLASS == CLASS_OUTPUT:
        #     async_add_entities([OnvifSwitch(event, device)], True)

    device.listeners.append(
        async_dispatcher_connect(hass, device.event_new_sensor, async_add_switch)
    )


class OnvifSwitch(OnvifEventBase, SwitchDevice):
    """Representation of a Onvif switch."""

    @property
    def is_on(self):
        """Return true if event is active."""
        return self.event.is_tripped

    async def async_turn_on(self, **kwargs):
        """Turn on switch."""
        action = "/"
        await self.hass.async_add_executor_job(
            self.device.api.vapix.ports[self.event.id].action, action
        )

    async def async_turn_off(self, **kwargs):
        """Turn off switch."""
        action = "\\"
        await self.hass.async_add_executor_job(
            self.device.api.vapix.ports[self.event.id].action, action
        )

    @property
    def name(self):
        """Return the name of the event."""
        # if self.event.id and self.device.api.vapix.ports[self.event.id].name:
        #     return "{} {}".format(
        #         self.device.name, self.device.api.vapix.ports[self.event.id].name
        #     )

        return super().name
