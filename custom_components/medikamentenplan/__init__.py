"""Medikamentenplan: reine Uebersicht (Reichweite/Nachbestellung), Daten nur lokal im HA Store."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN, PLATFORMS
from .plan import Plan
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
JS_URL = f"/{DOMAIN}/medikamentenplan-scanner.js"


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Domainweite Services und die Scanner-Karte (lokal ausgeliefert, inkl. ZXing, kein CDN)."""
    await async_setup_services(hass)
    www = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths([StaticPathConfig(f"/{DOMAIN}", str(www), cache_headers=False)])
    add_extra_js_url(hass, f"{JS_URL}?v=1.6.7")
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    plan = Plan(hass, entry)
    await plan.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = plan
    parent = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Medikamentenplan {entry.title}",
        manufacturer="Medikamentenplan",
    )
    plan.parent_device_id = parent.id
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # taeglich neu berechnen (Mitternacht); beim Start rechnen die Entities ohnehin frisch
    entry.async_on_unload(async_track_time_change(hass, lambda _now: plan.notify(), hour=0, minute=0, second=5))
    return True


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    """Plan geloescht -> Gesundheitsdaten im Store ebenfalls entfernen."""
    await Plan(hass, entry).store.async_remove()
