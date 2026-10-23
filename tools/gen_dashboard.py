#!/usr/bin/env python3
"""Erzeugt die Dashboard-Config (JSON) fuer Medikamentenplan.
Aufruf: gen_dashboard.py [PLAN]   -> ohne PLAN alle Plaene, mit PLAN nur dieser Plan.
Ausgabe: {"views": [...]} fuer ha_config_set_dashboard bzw. Lovelace-Raw-Editor.
Voraussetzung (HACS): auto-entities, mushroom, browser_mod."""
import json, sys

PLAN = sys.argv[1] if len(sys.argv) > 1 else None
PF = f" and state_attr(e, 'plan') == {PLAN!r}" if PLAN else ""

PLAN_MD = "{%- macro f(x) -%}{%- set r = x | float(0) -%}{%- if r == 0 -%}–{%- elif r == r | int -%}{{ r | int }}{%- else -%}{{ r | string | replace('.', ',') }}{%- endif -%}{%- endmacro -%}\n{%- set ns0 = namespace(l=[]) -%}{%- for e in integration_entities('medikamentenplan') | select('match', 'sensor\\..*_reichweite_tage_verbleibend$') if state_attr(e, 'status') != 'abgesetzt'@PF@ -%}{%- set ns0.l = ns0.l + [e] -%}{%- endfor -%}{%- set ents = ns0.l -%}\n{%- for p in ents | map('state_attr', 'plan') | unique | sort %}\n### {{ p }}\n| Medikament | Morgens | Mittags | Abends | Nachts |\n|:--|:-:|:-:|:-:|:-:|\n{%- set ns = namespace(rows=[], bed=[]) %}\n{%- for e in ents if state_attr(e, 'plan') == p %}\n{%- set a = states[e].attributes %}\n{%- set v = [a.get('morgens', 0), a.get('mittags', 0), a.get('abends', 0), a.get('nachts', 0)] | map('float', 0) | list %}\n{%- if a.modus == 'bedarf' %}\n{%- set ns.bed = ns.bed + [a.name ~ ' (ca. ' ~ (f(a.bedarf_pro_woche) | trim) ~ '× pro Woche)'] %}\n{%- else %}\n{%- set first = (v | map('bool') | list).index(true) if true in (v | map('bool') | list) else 9 %}\n{%- set lbl = a.name ~ (' (alle ' ~ a.intervall_tage ~ ' Tage)' if a.modus not in ['taeglich', 'bedarf'] and a.intervall_tage else '') %}\n{%- set ns.rows = ns.rows + [first ~ '@@' ~ lbl ~ '@@' ~ (f(v[0]) | trim) ~ '@@' ~ (f(v[1]) | trim) ~ '@@' ~ (f(v[2]) | trim) ~ '@@' ~ (f(v[3]) | trim)] %}\n{%- endif %}\n{%- endfor %}\n{%- for r in ns.rows | sort %}\n{%- set c = r.split('@@') %}\n| {{ c[1] }} | {{ c[2] }} | {{ c[3] }} | {{ c[4] }} | {{ c[5] }} |\n{%- endfor %}\n{%- if ns.bed %}\n\n*Bei Bedarf: {{ ns.bed | sort | join('; ') }}*\n{%- endif %}\n{% endfor -%}"
ABG_MD = "{%- set ns = namespace(r=[]) -%}{%- for e in integration_entities('medikamentenplan') | select('match', 'sensor\\..*_reichweite_tage_verbleibend$') if state_attr(e, 'status') == 'abgesetzt'@PF@ -%}{%- set a = states[e].attributes -%}{%- set d = (a.abgesetzt_am | as_datetime | as_local).strftime('%d.%m.%Y') if a.abgesetzt_am else '–' -%}{%- set ns.r = ns.r + ['- ' ~ a.name ~ ' (' ~ a.plan ~ ') · abgesetzt am ' ~ d] -%}{%- endfor -%}\n<details><summary><b>Abgesetzt ({{ ns.r | length }})</b></summary>\n\n{{ ns.r | sort | join('\\n') if ns.r else 'Keine abgesetzten Medikamente.' }}\n\n</details>"

R = "this.entity_id"  # auto-entities ersetzt den Platzhalter durch die Reichweite-Entity
LINK = {"reichweite_entity": R}


def popup():
    """Popup beim Tippen: kurze Zeilennamen, 'Neue Packung angefangen' als ganzflaechiger Button mit Bestaetigung."""
    rows = [{"entity_id": f"{d}.*_{k}", "attributes": LINK, "options": {"name": n}}
            for d, k, n in (("select", "hersteller", "Hersteller"), ("number", "packungsgrosse", "Packungsgröße"),
                            ("number", "anzahl_packungen", "Anzahl Packungen"))]
    button = {"entity_id": "button.*_neue_packung_angefangen", "attributes": LINK, "options": {
        "type": "button", "name": "Neue Packung angefangen", "icon": "mdi:package-variant-closed-plus",
        "show_state": False, "icon_height": "36px",
        "tap_action": {"action": "perform-action", "perform_action": "button.press",
                       "target": {"entity_id": R},
                       "confirmation": {"text": "Neue Packung jetzt anbrechen? Anbruch = heute, Bestand = Packungsgröße × Anzahl."}}}}
    return {"type": "vertical-stack", "cards": [
        {"type": "markdown", "content": "### {{ state_attr('this.entity_id','name') }}"},
        {"type": "custom:auto-entities", "show_empty": False,
         "card": {"type": "entities", "show_header_toggle": False}, "filter": {"include": rows}},
        {"type": "custom:auto-entities", "show_empty": False, "card_param": "cards",
         "card": {"type": "grid", "columns": 1, "square": False}, "filter": {"include": [button]}}]}


def vorrat():
    # kein "integration:"-Filter: braucht config/entity_registry/list (Admin-only), Nicht-Admins sahen sonst eine leere Karte
    rule = {"entity_id": "sensor.medikament_*_reichweite_tage_verbleibend", "options": {
        "type": "custom:mushroom-template-card",
        "primary": "{{ state_attr('this.entity_id','name') }}",
        "secondary": "{% set a = states['this.entity_id'].attributes %}{{ a.plan }} · {% if is_number(states('this.entity_id')) %}{{ states('this.entity_id') | int }} Tage übrig{% else %}Reichweite unbekannt{% endif %}{% if a.nachbestelldatum %} · nachbestellen ab {{ (a.nachbestelldatum | as_datetime | as_local).strftime('%d.%m.%Y') }}{% endif %}",
        "icon": "{{ {'ok':'mdi:pill','nachbestellen':'mdi:cart-arrow-down','aufgebraucht':'mdi:pill-off'}.get(state_attr('this.entity_id','status'),'mdi:help-circle') }}",
        "icon_color": "{{ {'ok':'green','nachbestellen':'orange','aufgebraucht':'red'}.get(state_attr('this.entity_id','status'),'grey') }}",
        "multiline_secondary": True, "layout": "horizontal", "fill_container": True,
        "tap_action": {"action": "fire-dom-event", "browser_mod": {"service": "browser_mod.popup",
                       "data": {"dismissable": True, "content": popup()}}},
        "hold_action": {"action": "more-info"}}}
    if PLAN:
        rule["attributes"] = {"plan": PLAN}
    return {"type": "custom:auto-entities", "show_empty": True,
            "card": {"type": "grid", "columns": 1, "square": False}, "card_param": "cards",
            "filter": {"include": [rule], "exclude": [{"attributes": {"status": "abgesetzt"}}]},
            "else": {"type": "markdown", "content": "Noch keine Medikamente angelegt (Einstellungen > Geräte & Dienste > Medikamentenplan)."},
            "sort": {"method": "state", "numeric": True}}


view = {"title": "Medikamente", "path": "medikamente", "icon": "mdi:pill", "type": "sections", "max_columns": 2, "sections": [
    {"type": "grid", "cards": [
        {"type": "heading", "heading": "Vorrat – dringendste zuerst · Tippen = Details/Neue Packung, Halten = more-info", "icon": "mdi:pill"},
        vorrat()]},
    {"type": "grid", "cards": [
        {"type": "markdown", "title": "Einnahmeplan", "content": PLAN_MD.replace("@PF@", PF)},
        {"type": "markdown", "content": ABG_MD.replace("@PF@", PF)}]}]}
print(json.dumps({"views": [view]}, ensure_ascii=False))
