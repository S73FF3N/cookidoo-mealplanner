import asyncio
import aiohttp
from django.conf import settings
from django.core.management.base import BaseCommand
from cookidoo_api import Cookidoo, CookidooConfig
from mealplanner.models import Recipe


def classify(categories):
    names = " ".join(c.name.lower() for c in categories)
    if "fleisch" in names:
        return "meat"
    if "fisch" in names or "meeresfr" in names:
        return "fish"
    return "veggie"


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


async def fetch_rotation():
    cfg = CookidooConfig(email=settings.COOKIDOO_MAIL, password=settings.COOKIDOO_PASSWORD)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        api = Cookidoo(session, cfg)
        await api.login()

        custom = await api.get_custom_collections()
        rotation = next(
            (c for c in custom if c.name.strip().lower() == "rotation"), None
        )
        if rotation is None:
            raise RuntimeError("Liste 'Rotation' nicht gefunden")

        base = [r for chapter in rotation.chapters for r in chapter.recipes]

        results = []
        for r in base:
            d = await api.get_recipe_details(r.id)
            kcal, protein = extract_nutrition(d)
            results.append({
                "cookidoo_id": r.id,
                "name": r.name,
                "active_time_min": round(d.active_time / 60),
                "total_time_min": round(d.total_time / 60),
                "category": classify(d.categories),
                "kcal": kcal,
                "protein_g": protein,
                "url": getattr(d, "url", ""),
            })
        return results


class Command(BaseCommand):
    help = "Importiert die Cookidoo-Liste 'Rotation'"

    def handle(self, *args, **options):
        data = asyncio.run(fetch_rotation())
        current_ids = {d["cookidoo_id"] for d in data}

        created = updated = 0
        for d in data:
            _, was_created = Recipe.objects.update_or_create(
                cookidoo_id=d["cookidoo_id"],
                defaults={k: v for k, v in d.items() if k != "cookidoo_id"}
                         | {"in_rotation": True},
            )
            created += was_created
            updated += not was_created

        removed = Recipe.objects.exclude(cookidoo_id__in=current_ids)\
                                .update(in_rotation=False)

        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {created} neu, {updated} aktualisiert, {removed} entfernt"
        ))
