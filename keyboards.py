# -*- coding: utf-8 -*-
import config

BTN_TICKET = "🎫 تیکت"
BTN_FAQ = "❓ سوالات متداول شما"
BTN_NEW_TICKET = "➕ ساخت تیکت"
BTN_MY_TICKETS = "📂 تیکت‌های من"
BTN_BACK_MAIN = "⬅️ بازگشت به منو"
BTN_BACK = "⬅️ بازگشت"
BTN_CLOSE_TICKET = "🔒 بستن تیکت"

BTN_FAQ_NEW = "➕ ساخت سوال"
BTN_FAQ_LIST = "📚 دیدن تمامی سوال‌ها"

BTN_PANEL = "🛠 پنل Staff"
BTN_MANAGE = "🎫 مدیریت تیکت‌ها"
BTN_MINE = "👤 تیکت‌های من"
BTN_STATS_ME = "📊 آمار من"
BTN_STATS_SYS = "📈 آمار سیستم"
BTN_STAFF_MGMT = "👨‍💼 مدیریت Staff"
BTN_ALERT = "🚨 ارسال اعلان"
BTN_UNANSWERED = "❗ بدون پاسخ"
BTN_STALE = "⏰ تیکت‌های معطل"
BTN_SEARCH = "🔍 جستجوی تیکت"

BTN_ADD_STAFF = "➕ افزودن Staff جدید"
BTN_CHANGE_RANK = "🔄 تغییر رنک Staff"
BTN_REMOVE_STAFF = "➖ حذف Staff"
BTN_LIST_STAFF = "📋 لیست Staffها"

BTN_ALERT_STAFF = "📢 به همه Staffها"
BTN_ALERT_USERS = "📢 به همه کاربران"

RATING_LABELS = ["⭐ 1", "⭐ 2", "⭐ 3", "⭐ 4", "⭐ 5"]


def main_menu_keypad():
    return {"rows": [[{"text": BTN_TICKET}], [{"text": BTN_FAQ}]], "resize_keyboard": True}


def staff_home_keypad():
    return {"rows": [[{"text": BTN_PANEL}]], "resize_keyboard": True}


def ticket_menu_keypad():
    return {"rows": [[{"text": BTN_NEW_TICKET}], [{"text": BTN_MY_TICKETS}],
                      [{"text": BTN_BACK_MAIN}]], "resize_keyboard": True}


def in_ticket_chat_keypad():
    return {"rows": [[{"text": BTN_BACK_MAIN}, {"text": BTN_CLOSE_TICKET}]], "resize_keyboard": True}


def staff_in_ticket_keypad():
    return {"rows": [[{"text": BTN_CLOSE_TICKET}, {"text": BTN_BACK}]], "resize_keyboard": True}


def faq_menu_keypad(can_create=False):
    rows = []
    if can_create:
        rows.append([{"text": BTN_FAQ_NEW}])
    rows.append([{"text": BTN_FAQ_LIST}])
    rows.append([{"text": BTN_BACK_MAIN if True else BTN_BACK}])
    return {"rows": rows, "resize_keyboard": True}


def rating_inline_keypad(ticket_id):
    return {"rows": [[{"type": "Simple", "button_id": f"rate_{ticket_id}_{i}", "button_text": t}
                       for i, t in enumerate(RATING_LABELS, start=1)]]}


def review_choice_inline_keypad(ticket_id):
    return {"rows": [[
        {"type": "Simple", "button_id": f"revw_{ticket_id}", "button_text": "📝 ثبت نظر"},
        {"type": "Simple", "button_id": f"revs_{ticket_id}", "button_text": "⏭ بدون نظر"},
    ]]}


def confirm_close_inline_keypad(ticket_id):
    return {"rows": [[
        {"type": "Simple", "button_id": f"userclose_yes_{ticket_id}", "button_text": "✅ بله، مطمئنم"},
        {"type": "Simple", "button_id": f"userclose_no_{ticket_id}", "button_text": "❌ نه، منصرف شدم"},
    ]]}


def faq_preview_inline_keypad():
    return {"rows": [
        [{"type": "Simple", "button_id": "faq_edit_q", "button_text": "✏️ ویرایش سوال"}],
        [{"type": "Simple", "button_id": "faq_edit_a", "button_text": "✏️ ویرایش جواب"}],
        [{"type": "Simple", "button_id": "faq_submit", "button_text": "✅ ثبت"}],
    ]}


def faq_list_inline_keypad(items):
    rows = []
    for it in items:
        short = it["question"] if len(it["question"]) <= 40 else it["question"][:37] + "..."
        rows.append([{"type": "Simple", "button_id": f"faqv_{it['id']}", "button_text": f"❓ {short}"}])
    return {"rows": rows}


def user_tickets_list_inline_keypad(tickets):
    rows = []
    for t in tickets:
        label = "🔴 باز" if t["status"] != "CLOSED" else "✅ بسته"
        rows.append([{"type": "Simple", "button_id": f"myticket_{t['id']}",
                       "button_text": f"🎫 #{t['id']} — {label}"}])
    return {"rows": rows}


# ---------------- پنل Staff ----------------
def staff_panel_keypad(rank):
    rows = [[{"text": BTN_MANAGE}], [{"text": BTN_MINE}], [{"text": BTN_FAQ}], [{"text": BTN_STATS_ME}],
            [{"text": BTN_UNANSWERED}, {"text": BTN_STALE}], [{"text": BTN_SEARCH}]]
    if config.RANK_LEVEL.get(rank, 0) >= config.RANK_LEVEL[config.RANK_ADMIN]:
        rows.append([{"text": BTN_STATS_SYS}, {"text": BTN_ALERT}])
    if config.RANK_LEVEL.get(rank, 0) >= config.RANK_LEVEL[config.RANK_MANAGER]:
        rows.append([{"text": BTN_STAFF_MGMT}])
    rows.append([{"text": BTN_BACK_MAIN}])
    return {"rows": rows, "resize_keyboard": True}


TICKET_FILTER_BUTTONS = [
    ("🆕 جدید", "new"),
    ("⏳ منتظر پاسخ Staff", "waiting_staff"),
    ("💬 در حال پاسخ‌گویی", "in_progress"),
    ("📨 منتظر پاسخ کاربر", "waiting_user"),
    ("🔴 باز", "open"),
    ("🔒 بسته‌شده", "closed"),
    ("📂 همه", "all"),
]


def ticket_management_keypad(counts):
    rows = [[{"text": f"{label} ({counts.get(key, 0)})"}] for label, key in TICKET_FILTER_BUTTONS]
    rows.append([{"text": BTN_BACK}])
    return {"rows": rows, "resize_keyboard": True}


def tickets_list_inline_keypad(tickets):
    rows = []
    for t in tickets:
        rows.append([{"type": "Simple", "button_id": f"view_{t['id']}",
                       "button_text": f"🎫 #{t['id']} — {config.STATUS_LABELS_FA.get(t['status'], t['status'])}"}])
    return {"rows": rows}


def ticket_action_inline_keypad(ticket_id, is_owner):
    rows = []
    if is_owner:
        rows.append([{"type": "Simple", "button_id": f"transfer_{ticket_id}", "button_text": "🔄 انتقال"}])
        rows.append([{"type": "Simple", "button_id": f"note_{ticket_id}", "button_text": "📝 یادداشت داخلی"}])
    else:
        rows.append([{"type": "Simple", "button_id": f"claim_{ticket_id}", "button_text": "👤 دریافت تیکت"}])
    rows.append([{"type": "Simple", "button_id": f"uinfo_{ticket_id}", "button_text": "👤 اطلاعات کاربر"},
                 {"type": "Simple", "button_id": f"hist_{ticket_id}", "button_text": "📜 تاریخچه"}])
    return {"rows": rows}


def busy_staff_inline_keypad(active_ticket_id):
    return {"rows": [
        [{"type": "Simple", "button_id": f"view_{active_ticket_id}", "button_text": "🎫 ورود به تیکت فعلی"}],
        [{"type": "Simple", "button_id": f"close_{active_ticket_id}", "button_text": "🔒 بستن تیکت"}],
        [{"type": "Simple", "button_id": f"transfer_{active_ticket_id}", "button_text": "🔄 انتقال تیکت"}],
    ]}


def new_ticket_notification_inline_keypad(ticket_id):
    return {"rows": [[{"type": "Simple", "button_id": f"claim_{ticket_id}", "button_text": "👀 مشاهده تیکت"}]]}


def staff_mgmt_keypad():
    return {"rows": [
        [{"text": BTN_ADD_STAFF}], [{"text": BTN_CHANGE_RANK}],
        [{"text": BTN_REMOVE_STAFF}], [{"text": BTN_LIST_STAFF}],
        [{"text": BTN_BACK}],
    ], "resize_keyboard": True}


def alert_menu_keypad():
    return {"rows": [[{"text": BTN_ALERT_STAFF}], [{"text": BTN_ALERT_USERS}], [{"text": BTN_BACK}]],
            "resize_keyboard": True}


def rank_pick_inline_keypad(target_guid):
    return {"rows": [[{"type": "Simple", "button_id": f"setrank_{target_guid}_{r}",
                        "button_text": config.RANK_LABELS_FA[r]}] for r in config.RANK_LEVEL.keys()]}


def staff_pick_inline_keypad(staff_guids, display_name_fn):
    return {"rows": [[{"type": "Simple", "button_id": f"pickrank_{g}", "button_text": display_name_fn(g)}]
                      for g in staff_guids]}
