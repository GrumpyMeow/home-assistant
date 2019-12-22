"""Onvif network device abstraction."""

import asyncio
import os

import onvif
from onvif import ONVIFCamera

from homeassistant.const import (
    CONF_DEVICE,
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_CAMERA, CONF_EVENTS, CONF_MODEL, DOMAIN, LOGGER
from .errors import CannotConnect


class OnvifNetworkDevice:
    """Manages a Onvif device."""

    def __init__(self, hass, config_entry):
        """Initialize the device."""
        self.hass = hass
        self.config_entry = config_entry
        self.available = True

        # self.api = None
        self.device = None
        self.fw_version = None

        self.listeners = []

    @property
    def host(self):
        """Return the host of this device."""
        return self.config_entry.data[CONF_DEVICE][CONF_HOST]

    @property
    def model(self):
        """Return the model of this device."""
        return self.config_entry.data[CONF_MODEL]

    @property
    def name(self):
        """Return the name of this device."""
        return self.config_entry.data[CONF_NAME]

    @property
    def serial(self):
        """Return the mac of this device."""
        return self.config_entry.data[CONF_MAC]

    async def async_update_device_registry(self):
        """Update device registry."""
        device_registry = await self.hass.helpers.device_registry.async_get_registry()
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            connections={(CONNECTION_NETWORK_MAC, self.serial)},
            identifiers={(DOMAIN, self.serial)},
            manufacturer="Onvif",
            model=f"{self.model}",
            name=self.name,
            sw_version=self.fw_version,
        )

    async def async_setup(self):
        """Set up the device."""
        try:
            self.device = await get_device(
                self.hass, self.config_entry.data[CONF_DEVICE]
            )

        except CannotConnect:
            raise ConfigEntryNotReady

        except Exception:  # pylint: disable=broad-except
            LOGGER.error("Unknown error connecting with Onvif device on %s", self.host)
            return False

        devicemgmt = self.device.create_devicemgmt_service()
        device_information = await devicemgmt.GetDeviceInformation()

        self.fw_version = device_information.FirmwareVersion

        if self.config_entry.options[CONF_CAMERA]:

            self.hass.async_create_task(
                self.hass.config_entries.async_forward_entry_setup(
                    self.config_entry, "camera"
                )
            )

        if self.config_entry.options[CONF_EVENTS]:

            # self.api.stream.connection_status_callback = (
            #     self.async_connection_status_callback
            # )
            # self.api.enable_events(event_callback=self.async_event_callback)

            platform_tasks = [
                self.hass.config_entries.async_forward_entry_setup(
                    self.config_entry, platform
                )
                for platform in ["binary_sensor", "switch"]
            ]
            self.hass.async_create_task(self.start(platform_tasks))

        self.config_entry.add_update_listener(self.async_new_address_callback)

        return True

    @property
    def event_new_address(self):
        """Device specific event to signal new device address."""
        return f"onvif_new_address_{self.serial}"

    @staticmethod
    async def async_new_address_callback(hass, entry):
        """Handle signals of device getting new address.

        This is a static method because a class method (bound method),
        can not be used with weak references.
        """
        device = hass.data[DOMAIN][entry.data[CONF_MAC]]
        # device.api.config.host = device.host
        async_dispatcher_send(hass, device.event_new_address)

    @property
    def event_reachable(self):
        """Device specific event to signal a change in connection status."""
        return f"onvif_reachable_{self.serial}"

    @callback
    def async_connection_status_callback(self, status):
        """Handle signals of device connection status.

        This is called on every RTSP keep-alive message.
        Only signal state change if state change is true.
        """

        self.available = not self.available
        async_dispatcher_send(self.hass, self.event_reachable, True)
        # if self.available != (status == SIGNAL_PLAYING):
        #     self.available = not self.available
        #     async_dispatcher_send(self.hass, self.event_reachable, True)

    @property
    def event_new_sensor(self):
        """Device specific event to signal new sensor available."""
        return f"onvif_add_sensor_{self.serial}"

    @callback
    def async_event_callback(self, action, event_id):
        """Call to configure events when initialized on event stream."""
        if action == "add":
            async_dispatcher_send(self.hass, self.event_new_sensor, event_id)

    async def start(self, platform_tasks):
        """Start the event stream when all platforms are loaded."""
        await asyncio.gather(*platform_tasks)
        # self.api.start()

    @callback
    def shutdown(self, event):
        """Stop the event stream."""
        # self.api.stop()

    async def async_reset(self):
        """Reset this device to default state."""
        platform_tasks = []

        if self.config_entry.options[CONF_CAMERA]:
            platform_tasks.append(
                self.hass.config_entries.async_forward_entry_unload(
                    self.config_entry, "camera"
                )
            )

        if self.config_entry.options[CONF_EVENTS]:
            # self.api.stop()
            platform_tasks += [
                self.hass.config_entries.async_forward_entry_unload(
                    self.config_entry, platform
                )
                for platform in ["binary_sensor", "switch"]
            ]

        await asyncio.gather(*platform_tasks)

        for unsub_dispatcher in self.listeners:
            unsub_dispatcher()
        self.listeners = []

        return True


async def get_device(hass, config):
    """Create a Onvif device."""

    # device = onvif.OnvifDevice(
    #     loop=hass.loop,
    #     host=config[CONF_HOST],
    #     username=config[CONF_USERNAME],
    #     password=config[CONF_PASSWORD],
    #     port=config[CONF_PORT],
    #     web_proto="http",
    # )

    device = ONVIFCamera(
        config[CONF_HOST],
        config[CONF_PORT],
        config[CONF_USERNAME],
        config[CONF_PASSWORD],
        "{}/wsdl/".format(os.path.dirname(onvif.__file__)),
    )

    return device

    # device.vapix.initialize_params(preload_data=False)
    # device.vapix.initialize_ports()

    # try:
    #     with async_timeout.timeout(15):

    #         await asyncio.gather(
    #             hass.async_add_executor_job(device.vapix.params.update_brand),
    #             hass.async_add_executor_job(device.vapix.params.update_properties),
    #             hass.async_add_executor_job(device.vapix.ports.update),
    #         )

    #     return device

    # except onvif.Unauthorized:
    #     LOGGER.warning(
    #         "Connected to device at %s but not registered.", config[CONF_HOST]
    #     )
    #     raise AuthenticationRequired

    # except (asyncio.TimeoutError, onvif.RequestError):
    #     LOGGER.error("Error connecting to the Onvif device at %s", config[CONF_HOST])
    #     raise CannotConnect

    # except onvif.OnvifException:
    #     LOGGER.exception("Unknown Onvif communication error occurred")
    #     raise AuthenticationRequired
