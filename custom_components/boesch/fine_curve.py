"""Feine Heizkurve HK1: die Integration rechnet, das Gerät regelt auf Festwert.

Die Bösch-Heizkurve (9 Stützpunkte) und die Parallelverschiebung (H 156)
kennen nur ganze Grad. Der Festwert HK1 Heizen (Webinterface) nimmt
Zehntelgrad an. Bei aktiver Option rechnet die Integration deshalb eine eigene
Kurve und schreibt das Ergebnis als Festwert, der Heizmodus steht auf "fixed".

Rechenweg (einmal pro Minute):
  1. Basis = lineare Interpolation der 9 Stützpunkte über die gemittelte
     Außentemperatur (H 276, dieselbe Größe, mit der das Gerät seine Kurve
     rechnet). Außerhalb -20/+20 °C gilt der Randwert.
  2. Ziel = Basis + feine Parallelverschiebung + Zuschlag, geklemmt auf
     [Minimum, Maximum].
  3. Rampe: das Ziel wird langsam angefahren (Standard: senken 0,1 K, heben
     0,2 K je 10 min), weil der Puffer-Soll dem HK1-Soll folgt.
  4. Ausgabe = Rampe + Sofort-Anhebung (eigenes Maximum), auf 0,1 gerundet.
  5. Schreibfilter: nur bei >= 0,1 K Unterschied und frühestens 10 min nach
     dem letzten Schreiben; eine geänderte Sofort-Anhebung geht sofort raus.
  6. Halten (nichts schreiben, Rampe pausiert) bei Warmwasser/Abtauen, ohne
     Außentemperatur oder Webinterface, und wenn am Gerät jemand den
     Heizmodus umgestellt hat (dann schaltet sich die Steuerung ab).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FINE_BOOST_MAX,
    CONF_FINE_CURVE,
    CONF_FINE_MAX,
    CONF_FINE_MIN,
    CONF_FINE_RAMP_DOWN,
    CONF_FINE_RAMP_UP,
    CONF_FINE_WRITE_INTERVAL,
    CONF_WEB_PASSWORD,
    DEFAULT_FINE_BOOST_MAX,
    DEFAULT_FINE_CURVE,
    DEFAULT_FINE_MAX,
    DEFAULT_FINE_MIN,
    DEFAULT_FINE_RAMP_DOWN,
    DEFAULT_FINE_RAMP_UP,
    DEFAULT_FINE_WRITE_INTERVAL,
    DOMAIN,
)
from .web_client import (
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_HEATING_CURVE,
    DP_HK1_HEATING_WATER_MODE,
    TYPE_INT32,
    TYPE_SINGLE,
)

if TYPE_CHECKING:
    from .coordinator import BoeschCoordinator, BoeschWebCoordinator

_LOGGER = logging.getLogger(__name__)

# Außentemperaturen der Kurven-Stützpunkte (fest in der Kermi-Firmware).
CURVE_X = (-20, -15, -10, -5, 0, 5, 10, 15, 20)
# Auflösung, die der Festwert am Gerät annimmt.
FIXED_SETPOINT_STEP = 0.1

TICK = timedelta(seconds=60)
# Rampen sind in K je 10 min angegeben.
RAMP_PERIOD_S = 600.0
# Erst so lange nach dem Einschalten prüfen, ob der HK1-Soll dem Festwert folgt
# (der HK1-Soll wird im 30-s-Takt gelesen und braucht einen Moment).
VERIFY_DELAY = timedelta(minutes=3)

# Heizmodus HK1 (Web-Datenpunkt), siehe select.HEIZMODUS.
MODE_CURVE = 0
MODE_FIXED = 1
# WANDA-Status (W 200), bei denen gehalten wird.
HOLD_STATUS = {2: "hot_water", 5: "defrost"}

# Modbus-Keys, die die Steuerung liest.
KEY_OUTDOOR = "boesch_hb_aussentemperatur_gemittelt"
KEY_STATUS = "boesch_wanda_status"
KEY_HK1_SETPOINT = "boesch_hb_hk1_soll"
KEY_BUFFER_SETPOINT = "boesch_hb_heizspeicher_soll"
KEY_PARALLEL = "boesch_hb_hk1_parallel"

_STORE_VERSION = 1


# Reparaturhinweis, wenn sich die Kurve selbst abschaltet; nur einer zugleich.
ISSUE_STOPPED = "fine_curve_stopped"


def round_setpoint(value: float) -> float:
    """Auf die Auflösung des Festwerts (0,1 K) runden."""
    return round(float(value), 1)


def fine_curve_enabled(options: dict[str, Any] | Any) -> bool:
    """Option an und Webinterface eingerichtet."""
    return bool(options.get(CONF_WEB_PASSWORD)) and bool(
        options.get(CONF_FINE_CURVE, DEFAULT_FINE_CURVE)
    )


def interpolate(points: Sequence[float], outdoor: float) -> float:
    """Vorlauf-Soll der Kurve bei `outdoor`; außerhalb der Stützpunkte Randwert."""
    if outdoor <= CURVE_X[0]:
        return points[0]
    if outdoor >= CURVE_X[-1]:
        return points[-1]
    for i in range(len(CURVE_X) - 1):
        x0, x1 = CURVE_X[i], CURVE_X[i + 1]
        if outdoor <= x1:
            y0, y1 = points[i], points[i + 1]
            return y0 + (y1 - y0) * (outdoor - x0) / (x1 - x0)
    return points[-1]  # pragma: no cover


def ramp(current: float, target: float, seconds: float, up: float, down: float) -> float:
    """`current` höchstens um up/down (K je 10 min) Richtung `target` bewegen."""
    if target > current:
        return min(target, current + up * seconds / RAMP_PERIOD_S)
    return max(target, current - down * seconds / RAMP_PERIOD_S)


@dataclass(frozen=True)
class FineCurveParams:
    """Einstellungen aus den Optionen."""

    min_value: float = DEFAULT_FINE_MIN
    max_value: float = DEFAULT_FINE_MAX
    boost_max: float = DEFAULT_FINE_BOOST_MAX
    ramp_up: float = DEFAULT_FINE_RAMP_UP
    ramp_down: float = DEFAULT_FINE_RAMP_DOWN
    write_interval: timedelta = timedelta(minutes=DEFAULT_FINE_WRITE_INTERVAL)

    @classmethod
    def from_options(cls, options: Any) -> FineCurveParams:
        return cls(
            min_value=float(options.get(CONF_FINE_MIN, DEFAULT_FINE_MIN)),
            max_value=float(options.get(CONF_FINE_MAX, DEFAULT_FINE_MAX)),
            boost_max=float(options.get(CONF_FINE_BOOST_MAX, DEFAULT_FINE_BOOST_MAX)),
            ramp_up=float(options.get(CONF_FINE_RAMP_UP, DEFAULT_FINE_RAMP_UP)),
            ramp_down=float(options.get(CONF_FINE_RAMP_DOWN, DEFAULT_FINE_RAMP_DOWN)),
            write_interval=timedelta(
                minutes=float(
                    options.get(CONF_FINE_WRITE_INTERVAL, DEFAULT_FINE_WRITE_INTERVAL)
                )
            ),
        )


def store_for(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Speicher für Stützpunkte, feine Parallelverschiebung und "aktiv"."""
    return Store(hass, _STORE_VERSION, f"{DOMAIN}.fine_curve.{entry_id}")


class FineCurveCoordinator(DataUpdateCoordinator[None]):
    """Rechnet die feine Kurve und schreibt den Festwert HK1.

    Der Zustand liegt in Attributen; Entities lesen ihn direkt. Ein Durchlauf
    wirft nie: Gründe fürs Halten stehen in `hold_reason`, damit die
    Einstell-Entities auch ohne Gerät bedienbar bleiben.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        web: BoeschWebCoordinator,
        coordinators: dict[str, BoeschCoordinator],
        params: FineCurveParams,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_fine_curve",
            update_interval=TICK,
            config_entry=entry,
        )
        self._web = web
        self._coordinators = coordinators
        self.params = params
        self._store = store_for(hass, entry.entry_id)
        self._lock = asyncio.Lock()

        # Persistent (Store)
        self.points: list[float] | None = None
        self.parallel = 0.0
        self.active = False
        # Flüchtig: nach einem Neustart 0, Automationen setzen sie neu.
        self.zuschlag = 0.0
        self.boost = 0.0

        self.base: float | None = None
        self.target: float | None = None
        self.ramp_value: float | None = None
        self.output: float | None = None
        self.last_written: float | None = None
        self.last_write: datetime | None = None
        self.hold_reason: str | None = None
        self._last_tick: datetime | None = None
        self._boost_pending = False
        self._write_error_logged = False
        self._verify_at: datetime | None = None

    # ---- Lebenszyklus --------------------------------------------------------

    async def async_setup(self) -> None:
        """Gespeicherten Zustand laden, STOP-Listener anmelden."""
        if data := await self._store.async_load():
            points = data.get("points")
            if isinstance(points, list) and len(points) == len(CURVE_X):
                self.points = [float(p) for p in points]
            self.parallel = float(data.get("parallel", 0.0))
            self.active = bool(data.get("active", False))
        self._try_initialize_points()
        assert self.config_entry is not None
        self.config_entry.async_on_unload(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_on_stop)
        )

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"points": self.points, "parallel": self.parallel, "active": self.active}
        )

    def _try_initialize_points(self) -> bool:
        """Beim ersten Einschalten: Bösch-Kurve + Parallelverschiebung übernehmen.

        Damit liefert die feine Kurve anfangs genau den Soll, den das Gerät
        selbst rechnet, und beim Umstieg springt nichts.
        """
        if self.points is not None:
            return True
        curve = (self._web.data or {}).get(DP_HK1_HEATING_CURVE) or {}
        by_x = {p.get("XValue"): p.get("YValue") for p in curve.get("CurveValues") or []}
        parallel = self._modbus(KEY_PARALLEL)
        if parallel is None or any(by_x.get(x) is None for x in CURVE_X):
            return False
        self.points = [round_setpoint(float(by_x[x]) + parallel) for x in CURVE_X]
        _LOGGER.info(
            "Feine Heizkurve aus Bösch-Kurve + Parallelverschiebung (%s K) "
            "vorbelegt: %s", parallel, self.points,
        )
        self.hass.async_create_task(self._async_save())
        return True

    async def _async_on_stop(self, event: Event) -> None:
        """HA stoppt: Festwert ohne Zuschlag und Sofort-Anhebung schreiben.

        So bleibt keine Anhebung stehen, falls HA länger nicht läuft. Der
        Heizmodus bleibt auf "fixed".
        """
        if not self.active or self.points is None:
            return
        outdoor = self._modbus(KEY_OUTDOOR)
        if outdoor is None or not self._web_ok():
            return
        value = round_setpoint(self._clamp(interpolate(self.points, outdoor) + self.parallel))
        try:
            await self._web.async_write(
                DP_HK1_FIXED_SETPOINT_HEATING, TYPE_SINGLE, value, refresh=False
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Feine Heizkurve: Festwert beim Beenden nicht geschrieben: %s", err)
            return
        _LOGGER.info("Feine Heizkurve: Festwert beim Beenden auf %s °C gesetzt", value)

    async def async_release(self) -> None:
        """Integration wird entladen oder die Option abgeschaltet: zurück auf Kurve."""
        if not self.active:
            return
        try:
            await self.async_deactivate()
        except HomeAssistantError as err:
            _LOGGER.warning("Feine Heizkurve: Heizmodus nicht zurückgestellt: %s", err)

    # ---- Bedienung ------------------------------------------------------------

    async def async_activate(self) -> None:
        """Sprungfrei einschalten: Festwert = aktueller HK1-Soll, dann "fixed"."""
        async with self._lock:
            if not self._try_initialize_points():
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="fine_curve_not_ready"
                )
            setpoint = self._modbus(KEY_HK1_SETPOINT)
            if setpoint is None or not self._web_ok():
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="fine_curve_not_ready"
                )
            value = round_setpoint(setpoint)
            await self._web.async_write(DP_HK1_FIXED_SETPOINT_HEATING, TYPE_SINGLE, value)
            await self._web.async_write(DP_HK1_HEATING_WATER_MODE, TYPE_INT32, MODE_FIXED)
            # Frisch lesen, sonst sähe der nächste Durchlauf noch "curve".
            await self._web.async_refresh()
            now = dt_util.utcnow()
            self.active = True
            self.ramp_value = value
            self.output = value
            self.last_written = value
            self.last_write = now
            self._last_tick = now
            self._verify_at = now + VERIFY_DELAY
            self.hold_reason = None
            await self._async_save()
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_STOPPED)
            _LOGGER.info("Feine Heizkurve aktiv, Start bei %s °C", value)
        self.async_update_listeners()

    async def async_deactivate(self) -> None:
        """Ausschalten: Heizmodus zurück auf "curve"."""
        async with self._lock:
            await self._web.async_write(DP_HK1_HEATING_WATER_MODE, TYPE_INT32, MODE_CURVE)
            self._set_inactive()
            await self._async_save()
        self.async_update_listeners()

    async def _async_stop(self, reason: str, placeholders: dict[str, str]) -> None:
        """Selbst abschalten (ohne Moduswechsel) und in Reparaturen melden."""
        self._set_inactive()
        self.output = None
        await self._async_save()
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_STOPPED,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"fine_curve_{reason}",
            translation_placeholders=placeholders,
        )

    def _set_inactive(self) -> None:
        self.active = False
        self.ramp_value = None
        self._verify_at = None
        self._boost_pending = False

    async def async_set_point(self, index: int, value: float) -> None:
        if self.points is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="fine_curve_not_ready"
            )
        self.points[index] = round_setpoint(value)
        await self._async_save()
        self.async_update_listeners()

    async def async_set_parallel(self, value: float) -> None:
        self.parallel = round_setpoint(value)
        await self._async_save()
        self.async_update_listeners()

    def set_zuschlag(self, value: float) -> None:
        """Zuschlag (läuft durch die Rampe, wirkt ab dem nächsten Durchlauf)."""
        self.zuschlag = round_setpoint(value)
        self.async_update_listeners()

    async def async_set_boost(self, value: float) -> None:
        """Sofort-Anhebung: an Rampe und Schreibfilter vorbei sofort schreiben."""
        value = round_setpoint(value)
        if value == self.boost:
            return
        self.boost = value
        self._boost_pending = True
        await self._async_run(dt_util.utcnow())
        self.async_update_listeners()

    # ---- Durchlauf -------------------------------------------------------------

    async def _async_update_data(self) -> None:
        await self._async_run(dt_util.utcnow())

    async def _async_run(self, now: datetime) -> None:
        async with self._lock:
            self.hold_reason = await self._async_step(now)

    async def _async_step(self, now: datetime) -> str | None:
        """Ein Durchlauf; liefert den Grund fürs Halten oder None."""
        seconds = (
            max(0.0, (now - self._last_tick).total_seconds()) if self._last_tick else 0.0
        )
        self._last_tick = now

        if not self._try_initialize_points():
            return "not_initialized"
        assert self.points is not None
        outdoor = self._modbus(KEY_OUTDOOR)
        if outdoor is None:
            self.base = self.target = None
        else:
            self.base = interpolate(self.points, outdoor)
            self.target = self._clamp(self.base + self.parallel + self.zuschlag)
        if not self.active:
            # Zum Vergleich vor dem Einschalten: was geschrieben würde.
            self.output = None if self.target is None else round_setpoint(self.target)
            return "inactive"
        if not self._web_ok():
            return "web_unavailable"
        mode = (self._web.data or {}).get(DP_HK1_HEATING_WATER_MODE)
        if mode is None:
            return "web_unavailable"
        if int(mode) != MODE_FIXED:
            _LOGGER.warning(
                "Feine Heizkurve: Heizmodus am Gerät wurde umgestellt; "
                "Steuerung abgeschaltet (es wird nicht zurückgeschaltet)"
            )
            await self._async_stop("mode_changed", {})
            return "mode_changed"
        if (foreign := self._foreign_setpoint()) is not None:
            # Jemand anderes schreibt den Festwert (zweite HA-Instanz, Web-UI,
            # Festwert-Entity): zurückziehen, sonst steuern zwei gegeneinander.
            _LOGGER.warning(
                "Feine Heizkurve: Festwert am Gerät (%s °C) wurde von außen "
                "geändert (zuletzt selbst geschrieben: %s °C); Steuerung "
                "abgeschaltet. Läuft die feine Heizkurve in einer zweiten "
                "Home-Assistant-Instanz?",
                foreign, self.last_written,
            )
            await self._async_stop(
                "foreign_write",
                {"value": str(foreign), "last_written": str(self.last_written)},
            )
            return "foreign_write"
        if outdoor is None or self.target is None:
            return "outdoor_unavailable"

        if self.ramp_value is None:
            # Nach einem Neustart beim aktuellen Festwert am Gerät weitermachen.
            current = (self._web.data or {}).get(DP_HK1_FIXED_SETPOINT_HEATING)
            self.ramp_value = float(current) if current is not None else self.target
            if self.last_written is None and current is not None:
                self.last_written = round_setpoint(float(current))

        status = self._modbus(KEY_STATUS)
        hold = HOLD_STATUS.get(int(status)) if status is not None else None
        if hold is None:
            self.ramp_value = ramp(
                self.ramp_value, self.target, seconds,
                self.params.ramp_up, self.params.ramp_down,
            )
        self.output = self._with_boost(self.ramp_value)
        self._verify(now)

        if hold is not None and not self._boost_pending:
            return hold
        if self.last_written is not None and abs(self.output - self.last_written) < 0.05:
            self._boost_pending = False
            return None
        if (
            not self._boost_pending
            and self.last_write is not None
            and now - self.last_write < self.params.write_interval
        ):
            return None
        return await self._async_write(self.output, now)

    async def _async_write(self, value: float, now: datetime) -> str | None:
        try:
            await self._web.async_write(DP_HK1_FIXED_SETPOINT_HEATING, TYPE_SINGLE, value)
        except HomeAssistantError as err:
            # Nicht hektisch wiederholen: nächster Versuch beim nächsten Durchlauf.
            if not self._write_error_logged:
                _LOGGER.warning("Feine Heizkurve: Festwert nicht geschrieben: %s", err)
                self._write_error_logged = True
            else:
                _LOGGER.debug("Feine Heizkurve: Festwert nicht geschrieben: %s", err)
            return "write_failed"
        if self._write_error_logged:
            _LOGGER.info("Feine Heizkurve: Schreiben klappt wieder")
        self._write_error_logged = False
        self._boost_pending = False
        self.last_written = value
        self.last_write = now
        return None

    def _verify(self, now: datetime) -> None:
        """Einmal nach dem Einschalten loggen, ob HK1- und Puffer-Soll folgen.

        Offene Frage an Bösch: wirkt die Parallelverschiebung H 156 auch im
        Festwert-Modus? Dann läge der HK1-Soll um H 156 über dem Festwert.
        """
        if self._verify_at is None or now < self._verify_at:
            return
        self._verify_at = None
        hk1, buffer = self._modbus(KEY_HK1_SETPOINT), self._modbus(KEY_BUFFER_SETPOINT)
        if hk1 is None or self.last_written is None:
            return
        parallel = self._modbus(KEY_PARALLEL)
        if abs(hk1 - self.last_written) < 0.15:
            _LOGGER.info(
                "Feine Heizkurve: HK1-Soll %s folgt dem Festwert %s (Puffer-Soll %s)",
                hk1, self.last_written, buffer,
            )
        else:
            _LOGGER.warning(
                "Feine Heizkurve: HK1-Soll %s weicht vom Festwert %s ab (Puffer-Soll "
                "%s, Parallelverschiebung am Gerät %s K). Wirkt H 156 im "
                "Festwert-Modus, dann dort 0 einstellen.",
                hk1, self.last_written, buffer, parallel,
            )

    # ---- Hilfen ------------------------------------------------------------------

    def _foreign_setpoint(self) -> float | None:
        """Festwert am Gerät, falls er nicht der zuletzt selbst geschriebene ist.

        Nach einem eigenen Schreibfehler wird nicht verglichen: ob der Wert
        trotzdem angekommen ist, ist dann unklar.
        """
        if self.last_written is None or self._write_error_logged:
            return None
        current = (self._web.data or {}).get(DP_HK1_FIXED_SETPOINT_HEATING)
        if current is None or abs(float(current) - self.last_written) < 0.05:
            return None
        return round_setpoint(float(current))

    def _clamp(self, value: float) -> float:
        return min(max(value, self.params.min_value), self.params.max_value)

    def _with_boost(self, value: float) -> float:
        if self.boost <= 0:
            return round_setpoint(value)
        return round_setpoint(max(value, min(value + self.boost, self.params.boost_max)))

    def _web_ok(self) -> bool:
        return self._web.last_update_success and self._web.data is not None

    def _modbus(self, key: str) -> float | None:
        """Zuletzt gelesener Modbus-Wert (None, wenn die Gruppe ausgefallen ist)."""
        for coordinator in self._coordinators.values():
            if coordinator.data is not None and key in coordinator.data:
                if not coordinator.last_update_success:
                    return None
                value = coordinator.data[key]
                return None if value is None else float(value)
        return None

    @callback
    def attributes(self) -> dict[str, Any]:
        """Attribute des Sensors "Berechneter Festwert"."""
        hk1 = self._modbus(KEY_HK1_SETPOINT)
        return {
            "basiskurve": None if self.base is None else round(self.base, 2),
            "parallelverschiebung": self.parallel,
            "zuschlag": self.zuschlag,
            "sofort_anhebung": self.boost,
            "ziel_vor_rampe": None if self.target is None else round(self.target, 2),
            "rampe": None if self.ramp_value is None else round(self.ramp_value, 2),
            "zuletzt_geschrieben": self.last_written,
            "letzter_schreibvorgang": self.last_write,
            "grund_halten": self.hold_reason,
            "hk1_soll": hk1,
            "heizspeicher_soll": self._modbus(KEY_BUFFER_SETPOINT),
            "parallel_geraet": self._modbus(KEY_PARALLEL),
            "abweichung_hk1_soll": (
                None
                if hk1 is None or self.last_written is None or not self.active
                else round(hk1 - self.last_written, 1)
            ),
        }
