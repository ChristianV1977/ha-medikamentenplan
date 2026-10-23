DOMAIN = "medikamentenplan"
STORAGE_VERSION = 1
PLATFORMS = ["sensor", "button"]
SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
SIGNAL_NEW = f"{DOMAIN}_new_{{}}"

FORMS = ["tablette", "kapsel", "tropfen", "saft", "spray", "salbe", "pflaster", "zaepfchen", "spritze", "pulver", "sonstige"]
MODES = ["taeglich", "intervall", "bedarf"]
# Felder, die beim "aus Katalog uebernehmen" mitkommen (keine Daten/Bestand)
CATALOG_FIELDS = ["name", "hersteller", "wirkstoff", "darreichungsform", "dosis", "einheit", "modus",
                  "pro_tag", "intervall_tage", "bedarf_pro_woche", "packungsgroesse", "zweck",
                  "rezeptpflichtig", "vorlauf_tage", "notiz"]
