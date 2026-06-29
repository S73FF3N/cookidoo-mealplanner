from django.core.management.base import BaseCommand
from django.conf import settings
from mealplanner.models import WeeklyPlan
from mealplanner.telegram_api import send_message, build_selection_keyboard


class Command(BaseCommand):
    help = "Sendet die Vorschläge des neuesten Plans per Telegram"

    def handle(self, *args, **options):
        plan = WeeklyPlan.objects.order_by('-week_start').first()
        if not plan:
            self.stderr.write("Kein Plan. Erst: suggest_meals --save")
            return
        plan.selected.clear()
        text = (f"<b>🍽 Essensplan – Woche ab {plan.week_start}</b>\n\n"
                f"Tippt 6 Gerichte zum Auswählen an:")
        for chat_id in settings.TELEGRAM_CHAT_IDS:
            res = send_message(chat_id, text,
                               reply_markup=build_selection_keyboard(plan))
            ok = "✓" if res.get("ok") else f"Fehler: {res}"
            self.stdout.write(f"{chat_id}: {ok}")
