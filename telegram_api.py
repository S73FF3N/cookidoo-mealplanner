import requests
from django.conf import settings

API = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}"
TAGS = {'meat': '🍖', 'fish': '🐟', 'veggie': '🌿'}
DAY_LABELS = {'Mo': 'Montag', 'Mi': 'Mittwoch', 'Do': 'Donnerstag',
              'Fr': 'Freitag', 'Sa': 'Samstag', 'So': 'Sonntag'}
DAY_ORDER = ['Mi', 'Do', 'Fr', 'Sa', 'So', 'Mo']


def send_message(chat_id, text, reply_markup=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        p["reply_markup"] = reply_markup
    return requests.post(f"{API}/sendMessage", json=p, timeout=20).json()


def edit_reply_markup(chat_id, message_id, reply_markup):
    return requests.post(f"{API}/editMessageReplyMarkup", json={
        "chat_id": chat_id, "message_id": message_id,
        "reply_markup": reply_markup}, timeout=20).json()


def edit_message_text(chat_id, message_id, text, reply_markup=None):
    p = {"chat_id": chat_id, "message_id": message_id,
         "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        p["reply_markup"] = reply_markup
    return requests.post(f"{API}/editMessageText", json=p, timeout=20).json()


def answer_callback(cb_id, text=None, show_alert=False):
    p = {"callback_query_id": cb_id}
    if text:
        p["text"] = text
        p["show_alert"] = show_alert
    return requests.post(f"{API}/answerCallbackQuery", json=p, timeout=20).json()


def build_selection_keyboard(plan):
    selected_ids = set(plan.selected.values_list('cookidoo_id', flat=True))
    rows = []
    for r in plan.suggested.all().order_by('category', 'name'):
        check = "✅" if r.cookidoo_id in selected_ids else "▫️"
        new = "🆕" if (r.is_candidate and not r.in_rotation) else ""
        fast = "⚡" if r.active_time_min < 30 else ""
        label = f"{check} {TAGS[r.category]}{new} {r.name} ({r.active_time_min}m{fast})"
        rows.append([{"text": label,
                      "callback_data": f"sel:{plan.id}:{r.cookidoo_id}"}])
    n = len(selected_ids)
    if n == 0:
        confirm = "🚫 Diese Woche aussetzen"
    else:
        confirm = f"✅ Übernehmen ({n}/6)"
    rows.append([{"text": confirm, "callback_data": f"confirm:{plan.id}"}])
    return {"inline_keyboard": rows}


def format_day_plan(plan):
    lines = [f"<b>📅 Wochenplan ab {plan.week_start}</b>",
             "Zwei Tage antippen, um Gerichte zu tauschen:\n"]
    by_day = {a.day: a.recipe for a in plan.assignments.all()}
    for d in DAY_ORDER:
        r = by_day.get(d)
        if r:
            fast = " ⚡" if r.active_time_min < 30 else ""
            lines.append(f"<b>{DAY_LABELS[d]}:</b> {TAGS[r.category]} "
                         f"{r.name} ({r.active_time_min}m{fast})")
        else:
            lines.append(f"<b>{DAY_LABELS[d]}:</b> –")
    return "\n".join(lines)


def format_day_plan(plan):
    lines = [f"<b>📅 Wochenplan ab {plan.week_start}</b>\n"]
    by_day = {a.day: a.recipe for a in plan.assignments.all()}
    for d in DAY_ORDER:
        r = by_day.get(d)
        if r:
            fast = " ⚡" if r.active_time_min < 30 else ""
            lines.append(f"<b>{DAY_LABELS[d]}:</b> {TAGS[r.category]} "
                         f"{r.name} ({r.active_time_min}m{fast})")
        else:
            lines.append(f"<b>{DAY_LABELS[d]}:</b> –")
    return "\n".join(lines)


def build_done_keyboard(plan):
    return {"inline_keyboard": [
        [{"text": "✅ Fertig & an Cookidoo senden",
          "callback_data": f"done:{plan.id}"}]
    ]}
