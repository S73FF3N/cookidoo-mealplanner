from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Mealplanner: Vorschläge erzeugen, speichern und per Telegram senden"

    def handle(self, *args, **options):

        import datetime
        if datetime.date.today().weekday() != 6:   # 6 = Sonntag
            self.stdout.write("Heute ist nicht Sonntag – kein Lauf.")
            return

        self.stdout.write("→ Erzeuge & speichere Vorschläge ...")
        call_command('suggest_meals', save=True)
        self.stdout.write("→ Sende an Telegram ...")
        call_command('send_suggestions')
        self.stdout.write(self.style.SUCCESS("Mealplanner fertig."))
