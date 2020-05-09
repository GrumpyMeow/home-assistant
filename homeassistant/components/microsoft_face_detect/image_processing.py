"""Component that will help set the Microsoft face detect processing."""
import io
import json
import logging
from pathlib import Path

from PIL import Image, ImageDraw, UnidentifiedImageError
import voluptuous as vol

from homeassistant.components.image_processing import (
    ATTR_AGE,
    ATTR_GENDER,
    ATTR_GLASSES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SOURCE,
    PLATFORM_SCHEMA,
    ImageProcessingFaceEntity,
)
from homeassistant.components.microsoft_face import DATA_MICROSOFT_FACE
from homeassistant.core import split_entity_id
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.util.pil import draw_box

_LOGGER = logging.getLogger(__name__)

# Microsoft Face platform supported attributes
ATTR_SMILE = "smile"
ATTR_FACIAL_HAIR = "facialHair"
ATTR_HEADPOSE = "headPose"
ATTR_EMOTION = "emotion"
ATTR_HAIR = "hair"
ATTR_MAKEUP = "makeup"
ATTR_ACCESSORIES = "accessories"
ATTR_BLUR = "blur"
ATTR_EXPOSURE = "exposure"
ATTR_NOISE = "noise"

SUPPORTED_ATTRIBUTES = [
    ATTR_AGE,
    ATTR_GENDER,
    ATTR_GLASSES,
    ATTR_SMILE,
    ATTR_FACIAL_HAIR,
    ATTR_HEADPOSE,
    ATTR_EMOTION,
    ATTR_HAIR,
    ATTR_MAKEUP,
    ATTR_ACCESSORIES,
    ATTR_BLUR,
    ATTR_EXPOSURE,
    ATTR_NOISE,
]

CONF_DETECTIONMODEL = "detectionModel"
CONF_RECOGNITIONMODEL = "recognitionModel"
CONF_ATTRIBUTES = "attributes"
CONF_SAVE_FILE_FOLDER = "save_file_folder"
CONF_SAVE_TIMESTAMPTED_FILE = "save_timestamped_file"
DATETIME_FORMAT = "%Y%m%d%H%M%S"

DEFAULT_ATTRIBUTES = [ATTR_AGE, ATTR_GENDER]


def validate_attributes(list_attributes):
    """Validate face attributes."""
    for attr in list_attributes:
        if attr not in SUPPORTED_ATTRIBUTES:
            raise vol.Invalid(f"Unsupported attribute '{attr}'")
    return list_attributes


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_ATTRIBUTES, default=DEFAULT_ATTRIBUTES): vol.All(
            cv.ensure_list, validate_attributes
        ),
        vol.Optional(CONF_SAVE_FILE_FOLDER): cv.isdir,
        vol.Optional(CONF_SAVE_TIMESTAMPTED_FILE, default=False): cv.boolean,
        vol.Optional(CONF_DETECTIONMODEL, default="detection_01"): cv.string,
        vol.Optional(CONF_RECOGNITIONMODEL, default="recognition_01"): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Microsoft Face detection platform."""
    api = hass.data[DATA_MICROSOFT_FACE]
    attributes = config[CONF_ATTRIBUTES]

    save_file_folder = config.get(CONF_SAVE_FILE_FOLDER)
    if save_file_folder:
        save_file_folder = Path(save_file_folder)

    entities = []
    for camera in config[CONF_SOURCE]:
        entities.append(
            MicrosoftFaceDetectEntity(
                camera[CONF_ENTITY_ID],
                api,
                attributes,
                save_file_folder,
                config[CONF_SAVE_TIMESTAMPTED_FILE],
                config[CONF_DETECTIONMODEL],
                config[CONF_RECOGNITIONMODEL],
                camera.get(CONF_NAME),
            )
        )

    async_add_entities(entities)


class MicrosoftFaceDetectEntity(ImageProcessingFaceEntity):
    """Microsoft Face API entity for identify."""

    def __init__(
        self,
        camera_entity,
        api,
        attributes,
        save_file_folder,
        save_timestamped_file,
        detectionModel,
        recognitionModel,
        name=None,
    ):
        """Initialize Microsoft Face."""
        super().__init__()

        self._api = api
        self._camera = camera_entity
        self._attributes = attributes
        self._save_file_folder = save_file_folder
        self._save_timestamped_file = save_timestamped_file
        self._detection_model = detectionModel
        self._recognition_model = recognitionModel

        if name:
            self._name = name
        else:
            self._name = f"MicrosoftFaceDetect {split_entity_id(camera_entity)[1]}"

    @property
    def camera_entity(self):
        """Return camera entity id from process pictures."""
        return self._camera

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    async def async_process_image(self, image):
        """Process image.

        This method is a coroutine.
        """
        face_data = None
        try:
            face_data = await self._api.call_api(
                "post",
                "detect",
                image,
                binary=True,
                params={
                    "returnFaceId": "true",
                    "returnFaceAttributes": ",".join(self._attributes),
                    "detectionModel": self._detection_model,
                    "recognitionModel": self._recognition_model,
                },
            )
        except HomeAssistantError as err:
            _LOGGER.error("Can't process image: %s", err)
            raise

        if not face_data:
            face_data = []

        faces = []
        for face in face_data:
            face_attr = {}
            for attr in self._attributes:
                if attr in face["faceAttributes"]:
                    face_attr[attr] = face["faceAttributes"][attr]

            if face_attr:
                faces.append(face_attr)

        self.async_process_faces(faces, len(face_data))

        if self._save_file_folder and len(face_data) > 0:
            self.save_image(image, face_data, self._save_file_folder)

    def save_image(self, image, face_data, directory):
        """Save a timestamped image with bounding boxes around detected faces."""
        timestamp = dt_util.now().strftime(DATETIME_FORMAT)
        try:
            img = Image.open(io.BytesIO(bytearray(image))).convert("RGB")
        except UnidentifiedImageError:
            _LOGGER.warning("Unable to process image, bad data")
            return
        draw = ImageDraw.Draw(img)

        # Save image and json as "timestamped"
        if self._save_timestamped_file:
            timestamp_save_path = directory / f"{self._name}_{timestamp}"
            img.save(f"{timestamp_save_path}.jpg")

            with open(f"{timestamp_save_path}.json", "w") as outfile:
                json.dump(face_data, outfile, indent=4, sort_keys=True)

        # Draw bounding boxes
        for face in face_data:
            box = (
                face["faceRectangle"]["top"],
                face["faceRectangle"]["left"],
                face["faceRectangle"]["top"] + face["faceRectangle"]["height"],
                face["faceRectangle"]["left"] + face["faceRectangle"]["width"],
            )
            draw_box(draw, box, 1, 1, str(face["faceId"]))

        # Save image-with-boxes and json as "latest"
        latest_save_path = directory / f"{self._name}_latest"
        img.save(f"{latest_save_path}.jpg")
        with open(f"{latest_save_path}.json", "w") as outfile:
            json.dump(face_data, outfile, indent=4, sort_keys=True)

        # Save image-with-boxes as "timestamped"
        if self._save_timestamped_file:
            timestamp_save_path = directory / f"{self._name}_{timestamp}_boxed"
            img.save(f"{timestamp_save_path}.jpg")
