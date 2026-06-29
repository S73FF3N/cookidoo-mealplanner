import asyncio
import datetime
from decouple import config
from django.conf import settings
from django.utils import timezone
from cookidoo_api import Cookidoo, CookidooConfig

# Offset ab week_start (= Dienstag, Einkaufstag ohne Mahlzeit)
DAY_OFFSET = {'Mi': 1, 'Do': 2, 'Fr': 3, 'Sa': 4, 'So': 5, 'Mo': 6}

async def _sync(week_start, day_recipes, new_recipe_ids):
    """day_recipes: {'Mo': ['r123', ...], ...}; new_recipe_ids: ['r999', ...]"""
    cfg = CookidooConfig(email=config("COOKIDOO_MAIL"), password=config("COOKIDOO_PASSWORD"))
    jar = aiohttp_cookiejar()
    import aiohttp
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        api = Cookidoo(session, cfg)
        await api.login()

        # 1) Gerichte in "Meine Woche" eintragen (pro Tag ein Aufruf)
        for day, ids in day_recipes.items():
            if not ids:
                continue
            d = week_start + datetime.timedelta(days=DAY_OFFSET[day])
            await api.add_recipes_to_calendar(d, ids)

        # 2) Neues Gericht der Rotation hinzufügen
        if new_recipe_ids:
            await api.add_recipes_to_custom_collection(
                settings.ROTATION_COLLECTION_ID, new_recipe_ids)


def aiohttp_cookiejar():
    import aiohttp
    return aiohttp.CookieJar(unsafe=True)


def sync_plan_to_cookidoo(plan):
    """Synchron aufrufbar aus dem Webhook. Gibt (ok, info_text) zurück."""
    from .models import Recipe

    if plan.synced_at:
        return False, f"Bereits am {plan.synced_at:%d.%m. %H:%M} synchronisiert."

    assignments = list(plan.assignments.select_related('recipe').all())
    if not assignments:
        return False, "Keine Tageszuordnungen vorhanden."

    day_recipes = {}
    new_ids = []
    for a in assignments:
        day_recipes.setdefault(a.day, []).append(a.recipe.cookidoo_id)
        if not a.recipe.in_rotation:          # = neues Gericht
            new_ids.append(a.recipe.cookidoo_id)

    try:
        asyncio.run(_sync(plan.week_start, day_recipes, new_ids))
    except Exception as e:
        return False, f"Cookidoo-Fehler: {e}"

    # Lokale Statistiken & Rotation-Status nachziehen
    today = timezone.now().date()
    for a in assignments:
        r = a.recipe
        r.last_selected = today
        r.times_selected = (r.times_selected or 0) + 1
        if not r.in_rotation:                 # neues Gericht aufgenommen
            r.in_rotation = True
        r.save(update_fields=['last_selected', 'times_selected', 'in_rotation'])

    # last_suggested für alle Vorschläge der Woche setzen
    plan.suggested.update(last_suggested=plan.week_start)

    msg = f"{len(assignments)} Gerichte in 'Meine Woche' eingetragen."
    if new_ids:
        names = ", ".join(a.recipe.name for a in assignments
                          if a.recipe.cookidoo_id in new_ids)
        msg += f"\n🆕 Zur Rotation hinzugefügt: {names}"

    plan.synced_at = timezone.now()
    plan.save(update_fields=['synced_at'])
    return True, msg
