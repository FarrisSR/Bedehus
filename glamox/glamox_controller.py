# glamox/glamox_controller.py
import requests
from typing import Optional
from .common import (
    load_secrets, auth,
    resolve_room_id, get_room_status, set_room_target,
)


class glamox_controller:
    """Drop-in i samme ånd som mill_controller, men rom velges ved init én gang."""

    def __init__(self, room_name: str):
        self.room_name = room_name
        s = load_secrets()
        self.api = s["API_URL"]
        self.account_id = s["ACCOUNT_ID"]
        self.api_password = s["API_PASSWORD"]
        self._token: Optional[str] = None
        self._room_id: Optional[int] = None  # caches

    def _ensure_auth(self):
        if not self._token:
            self._token = auth(self.api, self.account_id, self.api_password)

    def _ensure_room_id(self):
        if self._room_id is None:
            self._ensure_auth()
            self._room_id = resolve_room_id(
                self.api, self._token, self.room_name)

    def set_temperature(self, value: float):
        try:
            self._ensure_room_id()
            return set_room_target(self.api, self._token, self._room_id, float(value))
        except requests.RequestException as e:
            print(f"Feil ved å sette temperatur: {e}")
            return None

    def get_control_status(self):
        try:
            self._ensure_room_id()
            return get_room_status(self.api, self._token, self._room_id)
        except requests.RequestException as e:
            print(f"Feil ved henting av kontrollstatus: {e}")
            return None
