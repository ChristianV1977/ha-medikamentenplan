#!/usr/bin/env python3
"""Erzeugt die Dashboard-Config 'Medikamente' aus der Entity-Registry (Plaene + Medikamente).
Nach dem Anlegen neuer Medikamente erneut ausfuehren und per ha_config_set_dashboard (url_path medikamente) einspielen.
Ohne auto-entities-Karte sind die Medikamentenkarten statisch; die Uebersicht (Markdown) ist immer dynamisch."""
import json, sys
S = sys.argv[1] if len(sys.argv) > 1 else "/mnt/homeassistant/.storage"
reg = json.load(open(f"{S}/core.entity_registry"))["data"]["entities"]
ent = json.load(open(f"{S}/core.config_entries"))["data"]["entries"]
titles = {e["entry_id"]: e["title"] for e in ent if e["domain"] == "medikamentenplan"}
plans = {}
for r in reg:
    if r["platform"] != "medikamentenplan" or r["config_entry_id"] not in titles:
        continue
    key = r["unique_id"].split("_", 1)[1]  # <med_id>_<typ>
    med, typ = key.split("_", 1)
    plans.setdefault(r["config_entry_id"], {}).setdefault(med, {})[typ] = r["entity_id"]

OVERVIEW = """{% set ns = namespace(rows=[]) %}
{%- for e in integration_entities('medikamentenplan') if e.endswith('_reichweite_tage_verbleibend') %}
{%- set a = states[e].attributes %}
{%- set ic = {'ok':'🟢','nachbestellen':'🟠','aufgebraucht':'🔴'}.get(a.status,'⚪') %}
{%- set nb = (a.nachbestelldatum | as_datetime | as_local).strftime('%d.%m.%Y') if a.nachbestelldatum else '–' %}
{%- set tage = states(e) if is_number(states(e)) else '–' %}
{%- set ns.rows = ns.rows + ['| ' ~ ic ~ ' | ' ~ a.plan ~ ' | ' ~ a.name ~ ' | ' ~ (a.zweck or '') ~ ' | ' ~ tage ~ ' | ' ~ nb ~ ' |'] %}
{%- endfor %}
| | Plan | Medikament | Wofür | Tage | Nachbestellen ab |
|---|---|---|---|---|---|
{{ ns.rows | join('\\n') if ns.rows else '| | | Noch keine Medikamente angelegt | | | |' }}"""

def med_cards(m):
    r, n, s, b = m["reichweite"], m["nachbestelldatum"], m["status"], m["neue_packung"]
    col = "{{ {'ok':'green','nachbestellen':'orange','aufgebraucht':'red'}.get(states('%s'),'grey') }}" % s
    sec = ("{% set a = states.@R@.attributes %}{{ a.zweck or '' }}{{ ' · ' if a.zweck }}"
           "{{ a.dosis | round(2) | string | replace('.0','') }} {{ a.einheit }} "
           "{{ {'taeglich': '× ' ~ (a.pro_tag | round(2) | string | replace('.0','')) ~ ' täglich', 'intervall': 'alle ' ~ a.intervall_tage ~ ' Tage', 'bedarf': 'bei Bedarf'}[a.modus] }}\n"
           "{{ states('@R@') }} Tage verbleibend · Nachbestellen ab "
           "{{ as_timestamp(states('@N@')) | timestamp_custom('%d.%m.%Y') if states('@N@') not in ['unknown','unavailable'] else '–' }}"
           ).replace('@R@', r).replace('@N@', n)
    return {"type": "vertical-stack", "cards": [
        {"type": "custom:mushroom-template-card", "entity": s,
         "primary": "{{ state_attr('%s','name') }}" % r, "secondary": sec, "multiline_secondary": True,
         "icon": "mdi:pill", "icon_color": col, "badge_icon": "{{ {'nachbestellen':'mdi:cart','aufgebraucht':'mdi:alert'}.get(states('%s'),'') }}" % s,
         "badge_color": col, "tap_action": {"action": "more-info"}},
        {"type": "custom:mushroom-template-card", "entity": b, "primary": "Neue Packung angefangen",
         "icon": "mdi:package-variant-closed-plus", "icon_color": "blue", "layout": "horizontal",
         "tap_action": {"action": "perform-action", "perform_action": "button.press", "target": {"entity_id": b},
                        "confirmation": {"text": "Neue Packung angefangen? Anbruch = heute, Bestand = Packungsgröße."}}}]}

views = [{"title": "Übersicht", "path": "uebersicht", "icon": "mdi:format-list-bulleted", "type": "sections", "max_columns": 2,
          "sections": [{"type": "grid", "cards": [{"type": "heading", "heading": "Alle Medikamente", "icon": "mdi:pill"},
                                                  {"type": "markdown", "content": OVERVIEW}]}]}]
for eid, meds in sorted(plans.items(), key=lambda x: titles[x[0]]):
    meds = {k: v for k, v in meds.items() if {"reichweite", "nachbestelldatum", "status", "neue_packung"} <= set(v)}
    cards = [{"type": "heading", "heading": f"Plan {titles[eid]}", "icon": "mdi:account"}]
    cards += [med_cards(m) for m in meds.values()]
    views.append({"title": titles[eid], "path": "plan-" + titles[eid].lower().replace(" ", "-"), "icon": "mdi:account", "type": "sections",
                  "max_columns": 2, "sections": [{"type": "grid", "cards": cards}]})
print(json.dumps({"views": views}, ensure_ascii=False))
