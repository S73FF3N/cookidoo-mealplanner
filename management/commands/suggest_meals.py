import json
import random
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from google import genai
from google.genai import types
from mealplanner.models import Recipe, WeeklyPlan
import time
from google.genai import errors as genai_errors

SYSTEM_PROMPT = """Du bist ein Assistent für die wöchentliche Essensplanung einer \
Familie (2 Erwachsene, 2 Kinder, 3 und 6 Jahre).

Wähle aus der Rotation-Liste GENAU so viele Gerichte wie im Feld "anzahl_rotation" \
angegeben. Diese bilden zusammen mit einem ggf. unter "neues_gericht" gesetzten \
Gericht die Vorauswahl, aus der die Familie später 6 final wählt.

Ist ein "neues_gericht" gesetzt, wähle es NICHT erneut, sorge aber für Vielfalt im \
Vergleich dazu (andere Hauptzutat/Stil).

VERBINDLICHE Zusammensetzung deiner Rotations-Auswahl (vor dem Antworten zählen!):
- MINDESTENS 2 Gerichte der Kategorie Fleisch oder Fisch (Feld "kategorie").
- MINDESTENS 3 Gerichte mit aktiv_min >= 30 (aufwändigere Gerichte). NICHT \
zugunsten schneller Gerichte abwählen.
- MINDESTENS 2 Gerichte mit aktiv_min < 30 (schnelle Gerichte).
- Übrige Plätze: vegetarische Gerichte (vegetarisch wird bevorzugt).

WEICHE Ziele:
- Echte Abwechslung bei Hauptzutat und Stil – nicht 5x Pasta, nicht 5x Bohnen.
- Gesunde, nahrhafte Gerichte bevorzugen (Nährwerte beachten).
- Freitext-Feedback und Historie der Vorwochen berücksichtigen.
- Berücksichtige Saisonalität.

Zähle vor der Ausgabe durch. Erfüllst du die MINDEST-Vorgaben nicht, korrigiere die \
Auswahl, bevor du antwortest.

Antworte AUSSCHLIESSLICH mit JSON, ohne Markdown, ohne Vortext:
{"suggestions": [{"id": "r12345", "reason": "kurze Begründung"}], \
"overall": "kurze Gesamtbegründung"}"""


def next_tuesday(today=None):
    today = today or datetime.date.today()
    ahead = (1 - today.weekday()) % 7 or 7
    return today + datetime.timedelta(days=ahead)


RETRYABLE_CODES = {429, 500, 502, 503, 504}


def generate_with_retry(client, *, model, contents, config,
                        max_attempts=4, log=print):
    """Ruft Gemini auf und wiederholt nur bei vorübergehenden Fehlern."""
    delay = 2.0
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config)
        except genai_errors.APIError as e:
            code = getattr(e, "code", None)
            # Dauerhafte Fehler (z. B. 400) sofort durchreichen
            if code not in RETRYABLE_CODES or attempt == max_attempts:
                raise
            wait = delay + random.uniform(0, 1)   # Backoff + Jitter
            log(f"Gemini überlastet (Code {code}), Versuch {attempt}/"
                f"{max_attempts} – neuer Versuch in {wait:.1f}s ...")
            time.sleep(wait)
            delay *= 2                              # 2s, 4s, 8s ...


class Command(BaseCommand):
    help = "Erzeugt 10 Vorschläge (9 Rotation + 1 neues) für die kommende Woche"

    def add_arguments(self, parser):
        parser.add_argument('--save', action='store_true',
                            help='Plan speichern (sonst nur Vorschau)')

    def handle(self, *args, **options):
        week_start = next_tuesday()

        last_plan = WeeklyPlan.objects.order_by('-week_start').first()
        banned = set()
        if last_plan:
            banned = set(last_plan.suggested.values_list('cookidoo_id', flat=True))

        # Rotations-Pool
        eligible = Recipe.objects.filter(
            in_rotation=True, active_time_min__lte=60
        ).exclude(cookidoo_id__in=banned)

        # Entdeckungs-Slot: 1 Kandidat deterministisch ziehen
        cand_pool = list(Recipe.objects.filter(
            is_candidate=True, in_rotation=False, active_time_min__lte=60
        ).exclude(cookidoo_id__in=banned))
        discovery = random.choice(cand_pool) if cand_pool else None
        n_rotation = 9 if discovery else 10

        if eligible.count() < n_rotation:
            self.stderr.write(f"Weniger als {n_rotation} Rotations-Gerichte.")
            return

        recipes_payload = [{
            "id": r.cookidoo_id, "name": r.name,
            "kategorie": r.get_category_display(),
            "aktiv_min": r.active_time_min, "kcal": r.kcal,
        } for r in eligible]

        neues = None
        if discovery:
            neues = {
                "name": discovery.name,
                "kategorie": discovery.get_category_display(),
                "aktiv_min": discovery.active_time_min,
            }

        history = []
        for plan in WeeklyPlan.objects.order_by('-week_start')[:3]:
            history.append({
                "woche": str(plan.week_start),
                "gewaehlt": [a.recipe.name for a in plan.assignments.all()],
                "feedback": plan.feedback_text,
            })

        user_msg = json.dumps({
            "anzahl_rotation": n_rotation,
            "neues_gericht": neues,
            "verfuegbare_gerichte": recipes_payload,
            "historie": history,
        }, ensure_ascii=False)

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        resp = generate_with_retry(
            client,
            model="gemini-2.5-flash",
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=1024),
                max_output_tokens=4096,
            ),
            log=self.stdout.write,
        )

        if not resp.text:
            fr = resp.candidates[0].finish_reason if resp.candidates else "?"
            self.stderr.write(f"Leere Antwort (finish_reason={fr}).")
            return
        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            self.stderr.write("Kein gültiges JSON (evtl. abgeschnitten):")
            self.stderr.write(resp.text[-300:])
            return

        by_id = {r.cookidoo_id: r for r in eligible}
        chosen = []
        self.stdout.write(f"\n=== Vorschläge für Woche ab {week_start} ===\n")
        for s in data["suggestions"]:
            r = by_id.get(s["id"])
            if not r:
                continue
            chosen.append(r)
            tag = {'meat': '🍖', 'fish': '🐟', 'veggie': '🌿'}[r.category]
            fast = ' ⚡' if r.active_time_min < 30 else ''
            self.stdout.write(f"{tag} {r.name} ({r.active_time_min} min{fast})")
            self.stdout.write(f"    → {s['reason']}")

        if discovery:
            chosen.append(discovery)
            tag = {'meat': '🍖', 'fish': '🐟', 'veggie': '🌿'}[discovery.category]
            fast = ' ⚡' if discovery.active_time_min < 30 else ''
            self.stdout.write(f"🆕 {tag} {discovery.name} "
                              f"({discovery.active_time_min} min{fast})")
            self.stdout.write("    → NEUES Gericht zum Ausprobieren (nicht in Rotation)")

        veggie = sum(1 for r in chosen if r.category == 'veggie')
        mf = sum(1 for r in chosen if r.category in ('meat', 'fish'))
        fastn = sum(1 for r in chosen if r.active_time_min < 30)
        longn = sum(1 for r in chosen if r.active_time_min >= 30)
        self.stdout.write(f"\nGesamt: {data.get('overall', '')}")
        self.stdout.write(f"Validierung: {len(chosen)} Gerichte | veggie {veggie} | "
                          f"Fleisch/Fisch {mf} | schnell {fastn} | aufwändig {longn}")

        if len(chosen) != 10:
            self.stderr.write(f"⚠ {len(chosen)} statt 10 Treffer.")

        if options['save']:
            plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_start)
            plan.suggested.set(chosen)
            plan.reasoning = data.get('overall', '')
            plan.save()
            self.stdout.write(self.style.SUCCESS("Plan gespeichert."))