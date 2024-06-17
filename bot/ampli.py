from typing import Optional, TypeVar
from concurrent.futures import ThreadPoolExecutor

from amplitude import Amplitude, BaseEvent, EventOptions

from bot.config import config


Event = TypeVar("Event", bound=BaseEvent)

executor = ThreadPoolExecutor(max_workers=5)


class Ampli:
    def __init__(self, api_key: str):
        self.client = Amplitude(api_key=api_key)
        self.client.configuration.server_zone = 'US'

    def track(self, user_id: str, event: Event, event_options: Optional[EventOptions] = None):
        if not event_options:
            event_options = EventOptions()
        event_options["user_id"] = user_id
        event.load_event_options(event_options)
        self.client.track(event)

    def flush(self):
        self.client.flush()

    def shutdown(self):
        self.client.shutdown()


amplitude = Ampli(api_key=config.amplitude_api_key)


class UserRegistrationEvent(BaseEvent):
    def __init__(self):
        super().__init__(event_type="User Registration")


class UserSendTextEvent(BaseEvent):
    def __init__(self):
        super().__init__(event_type="Text Message")


class UserSendVoiceEvent(BaseEvent):
    def __init__(self):
        super().__init__(event_type="Voice Message")


class UserSendPhotoEvent(BaseEvent):
    def __init__(self):
        super().__init__(event_type="Photo Message")


class PhotoRecognitionEvent(BaseEvent):
    def __init__(self):
        super().__init__(event_type="Photo Recognition")


class ValueValidationEvent(BaseEvent):
    def __init__(self):
        super().__init__(event_type="Value Validation")