from unittest.mock import patch, MagicMock
from requests.exceptions import ConnectionError as RequestsConnectionError

from mill_controller.mill_controller import mill_controller


def _mock_response(json_data=None):
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = json_data or {}
    return mock


class TestSetTemperature:
    def test_posts_to_correct_endpoint(self):
        with patch("requests.post", return_value=_mock_response()) as mock_post:
            mill_controller("192.168.1.50").set_temperature(21)
        url = mock_post.call_args.args[0]
        assert url == "http://192.168.1.50/set-temperature"

    def test_sends_value_and_type_in_payload(self):
        with patch("requests.post", return_value=_mock_response()) as mock_post:
            mill_controller("192.168.1.50", "Normal").set_temperature(21)
        payload = mock_post.call_args.kwargs["json"]
        assert payload == {"type": "Normal", "value": 21}

    def test_custom_temp_type_in_payload(self):
        with patch("requests.post", return_value=_mock_response()) as mock_post:
            mill_controller("192.168.1.50", "Away").set_temperature(17)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "Away"

    def test_returns_none_on_network_error(self):
        with patch("requests.post", side_effect=RequestsConnectionError("timeout")):
            result = mill_controller("192.168.1.50").set_temperature(21)
        assert result is None

    def test_returns_response_json_on_success(self):
        with patch("requests.post", return_value=_mock_response({"status": "ok"})):
            result = mill_controller("192.168.1.50").set_temperature(21)
        assert result == {"status": "ok"}


class TestGetControlStatus:
    def test_gets_correct_endpoint(self):
        with patch("requests.get", return_value=_mock_response()) as mock_get:
            mill_controller("192.168.1.50").get_control_status()
        url = mock_get.call_args.args[0]
        assert url == "http://192.168.1.50/control-status"

    def test_returns_none_on_network_error(self):
        with patch("requests.get", side_effect=RequestsConnectionError("timeout")):
            result = mill_controller("192.168.1.50").get_control_status()
        assert result is None

    def test_returns_response_json_on_success(self):
        with patch("requests.get", return_value=_mock_response({"temperature": 21.0})):
            result = mill_controller("192.168.1.50").get_control_status()
        assert result == {"temperature": 21.0}
