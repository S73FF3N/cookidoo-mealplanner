# Mealplanner

Eine wiederverwendbare Django-App zur wöchentlichen Essensplanung mit
Cookidoo-Anbindung, Telegram-Bot und KI-gestützten Vorschlägen (Gemini).

## Installation

1. App ins Django-Projekt kopieren oder als Paket installieren, sodass der
   Ordner `mealplanner/` im Projektpfad liegt.

2. Abhängigkeiten installieren:
```bash
   pip install -r mealplanner/requirements.txt
```

3. In `settings.py` die App registrieren und Konfiguration ergänzen:
```python
   INSTALLED_APPS = [..., "mealplanner"]

   from decouple import config
   COOKIDOO_MAIL          = config("MAIL")
   COOKIDOO_PASSWORD      = config("PASSWORD")
   ROTATION_COLLECTION_ID = config("ROTATION_COLLECTION_ID")
   GEMINI_API_KEY         = config("GEMINI_API_KEY")
   TELEGRAM_TOKEN         = config("TELEGRAM_TOKEN")
   TELEGRAM_CHAT_IDS      = [s.strip() for s in
                            config("TELEGRAM_CHAT_IDS", default="").split(",")
                            if s.strip()]
```

4. Im Haupt-`urls.py` einbinden:
```python
   path("mealplanner/", include("mealplanner.urls")),
```

5. Migrationen ausführen:
```bash
   python manage.py migrate
```

6. Benötigte `.env`-Variablen: `MAIL`, `PASSWORD`, `ROTATION_COLLECTION_ID`,
   `GEMINI_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_IDS`.

## Befehle

- `python manage.py import_rotation`   – Rotation-Liste aus Cookidoo importieren
- `python manage.py import_candidates` – Kandidaten-Pool importieren
- `python manage.py suggest_meals [--save]` – Vorschläge erzeugen
- `python manage.py send_suggestions`  – Vorschläge per Telegram senden
- `python manage.py weekly_run`        – Sonntagslauf (Vorschläge + Senden)
