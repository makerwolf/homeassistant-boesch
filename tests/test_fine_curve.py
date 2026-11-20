"""Feine Heizkurve HK1 (Festwert-Modus, von der Integration gesteuert)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from custom_components.boesch.const import (
    CONF_FINE_BOOST_MAX,
    CONF_FINE_CURVE,
    CONF_FINE_MAX,
    CONF_FINE_MIN,
    CONF_FINE_RAMP_DOWN,
    CONF_FINE_RAMP_UP,
    CONF_FINE_WRITE_INTERVAL,
    CONF_WEB_PASSWORD,
    CONF_WEB_POWER,
    DOMAIN,
)
from custom_components.boesch.fine_curve import (
    ISSUE_STOPPED,
    FineCurveCoordinator,
    interpolate,
    ramp,
    round_setpoint,
)
from custom_components.boesch.web_client import (
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_HEATING_CURVE,
    DP_HK1_HEATING_WATER_MODE,
    TYPE_INT32,
    TYPE_SINGLE,
)

from .conftest import HYDROBOX, WANDA

HB = "dev50"
# Bösch-Kurve der Anlage (Stand 2026-11-19), -20 ... +20 °C.
BOESCH_CURVE = (36.0, 34.0, 34.0, 34.0, 33.0, 32.0, 31.0, 29.0, 21.0)
POINTS = [y + 1 for y in BOESCH_CURVE]  # + Parallelverschiebung H 156 = 1 K


# ---- Reine Rechnung -------------------------------------------------------------


@pytest.mark.parametrize(
    ("outdoor", "expected"),
    [(-30, 37.0), (-20, 37.0), (20, 22.0), (35, 22.0), (6.5, 32.7), (0, 34.0),
     (17.5, 26.0), (-17.5, 36.0)],
)
def test_interpolate(outdoor, expected) -> None:
    assert interpolate(POINTS, outdoor) == pytest.approx(expected)


def test_ramp_both_directions() -> None:
    # heben 0,2 K / senken 0,1 K je 10 min
    assert ramp(30.0, 31.0, 600, 0.2, 0.1) == pytest.approx(30.2)
    assert ramp(30.0, 29.0, 600, 0.2, 0.1) == pytest.approx(29.9)
    assert ramp(30.0, 29.0, 60, 0.2, 0.1) == pytest.approx(29.99)
    # nicht übers Ziel hinaus
    assert ramp(30.0, 30.05, 600, 0.2, 0.1) == 30.05
    assert ramp(30.0, 29.97, 600, 0.2, 0.1) == 29.97


def test_round_setpoint() -> None:
    assert round_setpoint(0.1 + 0.2 + 33) == 33.3
    assert round_setpoint(33.24) == 33.2


# ---- Fixtures ----------------------------------------------------------------------


@pytest.fixture
def plant(fake_modbus, fake_web):
    """Anlage im Heizbetrieb, Heizmodus "Kurve", gemittelte Außentemperatur 6,5 °C."""
    fake_modbus.registers.update({
        (HYDROBOX, 276): 65,   # gemittelte Außentemperatur 6,5 °C
        (HYDROBOX, 152): 327,  # HK1-Soll 32,7 °C
        (HYDROBOX, 2): 326,    # Puffer-Soll 32,6 °C
        (HYDROBOX, 156): 1,    # Parallelverschiebung 1 K
        (WANDA, 200): 4,       # Status: heizen
    })
    fake_web.values.update({
        (HB, DP_HK1_HEATING_WATER_MODE): 0,
        (HB, DP_HK1_FIXED_SETPOINT_HEATING): 33.2,
        (HB, DP_HK1_HEATING_CURVE): {
            "CurveValues": [
                {"XValue": x, "YValue": y}
                for x, y in zip(range(-20, 25, 5), BOESCH_CURVE, strict=True)
            ],
            "Info": 0,
        },
    })
    return fake_modbus, fake_web


async def _setup(hass: HomeAssistant, entry, **options) -> FineCurveCoordinator:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={CONF_WEB_PASSWORD: "pw", CONF_FINE_CURVE: True, **options}
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fine = entry.runtime_data.fine
    assert fine is not None
    return fine


def _writes(fake_web) -> list[tuple[str, object]]:
    """(Datenpunkt, Wert) aller Web-Schreibvorgänge."""
    return [(cid, value) for client in fake_web.instances for _, cid, _, value in client.writes]


def _festwert_writes(fake_web) -> list[float]:
    return [v for cid, v in _writes(fake_web) if cid == DP_HK1_FIXED_SETPOINT_HEATING]


async def _activate(hass, fake_web) -> None:
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.boesch_hb_hk1_feinkurve_aktiv"},
        blocking=True,
    )
    fake_web.instances[-1].writes.clear()


async def _set(hass, entity: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity, "value": value}, blocking=True
    )


async def _run(hass, fine: FineCurveCoordinator, now) -> None:
    """Ein Durchlauf zu einem festen Zeitpunkt, danach Entities aktualisieren."""
    await fine._async_run(now)
    fine.async_update_listeners()
    await hass.async_block_till_done()


async def _refresh_all(entry) -> None:
    for coordinator in entry.runtime_data.coordinators.values():
        await coordinator.async_refresh()
    await entry.runtime_data.web.async_refresh()


# ---- Option an/aus, Vorbelegung ----------------------------------------------------


async def test_option_off_no_entities(hass, plant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={CONF_WEB_PASSWORD: "pw"})
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.fine is None
    assert hass.states.get("switch.boesch_hb_hk1_feinkurve_aktiv") is None
    assert hass.states.get("number.boesch_hb_hk1_feinkurve_m20") is None
    assert hass.states.get("sensor.boesch_hb_hk1_fein_festwert") is None


async def test_option_needs_web(hass, plant, config_entry) -> None:
    """Ohne Web-Passwort bleibt die Option wirkungslos."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={CONF_FINE_CURVE: True})
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.fine is None


async def test_prefill_from_boesch_curve(hass, plant, config_entry) -> None:
    """Erstes Einschalten: Bösch-Kurve + Parallelverschiebung, nichts springt."""
    fine = await _setup(hass, config_entry)
    assert fine.points == POINTS
    assert hass.states.get("number.boesch_hb_hk1_feinkurve_m20").state == "37.0"
    assert hass.states.get("number.boesch_hb_hk1_fein_parallel").state == "0.0"
    # Inaktiv: Sensor zeigt, was geschrieben würde = HK1-Soll des Geräts.
    state = hass.states.get("sensor.boesch_hb_hk1_fein_festwert")
    assert state.state == "32.7"
    assert state.attributes["grund_halten"] == "inactive"
    assert state.attributes["hk1_soll"] == 32.7
    assert state.attributes["heizspeicher_soll"] == 32.6
    assert _writes(plant[1]) == []


async def test_points_persist(hass, plant, config_entry, hass_storage) -> None:
    await _setup(hass, config_entry)
    await _set(hass, "number.boesch_hb_hk1_feinkurve_p5", 32.4)
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", -0.3)
    data = hass_storage[f"boesch.fine_curve.{config_entry.entry_id}"]["data"]
    assert data["points"][5] == 32.4
    assert data["parallel"] == -0.3


async def test_option_off_drops_store(hass, plant, config_entry, hass_storage) -> None:
    await _setup(hass, config_entry)
    ir.async_create_issue(
        hass, DOMAIN, ISSUE_STOPPED, is_fixable=False,
        severity=ir.IssueSeverity.WARNING, translation_key="fine_curve_mode_changed",
    )
    key = f"boesch.fine_curve.{config_entry.entry_id}"
    assert key in hass_storage
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_WEB_PASSWORD: "pw", CONF_FINE_CURVE: False}
    )
    await hass.async_block_till_done()
    assert key not in hass_storage
    assert hass.states.get("switch.boesch_hb_hk1_feinkurve_aktiv") is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_STOPPED) is None


# ---- Ein-/Ausschalten -------------------------------------------------------------


async def test_activate_without_jump(hass, plant, config_entry) -> None:
    """Erst Festwert = aktueller HK1-Soll, dann Heizmodus "fixed"."""
    fine = await _setup(hass, config_entry)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.boesch_hb_hk1_feinkurve_aktiv"},
        blocking=True,
    )
    assert _writes(plant[1]) == [
        (DP_HK1_FIXED_SETPOINT_HEATING, 32.7),
        (DP_HK1_HEATING_WATER_MODE, 1),
    ]
    assert hass.states.get("switch.boesch_hb_hk1_feinkurve_aktiv").state == "on"
    assert fine.last_written == 32.7


async def test_activate_not_ready(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    plant[0].fail = True
    await _refresh_all(config_entry)
    with pytest.raises(HomeAssistantError, match="not ready"):
        await fine.async_activate()
    assert not fine.active


async def test_deactivate_back_to_curve(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.boesch_hb_hk1_feinkurve_aktiv"},
        blocking=True,
    )
    assert _writes(plant[1]) == [(DP_HK1_HEATING_WATER_MODE, 0)]
    assert not fine.active


# ---- Rampe und Schreibfilter -----------------------------------------------------------


async def test_ramp_up_and_write_filter(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    t0 = fine.last_write
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", 1.0)  # Ziel 33,7

    # Nach 1 min: Rampe erst +0,02 K -> nichts zu schreiben.
    await _run(hass, fine, t0 + timedelta(minutes=1))
    assert _festwert_writes(plant[1]) == []
    # Nach 5 min: +0,1 K, aber der letzte Schreibvorgang ist < 10 min her.
    await _run(hass, fine, t0 + timedelta(minutes=5))
    assert fine.output == 32.8
    assert _festwert_writes(plant[1]) == []
    # Nach 10 min: +0,2 K, Filter frei.
    await _run(hass, fine, t0 + timedelta(minutes=10))
    assert _festwert_writes(plant[1]) == [32.9]
    # Weitere 10 min: +0,2 K
    await _run(hass, fine, t0 + timedelta(minutes=20))
    assert _festwert_writes(plant[1]) == [32.9, 33.1]


async def test_ramp_down(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    t0 = fine.last_write
    await _set(hass, "number.boesch_hb_hk1_zuschlag", -2.0)  # Ziel 30,7
    for minute in range(1, 31):
        await _run(hass, fine, t0 + timedelta(minutes=minute))
    # 0,1 K je 10 min
    assert _festwert_writes(plant[1]) == [32.6, 32.5, 32.4]
    attrs = hass.states.get("sensor.boesch_hb_hk1_fein_festwert").attributes
    assert attrs["ziel_vor_rampe"] == 30.7
    assert attrs["zuschlag"] == -2.0


async def test_target_clamped(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry, **{CONF_FINE_MAX: 33.0})
    await _activate(hass, plant[1])
    await _set(hass, "number.boesch_hb_hk1_zuschlag", 5.0)
    await _run(hass, fine, fine.last_write + timedelta(minutes=1))
    assert fine.target == 33.0


# ---- Sofort-Anhebung -------------------------------------------------------------------


async def test_boost_bypasses_ramp_and_filter(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    await _set(hass, "number.boesch_hb_hk1_sofort_anhebung", 3.0)
    assert _festwert_writes(plant[1]) == [35.7]
    # Abbauen geht genauso sofort.
    await _set(hass, "number.boesch_hb_hk1_sofort_anhebung", 1.5)
    assert _festwert_writes(plant[1]) == [35.7, 34.2]
    # Eigenes Maximum (45 °C)
    await _set(hass, "number.boesch_hb_hk1_sofort_anhebung", 12.0)
    assert _festwert_writes(plant[1])[-1] == 44.7
    assert fine.ramp_value == pytest.approx(32.7)


async def test_boost_max(hass, plant, config_entry) -> None:
    await _setup(hass, config_entry, **{CONF_FINE_BOOST_MAX: 40.0})
    await _activate(hass, plant[1])
    await _set(hass, "number.boesch_hb_hk1_sofort_anhebung", 12.0)
    assert _festwert_writes(plant[1]) == [40.0]


# ---- Halten ----------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "reason"), [(2, "hot_water"), (5, "defrost")])
async def test_hold_during_hot_water_and_defrost(
    hass, plant, config_entry, status, reason
) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    t0 = fine.last_write
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", 1.0)
    plant[0].registers[(WANDA, 200)] = status
    await _refresh_all(config_entry)

    await _run(hass, fine, t0 + timedelta(minutes=30))
    assert fine.hold_reason == reason
    assert _festwert_writes(plant[1]) == []
    # Rampe pausiert, sonst käme danach ein großer Schritt auf einmal.
    assert fine.ramp_value == pytest.approx(32.7)

    # Sofort-Anhebung geht trotzdem raus.
    await _set(hass, "number.boesch_hb_hk1_sofort_anhebung", 2.0)
    assert _festwert_writes(plant[1]) == [34.7]


async def test_hold_without_outdoor_temperature(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    plant[0].fail = True
    await _refresh_all(config_entry)
    await _run(hass, fine, fine.last_write + timedelta(minutes=30))
    assert fine.hold_reason == "outdoor_unavailable"
    assert _festwert_writes(plant[1]) == []


async def test_hold_without_web(hass, plant, config_entry) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    plant[1].error = True
    await config_entry.runtime_data.web.async_refresh()
    await _run(hass, fine, fine.last_write + timedelta(minutes=30))
    assert fine.hold_reason == "web_unavailable"
    assert fine.active


async def test_mode_changed_on_device(hass, plant, config_entry, caplog) -> None:
    """Am Gerät umgestellt: nicht zurückschalten, Switch spiegelt "aus"."""
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    plant[1].values[(HB, DP_HK1_HEATING_WATER_MODE)] = 0
    await config_entry.runtime_data.web.async_refresh()
    await _run(hass, fine, fine.last_write + timedelta(minutes=1))
    assert fine.hold_reason == "mode_changed"
    assert hass.states.get("switch.boesch_hb_hk1_feinkurve_aktiv").state == "off"
    assert _writes(plant[1]) == []
    assert "Heizmodus am Gerät wurde umgestellt" in caplog.text
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_STOPPED)
    assert issue is not None
    assert issue.translation_key == "fine_curve_mode_changed"


async def test_foreign_write_deactivates(hass, plant, config_entry, caplog) -> None:
    """Festwert von außen geändert (z. B. zweite HA-Instanz): zurückziehen."""
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    plant[1].values[(HB, DP_HK1_FIXED_SETPOINT_HEATING)] = 33.4
    await config_entry.runtime_data.web.async_refresh()
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", 1.0)
    await _run(hass, fine, fine.last_write + timedelta(minutes=20))
    assert fine.hold_reason == "foreign_write"
    assert hass.states.get("switch.boesch_hb_hk1_feinkurve_aktiv").state == "off"
    # Nichts geschrieben, Heizmodus bleibt beim anderen auf "Festwert".
    assert _writes(plant[1]) == []
    assert "wurde von außen geändert" in caplog.text
    assert "33.4" in caplog.text
    # Sichtbar in Reparaturen, bis wieder eingeschaltet wird.
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_STOPPED)
    assert issue is not None
    assert issue.translation_key == "fine_curve_foreign_write"
    assert issue.translation_placeholders == {"value": "33.4", "last_written": "32.7"}
    await fine.async_activate()
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_STOPPED) is None


async def test_own_value_not_foreign(hass, plant, config_entry) -> None:
    """Der eigene Festwert (auch als Float-Rauschen) gilt nicht als fremd."""
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    plant[1].values[(HB, DP_HK1_FIXED_SETPOINT_HEATING)] = 32.700000762939453
    await config_entry.runtime_data.web.async_refresh()
    await _run(hass, fine, fine.last_write + timedelta(minutes=1))
    assert fine.active
    assert fine.hold_reason is None


async def test_no_foreign_check_after_write_error(hass, plant, config_entry) -> None:
    """Schreibfehler, Wert kam aber doch an: kein Fehlalarm, normal weiter."""
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    t0 = fine.last_write
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", 1.0)
    plant[1].error = True
    await _run(hass, fine, t0 + timedelta(minutes=10))
    assert fine.hold_reason == "write_failed"
    plant[1].error = False
    plant[1].values[(HB, DP_HK1_FIXED_SETPOINT_HEATING)] = 32.8
    await config_entry.runtime_data.web.async_refresh()
    await _run(hass, fine, t0 + timedelta(minutes=11))
    assert fine.active
    assert fine.hold_reason is None


async def test_write_error_retried(hass, plant, config_entry, caplog) -> None:
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    t0 = fine.last_write
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", 1.0)
    plant[1].error = True
    await _run(hass, fine, t0 + timedelta(minutes=10))
    assert fine.hold_reason == "write_failed"
    assert caplog.text.count("Festwert nicht geschrieben") == 1
    plant[1].error = False
    await _run(hass, fine, t0 + timedelta(minutes=11))
    assert fine.hold_reason is None
    assert _festwert_writes(plant[1]) == [32.9]


async def test_verify_logs_deviation(hass, plant, config_entry, caplog) -> None:
    """Nach dem Einschalten: Hinweis, falls H 156 im Festwert-Modus mitwirkt."""
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    plant[0].registers[(HYDROBOX, 152)] = 337  # Festwert 32,7 + H 156
    await _refresh_all(config_entry)
    await _run(hass, fine, fine.last_write + timedelta(minutes=4))
    assert "weicht vom Festwert 32.7 ab" in caplog.text
    attrs = hass.states.get("sensor.boesch_hb_hk1_fein_festwert").attributes
    assert attrs["abweichung_hk1_soll"] == 1.0


# ---- Entladen, Neu laden, Beenden, Neustart --------------------------------------------


async def test_unload_back_to_curve(hass, plant, config_entry) -> None:
    await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    await hass.config_entries.async_unload(config_entry.entry_id)
    assert (DP_HK1_HEATING_WATER_MODE, 0) in _writes(plant[1])


async def test_option_off_back_to_curve(hass, plant, config_entry) -> None:
    await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_WEB_PASSWORD: "pw", CONF_FINE_CURVE: False}
    )
    await hass.async_block_till_done()
    assert (DP_HK1_HEATING_WATER_MODE, 0) in _writes(plant[1])


async def test_options_change_keeps_fixed(hass, plant, config_entry) -> None:
    """Andere Option geändert -> Neu laden ohne Umweg über "Kurve"."""
    await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    client = plant[1].instances[-1]
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, CONF_WEB_POWER: True},
    )
    await hass.async_block_till_done()
    assert (HB, DP_HK1_HEATING_WATER_MODE, TYPE_INT32, 0) not in client.writes
    assert config_entry.runtime_data.fine.active


async def test_stop_writes_without_offsets(hass, plant, config_entry) -> None:
    """HA stoppt: Basis + feine Parallelverschiebung, ohne Zuschlag/Anhebung."""
    await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    await _set(hass, "number.boesch_hb_hk1_fein_parallel", 0.4)
    await _set(hass, "number.boesch_hb_hk1_zuschlag", 2.0)
    await _set(hass, "number.boesch_hb_hk1_sofort_anhebung", 3.0)
    client = plant[1].instances[-1]
    client.writes.clear()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert client.writes == [(HB, DP_HK1_FIXED_SETPOINT_HEATING, TYPE_SINGLE, 33.1)]


async def test_restart_resumes_without_offsets(hass, plant, config_entry) -> None:
    """Nach Neustart: aktiv bleibt, Zuschlag/Anhebung 0, Rampe ab Gerätewert."""
    fine = await _setup(hass, config_entry)
    await _activate(hass, plant[1])
    await _set(hass, "number.boesch_hb_hk1_zuschlag", 2.0)
    plant[1].values[(HB, DP_HK1_FIXED_SETPOINT_HEATING)] = 33.0
    # Neu laden ohne Rückschalten simuliert den Neustart (Store bleibt).
    config_entry.runtime_data.reloading = True
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    fine = config_entry.runtime_data.fine
    assert fine.active
    assert fine.zuschlag == 0.0
    assert fine.boost == 0.0
    assert fine.ramp_value == 33.0
    assert hass.states.get("switch.boesch_hb_hk1_feinkurve_aktiv").state == "on"


# ---- Options-Flow ------------------------------------------------------------------


async def _options_step(hass, entry, step: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return result, await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_options_menu_only_with_fine_curve(hass, plant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={CONF_WEB_PASSWORD: "pw"})
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert "fine_curve" not in result["menu_options"]
    hass.config_entries.options.async_abort(result["flow_id"])


async def test_options_fine_curve(hass, plant, config_entry) -> None:
    await _setup(hass, config_entry)
    _, result = await _options_step(hass, config_entry, "fine_curve")
    assert result["step_id"] == "fine_curve"
    values = {
        CONF_FINE_MIN: 22.0,
        CONF_FINE_MAX: 21.0,
        CONF_FINE_BOOST_MAX: 45.0,
        CONF_FINE_RAMP_DOWN: 0.1,
        CONF_FINE_RAMP_UP: 0.3,
        CONF_FINE_WRITE_INTERVAL: 15,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    assert result["errors"] == {"base": "fine_min_max"}
    values[CONF_FINE_MAX] = 46.0
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    assert result["errors"] == {"base": "fine_boost_max"}
    values[CONF_FINE_MAX] = 38.0
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    params = config_entry.runtime_data.fine.params
    assert (params.max_value, params.ramp_up) == (38.0, 0.3)
    assert params.write_interval == timedelta(minutes=15)
