import json
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Recipe, WeeklyPlan, DayAssignment
import random
from .telegram_api import (send_message, edit_reply_markup, edit_message_text,
                           answer_callback, build_selection_keyboard,
                           build_done_keyboard, format_day_plan)

DAYS = ['Mi', 'Do', 'Fr', 'Sa', 'So', 'Mo']


@csrf_exempt
@require_POST
def telegram_webhook(request):
    secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", None)
    if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        return HttpResponseForbidden("bad secret")

    update = json.loads(request.body)
    if "callback_query" in update:
        _handle_callback(update["callback_query"])
    elif "message" in update:
        _handle_message(update["message"])
    return JsonResponse({"ok": True})


def _handle_message(msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text:
        return

    # Befehle haben Vorrang
    if text in ("/start", "/id"):
        send_message(chat_id, f"Deine Chat-ID: <code>{chat_id}</code>")
        return

    if str(chat_id) not in settings.TELEGRAM_CHAT_IDS:
        return  # nicht berechtigt – st: stiller Abbruch

    # Wartet ein Plan auf Feedback? Dann diese Nachricht als Feedback speichern.
    plan = WeeklyPlan.objects.filter(awaiting_feedback=True)\
                             .order_by('-week_start').first()
    if plan:
        plan.feedback_text = text
        plan.awaiting_feedback = False
        plan.save(update_fields=['feedback_text', 'awaiting_feedback'])
        send_message(chat_id, "✅ Notiert – danke! Das fließt in die nächste Planung ein.")
        return

    # Sonst: kurzer Hinweis
    send_message(chat_id, "Aktuell warte ich auf kein Feedback. "
                          "Die Vorschläge kommen automatisch am Montagabend.")


def _handle_callback(cq):
    data = cq.get("data", "")
    chat_id = cq["message"]["chat"]["id"]
    if str(chat_id) not in settings.TELEGRAM_CHAT_IDS:
        return answer_callback(cb_id, "Nicht berechtigt.", show_alert=True)
    message_id = cq["message"]["message_id"]
    cb_id = cq["id"]

    # --- Gerichte an-/abwählen ---
    if data.startswith("sel:"):
        _, plan_id, rid = data.split(":", 2)
        try:
            plan = WeeklyPlan.objects.get(id=int(plan_id))
            recipe = Recipe.objects.get(cookidoo_id=rid)
        except (WeeklyPlan.DoesNotExist, Recipe.DoesNotExist):
            return answer_callback(cb_id, "Nicht gefunden.")
        if plan.selected.filter(pk=recipe.pk).exists():
            plan.selected.remove(recipe)
        else:
            if plan.selected.count() >= 6:
                return answer_callback(cb_id, "Schon 6 gewählt – erst eines abwählen.",
                                       show_alert=True)
            plan.selected.add(recipe)
        edit_reply_markup(chat_id, message_id, build_selection_keyboard(plan))
        answer_callback(cb_id)

    # --- Auswahl bestätigen -> zufällige Tageszuordnung, fertig anzeigen ---
    elif data.startswith("confirm:"):
        _, plan_id = data.split(":", 1)
        plan = WeeklyPlan.objects.filter(id=int(plan_id)).first()
        if not plan:
            return answer_callback(cb_id, "Plan nicht gefunden.")
        n = plan.selected.count()
        if n > 6:
            return answer_callback(cb_id, "Höchstens 6 Gerichte.", show_alert=True)

        plan.assignments.all().delete()

        # 0 Gerichte = Woche bewusst aussetzen
        if n == 0:
            answer_callback(cb_id, "Woche ausgesetzt – es wird nichts geplant.",
                            show_alert=True)
            edit_message_text(chat_id, message_id,
                              f"🚫 <b>Woche ab {plan.week_start} ausgesetzt</b>\n\n"
                              f"Es wird nichts an Cookidoo gesendet.")
            return

        # 1–6 Gerichte: auf die ersten Tage verteilen
        recipes = list(plan.selected.all())
        random.shuffle(recipes)
        for day, r in zip(DAYS, recipes):
            DayAssignment.objects.create(plan=plan, recipe=r, day=day)
        answer_callback(cb_id)
        edit_message_text(chat_id, message_id,
                          format_day_plan(plan),
                          reply_markup=build_done_keyboard(plan))

    # --- Plan abschließen ---
    elif data.startswith("done:"):
        _, plan_id = data.split(":", 1)
        plan = WeeklyPlan.objects.filter(id=int(plan_id)).first()
        if not plan:
            return answer_callback(cb_id, "Plan nicht gefunden.")

        # sofort quittieren, damit Telegram nicht in den Timeout läuft
        answer_callback(cb_id, "⏳ Sende an Cookidoo …")
        edit_message_text(chat_id, message_id,
                          "⏳ <b>Sende an Cookidoo …</b>\n\n" + format_day_plan(plan))

        from .cookidoo_sync import sync_plan_to_cookidoo
        ok, info = sync_plan_to_cookidoo(plan)

        head = "✅ <b>Wochenplan synchronisiert</b>" if ok else "⚠️ <b>Fehler</b>"
        edit_message_text(chat_id, message_id,
                          f"{head}\n\n{format_day_plan(plan)}\n\n{info}")

        if ok:
            # andere wartende Pläne zurücksetzen, diesen markieren
            WeeklyPlan.objects.filter(awaiting_feedback=True)\
                              .update(awaiting_feedback=False)
            plan.awaiting_feedback = True
            plan.save(update_fields=['awaiting_feedback'])
            send_message(chat_id,
                "💬 Optional: Warum diese Auswahl? Schreib mir gern ein paar "
                "Stichworte (z. B. 'diese Woche wenig Zeit', 'Kinder wollten Pasta', "
                "'mal was Neues probiert'). Das verbessert die nächsten Vorschläge.\n\n"
                "Oder ignoriere diese Nachricht einfach.")
