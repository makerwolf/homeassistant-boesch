"""Modbus- und Web-Client gegen gemockte Gegenstellen."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import aiohttp
import pytest
from pymodbus.exceptions import ConnectionException, ModbusIOException

from custom_components.boesch.modbus_client import BoeschModbusClient, ModbusError
from custom_components.boesch.web_client import (
    TYPE_SINGLE,
    BoeschWebClient,
    WebAuthError,
    WebError,
)

# --------------------------------------------------------------------------
#  Modbus
# --------------------------------------------------------------------------


@pytest.fixture
async def modbus() -> BoeschModbusClient:
    # async: pymodbus braucht beim Anlegen einen laufenden Event-Loop.
    client = BoeschModbusClient("192.0.2.10", 502)
    client._client = MagicMock()
    client._client.connect = AsyncMock(return_value=True)
    type(client._client).connected = PropertyMock(return_value=True)
    return client


def _result(registers=None, error=False) -> MagicMock:
    result = MagicMock()
    result.isError.return_value = error
    result.registers = registers or []
    return result


async def test_read_block(modbus) -> None:
    modbus._client.read_holding_registers = AsyncMock(return_value=_result([1, 2]))
    assert await modbus.read_block(100, 2, 40) == [1, 2]
    modbus._client.read_holding_registers.assert_awaited_once_with(
        100, count=2, **{modbus._unit_kw: 40}
    )


@pytest.mark.parametrize("exc", [ModbusIOException("timeout"), ConnectionException("weg")])
async def test_read_pymodbus_exception_mapped(modbus, exc) -> None:
    """Neuere pymodbus werfen statt ein Fehlerergebnis zu liefern."""
    modbus._client.read_holding_registers = AsyncMock(side_effect=exc)
    with pytest.raises(ModbusError):
        await modbus.read_block(100, 2, 40)


async def test_read_error_result(modbus) -> None:
    modbus._client.read_holding_registers = AsyncMock(return_value=_result(error=True))
    with pytest.raises(ModbusError):
        await modbus.read_block(100, 2, 40)


async def test_reconnect_fails(modbus) -> None:
    type(modbus._client).connected = PropertyMock(return_value=False)
    modbus._client.connect = AsyncMock(return_value=False)
    with pytest.raises(ModbusError, match="Verbindung"):
        await modbus.read_block(100, 2, 40)


async def test_write_pymodbus_exception_mapped(modbus) -> None:
    modbus._client.write_register = AsyncMock(side_effect=ModbusIOException("timeout"))
    with pytest.raises(ModbusError):
        await modbus.write_register(102, 500, 50)


# --------------------------------------------------------------------------
#  Webinterface (Kermi x-center)
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status=200, body: Any = None, *, html=False, cookie=None) -> None:
        self.status = status
        self.ok = status < 400
        self.content_type = "text/html" if html else "application/json"
        self._body = body
        self.cookies = {}
        if cookie:
            self.cookies["XCenter"] = MagicMock(value=cookie)

    async def json(self, content_type=None):
        return self._body

    def raise_for_status(self) -> None:
        if not self.ok:
            raise aiohttp.ClientResponseError(MagicMock(), (), status=self.status)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None


class FakeSession:
    """Spielt eine feste Abfolge von Antworten ab und merkt sich die Aufrufe."""

    def __init__(self, logins: list[FakeResponse], requests: list[FakeResponse]) -> None:
        self._logins = logins
        self._requests = requests
        self.calls: list[tuple[str, str, Any, dict | None]] = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(("LOGIN", url, json, None))
        return self._logins.pop(0)

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json, headers))
        return self._requests.pop(0)


def _login_ok(cookie="abc") -> FakeResponse:
    return FakeResponse(body={"isValid": True}, cookie=cookie)


def _ok(data) -> FakeResponse:
    return FakeResponse(body={"StatusCode": 0, "ResponseData": data})


async def test_web_login_and_read() -> None:
    session = FakeSession(
        [_login_ok()],
        [_ok([{"DatapointConfigId": "a", "Value": 34.5}, {"DatapointConfigId": "b", "Value": "NaN"}])],
    )
    client = BoeschWebClient(session, "192.0.2.10", "pw")
    assert await client.async_read("dev", ["a", "b"]) == {"a": 34.5, "b": None}
    _, _, payload, headers = session.calls[1]
    assert headers == {"Cookie": "XCenter=abc"}
    assert payload["IgnoreErrors"] is True


async def test_web_wrong_password() -> None:
    session = FakeSession([FakeResponse(body={"isValid": False})], [])
    with pytest.raises(WebAuthError):
        await BoeschWebClient(session, "h", "falsch").async_login()


async def test_web_login_without_cookie() -> None:
    session = FakeSession([FakeResponse(body={"isValid": True})], [])
    with pytest.raises(WebError, match="Cookie"):
        await BoeschWebClient(session, "h", "pw").async_login()


async def test_web_session_expired_relogin() -> None:
    """Abgelaufene Session liefert HTML -> einmal neu anmelden, wiederholen."""
    session = FakeSession(
        [_login_ok("alt"), _login_ok("neu")],
        [FakeResponse(html=True), _ok([])],
    )
    client = BoeschWebClient(session, "h", "pw")
    assert await client.async_read("dev", ["a"]) == {}
    assert [c[0] for c in session.calls] == ["LOGIN", "POST", "LOGIN", "POST"]
    assert session.calls[3][3] == {"Cookie": "XCenter=neu"}


async def test_web_session_expired_twice_gives_up() -> None:
    session = FakeSession(
        [_login_ok(), _login_ok()],
        [FakeResponse(status=401), FakeResponse(status=401)],
    )
    with pytest.raises(WebError, match="Session"):
        await BoeschWebClient(session, "h", "pw").async_read("dev", ["a"])


async def test_web_status_code_error() -> None:
    session = FakeSession(
        [_login_ok()],
        [FakeResponse(body={"StatusCode": 5, "DisplayText": "Lesen nicht erlaubt"})],
    )
    with pytest.raises(WebError, match="Lesen nicht erlaubt"):
        await BoeschWebClient(session, "h", "pw").async_read("dev", ["a"])


async def test_web_get_device_id() -> None:
    devices = [{"Address": 40, "DeviceId": "wanda"}, {"Address": "50", "DeviceId": "hb"}]
    session = FakeSession([_login_ok()], [_ok(devices), _ok(devices)])
    client = BoeschWebClient(session, "h", "pw")
    assert await client.async_get_device_id(50) == "hb"
    with pytest.raises(WebError):
        await client.async_get_device_id(99)


async def test_web_write_single_as_string() -> None:
    """Kommazahlen schickt die Web-UI als String, `$type` zuerst."""
    session = FakeSession([_login_ok()], [_ok(None)])
    await BoeschWebClient(session, "h", "pw").async_write("dev", "cid", TYPE_SINGLE, 34.0)
    value = session.calls[1][2]["DatapointValues"][0]
    assert next(iter(value)) == "$type"
    assert value["Value"] == "34"


async def test_web_timeout_mapped() -> None:
    session = FakeSession([_login_ok()], [])
    session.request = MagicMock(side_effect=TimeoutError)
    with pytest.raises(WebError):
        await BoeschWebClient(session, "h", "pw").async_read("dev", ["a"])


async def test_unit_keyword_detected() -> None:
    """pymodbus-Parametername (device_id vs. slave) wird an der Signatur erkannt."""
    assert BoeschModbusClient("h", 502)._unit_kw in ("device_id", "slave")
