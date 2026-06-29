import asyncio
import aiohttp
from django.conf import settings
from django.core.management.base import BaseCommand
from cookidoo_api import Cookidoo, CookidooConfig
from mealplanner.models import Recipe

SOURCE_COLLECTIONS = ["soul food", "einfach. selbst. gemacht."]
MAX_ACTIVE_MIN = 60


def classify(categories):
    names = " ".join(c.name.lower() for c in categories)
    if "fleisch" in names:
        return "meat"
    if "fisch" in names or "meeresfr" in names:
        return "fish"
    return "veggie"


def is_main_dish(categories):
    return any("hauptgericht" in c.name.lower() for c in categories)


def extract_nutrition(detail):
    kcal = protein = None
    try:
        for group in detail.nutrition_groups:
            for rn in group.recipe_nutritions:
                for n in rn.nutritions:
                    if n.type == "kcal":
                        kcal = int(n.number)
                    elif n.type == "protein":
                        protein = int(n.number)
    except (AttributeError, TypeError):
        pass
    return kcal, protein


async def fetch_candidates(known_ids, log):
    cfg = CookidooConfig(email=settingsCOOKIDOO_MAIL, password=settings.COOKIDOO_PASSWORD)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        api = Cookidoo(session, cfg)
        await api.login()

        managed = await api.get_managed_collections()
        wanted = [c for c in managed
                  if c.name.strip().lower() in SOURCE_COLLECTIONS]
        log(f"{len(wanted)} Quell-Sammlungen: " + ", ".join(c.name for c in wanted))

        base = {}
        for col in wanted:
            for ch in getattr(col, "chapters", []) or []:
                for r in getattr(ch, "recipes", []) or []:
                    base[r.id] = r.name
        log(f"{len(base)} Rezepte in den Sammlungen.")

        todo = {rid: n for rid, n in base.items() if rid not in known_ids}
        log(f"{len(todo)} neue zu prüfen (Details abrufen, kann dauern)...")

        results, nonmain, slow = [], 0, 0
        for i, (rid, name) in enumerate(todo.items(), 1):
            if i % 25 == 0:
                log(f"  ... {i}/{len(todo)}")
            try:
                d = await api.get_recipe_details(rid)
            except Exception as e:
                log(f"  Übersprungen {name}: {e}")
                continue
            if not is_main_dish(d.categories):
                nonmain += 1
                continue
            active = round(d.active_time / 60)
            if active > MAX_ACTIVE_MIN:
                slow += 1
                continue
            kcal, protein = extract_nutrition(d)
            results.append({
                "cookidoo_id": rid, "name": name,
                "active_time_min": active,
                "total_time_min": round(d.total_time / 60),
                "category": classify(d.categories),
                "kcal": kcal, "protein_g": protein,
                "url": getattr(d, "url", ""),
            })
        log(f"Gefiltert: {nonmain} keine Hauptgerichte, {slow} zu lang.")
        return results


class Command(BaseCommand):
    help = "Importiert Kandidaten aus den kuratierten Sammlungen"

    def handle(self, *args, **options):
        known = set(Recipe.objects.values_list("cookidoo_id", flat=True))
        data = asyncio.run(fetch_candidates(known, self.stdout.write))

        created = 0
        for d in data:
            _, was_created = Recipe.objects.update_or_create(
                cookidoo_id=d["cookidoo_id"],
                defaults={k: v for k, v in d.items() if k != "cookidoo_id"}
                         | {"in_rotation": False, "is_candidate": True},
            )
            created += was_created

        pool = Recipe.objects.filter(is_candidate=True, in_rotation=False).count()
        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {created} neue Kandidaten. Pool: {pool} Gerichte."
        ))
