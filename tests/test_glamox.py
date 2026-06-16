import pytest
from unittest.mock import patch, MagicMock

from glamox.common import resolve_room_id, get_room_status, set_room_target


ROOMS = [
    {"id": "42", "name": "Storsalen", "temperature": 2100, "targetTemperature": 1700},
    {"id": "7", "name": "Bønnerom", "temperature": 1850, "targetTemperature": 1700},
]


class TestResolveRoomId:
    def test_finds_existing_room(self):
        with patch("glamox.common.list_rooms", return_value=ROOMS):
            assert resolve_room_id("http://api", "tok", "Storsalen") == 42

    def test_finds_second_room(self):
        with patch("glamox.common.list_rooms", return_value=ROOMS):
            assert resolve_room_id("http://api", "tok", "Bønnerom") == 7

    def test_raises_for_unknown_room(self):
        with patch("glamox.common.list_rooms", return_value=ROOMS):
            with pytest.raises(RuntimeError, match="Ukjent"):
                resolve_room_id("http://api", "tok", "Ukjent")


class TestGetRoomStatus:
    def test_temperature_converted_from_centi(self):
        with patch("glamox.common.list_rooms", return_value=ROOMS):
            status = get_room_status("http://api", "tok", 42)
        assert status["temperature"] == 21.0
        assert status["targetTemperature"] == 17.0

    def test_returns_correct_room_name(self):
        with patch("glamox.common.list_rooms", return_value=ROOMS):
            status = get_room_status("http://api", "tok", 7)
        assert status["room"] == "Bønnerom"
        assert status["temperature"] == 18.5

    def test_raises_for_unknown_id(self):
        with patch("glamox.common.list_rooms", return_value=ROOMS):
            with pytest.raises(RuntimeError):
                get_room_status("http://api", "tok", 999)


class TestSetRoomTarget:
    def _mock_post(self):
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {}
        return mock

    def test_converts_celsius_to_centi(self):
        with patch("requests.post", return_value=self._mock_post()) as mock_post:
            set_room_target("http://api", "tok", 42, 21.0)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["rooms"][0]["targetTemperature"] == "2100"

    def test_rounds_half_degrees(self):
        with patch("requests.post", return_value=self._mock_post()) as mock_post:
            set_room_target("http://api", "tok", 42, 17.5)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["rooms"][0]["targetTemperature"] == "1750"

    def test_sends_correct_room_id(self):
        with patch("requests.post", return_value=self._mock_post()) as mock_post:
            set_room_target("http://api", "tok", 42, 21.0)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["rooms"][0]["id"] == 42

    def test_includes_bearer_token(self):
        with patch("requests.post", return_value=self._mock_post()) as mock_post:
            set_room_target("http://api", "tok", 42, 21.0)
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer tok"
