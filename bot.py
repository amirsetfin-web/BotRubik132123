# -*- coding: utf-8 -*-
"""
بات پشتیبانی روبیکا - نسخه نهایی

⚠️ نکته درباره API rubpy:
    - rubpy غیررسمیه؛ اسم دقیق دکوراتور کال‌بک دکمه‌های شیشه‌ای
      (@app.on_callback_query) و فیلدهای دقیق آبجکت update (به‌خصوص برای
      تشخیص "کاربر برای اولین بار دکمه‌ی Start رو زده") رو با مستندات نسخه‌ی
      نصب‌شده‌ی خودتون تطبیق بدید -- جاهاش با کامنت TODO/VERIFY مشخص شده.
    - تشخیص "اولین ورود" (قبل از این‌که کاربر هیچ پیامی نداده): چون روبیکا به
      جای دستور متنی /start یک دکمه‌ی Start بومی نشون می‌ده، این بات فرض می‌کنه
      اولین Update دریافتی از هر GUID (چه از نوع "استارت شد" چه یک پیام معمولی)
      همون لحظه‌ی شروعه؛ این منطق در on_message با چک‌کردن نبودن رکورد کاربر در
      دیتابیس پیاده شده -- اگر rubpy نوع Update مشخصی برای "Start" داره، بهتره
      دقیقاً از همون استفاده کنید.

اجرا:
    pip install rubpy
    python bot.py
"""

import asyncio
import re

from rubpy import Client
from rubpy.types import Updates

import config
import database as db
import keyboards as kb

app = Client(name=config.SESSION_NAME)


# ============================================================
# ابزار کمکی
# ============================================================
def display_name(guid):
    info = db.get_user_info(guid)
    return info["display_name"] or guid


def rank_label(guid):
    r = db.get_staff_rank(guid)
    return config.RANK_LABELS_FA.get(r, r or "-")


async def notify_all_staff(text, inline_keypad=None):
    for s in db.list_staff_guids():
        try:
            await app.send_message(s, text, inline_keypad=inline_keypad)
        except Exception:
            pass


async def notify_new_ticket(ticket_id, user_guid, reason):
    text = (
        f"🔔 یک تیکت جدید ساخته شد\n"
        f"📝 موضوع: {reason}\n"
        f"🎫 شماره تیکت: #{ticket_id}\n"
        f"👤 کاربر: {display_name(user_guid)}"
    )
    await notify_all_staff(text, inline_keypad=kb.new_ticket_notification_inline_keypad(ticket_id))


async def broadcast_closure_notice(ticket_id):
    t = db.get_ticket(ticket_id)
    if not t:
        return
    if t["closed_by"] == t["user_guid"]:
        closer = f"خود کاربر ({display_name(t['user_guid'])})"
        reason_line = ""
    else:
        closer = f"{display_name(t['closed_by'])} ({rank_label(t['closed_by'])})"
        reason_line = f"\n📄 دلیل بستن: {t['close_reason'] or '-'}"
    text = (
        f"🔒 تیکت #{t['id']} بسته شد\n"
        f"👤 کاربر: {display_name(t['user_guid'])}\n"
        f"📝 موضوع تیکت: {t['reason']}\n"
        f"🔒 بسته‌شده توسط: {closer}"
        f"{reason_line}\n"
        f"🕒 زمان بستن: {t['closed_at']}"
    )
    await notify_all_staff(text)


async def broadcast_rating_update(ticket_id):
    t = db.get_ticket(ticket_id)
    if not t:
        return
    text = (
        f"📌 به‌روزرسانی تیکت بسته‌شده #{t['id']}\n"
        f"⭐ امتیاز کاربر: {t['rating'] or '-'}\n"
        f"📝 نظر: {t['review'] or 'ثبت نشد'}"
    )
    await notify_all_staff(text)


# ============================================================
# روتر اصلی
# ============================================================
@app.on_message()
async def router(update: Updates):
    text = (update.text or "").strip()
    guid = update.author_guid

    is_first_contact = db.get_user_info(guid)["display_name"] is None and db.get_state(guid)[0] is None
    db.ensure_user(guid)
    state, ctx = db.get_state(guid)

    # ---------- اولین برخورد: باید نام ماینکرفتی رو بگیریم ----------
    if is_first_contact or state == "AWAIT_MC_NAME":
        if state != "AWAIT_MC_NAME":
            db.set_state(guid, "AWAIT_MC_NAME")
            await update.reply("🎮 قبل از شروع، لطفاً نام ماینکرفتی (Minecraft Username) خودتون رو وارد کنید:")
            return
        # پیام بعدی = نام ماینکرفتی
        mc_name = text
        if not mc_name:
            await update.reply("لطفاً فقط نام کاربری ماینکرفتتون رو بفرستید.")
            return
        db.set_display_name(guid, mc_name)
        db.clear_state(guid)
        await update.reply(f"✅ خوش اومدید {mc_name} 👋")
        await send_main_menu(update, guid)
        return

    # ---------- دستورات متنی ----------
    if text == "/start":
        db.clear_state(guid)
        await send_main_menu(update, guid)
        return

    if text == kb.BTN_BACK_MAIN:
        db.clear_state(guid)
        await send_main_menu(update, guid)
        return

    if state:
        handled = await handle_state(update, guid, state, ctx, text)
        if handled:
            return

    # ---------- منوی اصلی ----------
    if text == kb.BTN_TICKET and not db.is_staff(guid):
        db.clear_state(guid)
        await update.reply("بخش تیکت 🎫", chat_keypad=kb.ticket_menu_keypad())
        return

    if text == kb.BTN_FAQ:
        db.clear_state(guid)
        can_create = db.has_rank(guid, config.PERMISSION["FAQ_CREATE"])
        await update.reply("سوالات متداول ❓", chat_keypad=kb.faq_menu_keypad(can_create=can_create))
        return

    if text == kb.BTN_NEW_TICKET:
        existing = db.get_open_ticket_for_user(guid)
        if existing:
            await update.reply(
                f"شما یک تیکت باز دارید (#{existing['id']}). تا وقتی بسته نشده نمی‌تونید تیکت جدید بسازید؛ ادامه بدید:"
            )
            db.set_state(guid, "IN_TICKET_CHAT", {"ticket_id": existing["id"]})
            await update.reply("پیام خود را بنویسید.", chat_keypad=kb.in_ticket_chat_keypad())
            return
        db.set_state(guid, "AWAIT_TICKET_REASON")
        await update.reply("📝 لطفاً موضوع تیکت را وارد کنید.")
        return

    if text == kb.BTN_MY_TICKETS:
        await show_my_tickets_summary(update, guid)
        return

    if text == kb.BTN_FAQ_NEW and db.has_rank(guid, config.PERMISSION["FAQ_CREATE"]):
        db.set_state(guid, "AWAIT_FAQ_QUESTION")
        await update.reply("❓ سوال را وارد کنید.")
        return

    if text == kb.BTN_FAQ_LIST:
        await show_faq_list(update)
        return

    # ---------- پنل Staff ----------
    if text == kb.BTN_PANEL and db.is_staff(guid):
        rank = db.get_staff_rank(guid)
        await update.reply("🛠 پنل Staff", chat_keypad=kb.staff_panel_keypad(rank))
        return

    if db.is_staff(guid):
        if await handle_staff_panel_text(update, guid, text):
            return

    # ---------- گفتگوی داخل تیکت (کاربر) ----------
    if state == "IN_TICKET_CHAT":
        await handle_user_ticket_message(update, guid, ctx.get("ticket_id"), text)
        return

    # ---------- پیش‌فرض ----------
    await send_main_menu(update, guid, prefix="متوجه نشدم 🙏\n")


async def send_main_menu(update, guid, prefix=""):
    if db.is_staff(guid):
        await update.reply(prefix + f"سلام {display_name(guid)} 👋", chat_keypad=kb.staff_home_keypad())
    else:
        await update.reply(prefix + f"سلام {display_name(guid)} 👋\nیکی از گزینه‌های زیر را انتخاب کنید:",
                            chat_keypad=kb.main_menu_keypad())


# ============================================================
# state های چند مرحله‌ای
# ============================================================
async def handle_state(update, guid, state, ctx, text):
    if state == "AWAIT_TICKET_REASON":
        await update.reply("⏳ در حال ساخت تیکت...")
        ticket_id = db.create_ticket(guid, text)
        db.set_state(guid, "IN_TICKET_CHAT", {"ticket_id": ticket_id})
        await update.reply(
            f"✅ یک تیکت ساخته شد\n📝 موضوع: {text}\n🎫 شماره تیکت: #{ticket_id}\n\n"
            f"تا وقتی این تیکت باز باشه هرچقدر بخواید می‌تونید همینجا پیام بدید.",
            chat_keypad=kb.in_ticket_chat_keypad()
        )
        await notify_new_ticket(ticket_id, guid, text)
        return True

    if state == "AWAIT_FAQ_QUESTION" and db.has_rank(guid, config.PERMISSION["FAQ_CREATE"]):
        db.set_state(guid, "AWAIT_FAQ_ANSWER", {"question": text})
        await update.reply("💬 جواب سوال را وارد کنید.")
        return True

    if state == "AWAIT_FAQ_ANSWER" and db.has_rank(guid, config.PERMISSION["FAQ_CREATE"]):
        ctx["answer"] = text
        db.set_state(guid, "FAQ_PREVIEW", ctx)
        await send_faq_preview(update, ctx)
        return True

    if state in ("AWAIT_FAQ_EDIT_Q",) and db.has_rank(guid, config.PERMISSION["FAQ_CREATE"]):
        ctx["question"] = text
        db.set_state(guid, "FAQ_PREVIEW", ctx)
        await send_faq_preview(update, ctx)
        return True

    if state in ("AWAIT_FAQ_EDIT_A",) and db.has_rank(guid, config.PERMISSION["FAQ_CREATE"]):
        ctx["answer"] = text
        db.set_state(guid, "FAQ_PREVIEW", ctx)
        await send_faq_preview(update, ctx)
        return True

    if state == "AWAIT_REVIEW_TEXT":
        ticket_id = ctx.get("ticket_id")
        db.set_review(ticket_id, text)
        db.clear_state(guid)
        await update.reply("🙏 از نظر شما متشکریم.")
        await broadcast_rating_update(ticket_id)
        await send_main_menu(update, guid)
        return True

    # ---------- بستن تیکت توسط Staff: نیاز به دلیل ----------
    if state == "AWAIT_CLOSE_REASON" and db.is_staff(guid):
        ticket_id = ctx.get("ticket_id")
        await finalize_staff_close(update, guid, ticket_id, close_reason=text)
        return True

    # ---------- مدیریت Staff ----------
    if state == "AWAIT_STAFF_ID" and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        target = text.strip()
        db.set_state(guid, "PICK_RANK_NEW", {"target": target})
        await update.reply(f"رنک مورد نظر برای «{target}» رو انتخاب کنید:",
                            inline_keypad=kb.rank_pick_inline_keypad(target))
        return True

    if state == "AWAIT_REMOVE_STAFF" and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        target = text.strip()
        target_rank = db.get_staff_rank(target)
        if target_rank == config.RANK_OWNER and db.get_staff_rank(guid) != config.RANK_OWNER:
            await update.reply("❌ فقط یک Owner می‌تونه Owner دیگه‌ای رو حذف کنه.")
        else:
            db.remove_staff(target)
            await update.reply(f"✅ «{target}» از لیست Staff حذف شد.")
        db.set_state(guid, None)
        rank = db.get_staff_rank(guid)
        await update.reply("👨‍💼 مدیریت Staff", chat_keypad=kb.staff_mgmt_keypad())
        return True

    if state == "AWAIT_ALERT_TEXT" and db.has_rank(guid, config.PERMISSION["BROADCAST"]):
        target = ctx.get("target")
        label = "📢 اعلان از پشتیبانی" if target == "staff" else "📢 اعلان همگانی"
        targets = db.list_staff_guids() if target == "staff" else db.list_all_user_guids()
        sent = 0
        for t in targets:
            try:
                await app.send_message(t, f"{label}\n\n{text}")
                sent += 1
            except Exception:
                pass
        await update.reply(f"✅ اعلان برای {sent} نفر ارسال شد.")
        db.set_state(guid, None)
        rank = db.get_staff_rank(guid)
        await update.reply("🛠 پنل Staff", chat_keypad=kb.staff_panel_keypad(rank))
        return True

    if state == "AWAIT_TICKET_NOTE" and db.is_staff(guid):
        ticket_id = ctx.get("ticket_id")
        db.add_ticket_note(ticket_id, guid, text)
        db.set_state(guid, "STAFF_IN_TICKET" if db.get_staff_active_ticket(guid) == ticket_id else None)
        await update.reply("📝 یادداشت ثبت شد (فقط برای Staffها قابل مشاهده‌ست).")
        return True

    if state == "STAFF_SEARCH" and db.is_staff(guid):
        db.set_state(guid, None)
        if text.isdigit():
            t = db.search_ticket_by_id(int(text))
            if t:
                await send_ticket_detail_to_staff(update, guid, t["id"])
            else:
                await update.reply("تیکتی با این شماره پیدا نشد.")
        else:
            tickets = db.search_tickets_by_user(text)
            if not tickets:
                await update.reply("تیکتی برای این کاربر پیدا نشد.")
            else:
                await update.reply("نتایج:", inline_keypad=kb.tickets_list_inline_keypad(tickets))
        return True

    # ---------- گفتگوی پیوسته‌ی Staff داخل تیکت claim‌شده ----------
    if state == "STAFF_IN_TICKET":
        ticket_id = ctx.get("ticket_id")
        t = db.get_ticket(ticket_id)
        if not t or t["status"] == config.STATUS_CLOSED:
            db.clear_state(guid)
            return False
        db.add_message(ticket_id, "staff", guid, text)
        db.staff_reply_transition(ticket_id)
        try:
            await app.send_message(t["user_guid"], f"👨‍💻 پشتیبانی:\n{text}")
        except Exception:
            pass
        return True

    return False


async def send_faq_preview(update, ctx):
    await update.reply(f"❓ سوال:\n{ctx.get('question')}\n\n💬 جواب:\n{ctx.get('answer')}",
                        inline_keypad=kb.faq_preview_inline_keypad())


# ============================================================
# تیکت‌های کاربر
# ============================================================
async def show_my_tickets_summary(update, guid):
    stats = db.get_user_ticket_stats(guid)
    text = (f"🎫 تعداد کل تیکت‌ها: {stats['total']}\n"
            f"🔴 تیکت‌های باز: {stats['open']}\n"
            f"✅ تیکت‌های بسته‌شده: {stats['closed']}")
    await update.reply(text, inline_keypad={"rows": [[{"type": "Simple", "button_id": "all_my_tickets",
                                                          "button_text": "📂 دیدن تمامی تیکت‌ها"}]]})


async def show_ticket_detail_for_user(update, guid, ticket_id):
    t = db.get_ticket(ticket_id)
    if not t or t["user_guid"] != guid:
        await update.reply("این تیکت متعلق به شما نیست یا پیدا نشد.")
        return
    messages = db.list_ticket_messages(ticket_id)
    history = "\n".join(f"[{'شما' if m['sender']=='user' else 'پشتیبانی'}] {m['text']}"
                         for m in messages) or "(پیامی ثبت نشده)"
    text = (
        f"🎫 تیکت #{t['id']}\n"
        f"وضعیت: {config.STATUS_LABELS_FA.get(t['status'], t['status'])}\n"
        f"📝 موضوع: {t['reason']}\n"
        f"📅 ساخته‌شده: {t['created_at']}\n"
        f"📅 بسته‌شده: {t['closed_at'] or '-'}\n"
        f"⭐ امتیاز: {t['rating'] or '-'}\n"
        f"📝 نظر: {t['review'] or '-'}\n\n"
        f"— تاریخچه —\n{history}"
    )
    await update.reply(text)
    if t["status"] != config.STATUS_CLOSED:
        db.set_state(guid, "IN_TICKET_CHAT", {"ticket_id": ticket_id})
        await update.reply("برای ادامه گفتگو، پیام خود را بنویسید.", chat_keypad=kb.in_ticket_chat_keypad())


async def handle_user_ticket_message(update, guid, ticket_id, text):
    t = db.get_ticket(ticket_id)
    if not t:
        db.clear_state(guid)
        await update.reply("این تیکت پیدا نشد.")
        return
    if t["status"] == config.STATUS_CLOSED:
        await update.reply("این تیکت بسته شده و امکان ارسال پیام جدید در آن وجود ندارد.")
        db.clear_state(guid)
        return

    if text == kb.BTN_CLOSE_TICKET:
        await update.reply("❓ مطمئنی می‌خوای این تیکت رو ببندی؟",
                            inline_keypad=kb.confirm_close_inline_keypad(ticket_id))
        return

    db.add_message(ticket_id, "user", guid, text)
    db.user_new_message_transition(ticket_id)

    # فقط اگر تیکت Claim شده باشه، پیام برای همون Staff می‌ره. اگه هنوز کسی
    # قبول نکرده، به بقیه‌ی Staffها اسپم نمی‌شه -- اعلان اولیه‌ی ساخت تیکت کافیه.
    if t["staff_guid"]:
        try:
            await app.send_message(
                t["staff_guid"], f"💬 پیام جدید | تیکت #{ticket_id}\n{text}",
                inline_keypad=kb.new_ticket_notification_inline_keypad(ticket_id)
            )
        except Exception:
            pass


# ============================================================
# بستن تیکت
# ============================================================
async def finalize_user_close(update, guid, ticket_id):
    user_guid, staff_guid = db.close_ticket(ticket_id, guid, close_reason=None)
    db.clear_state(guid)
    await update.reply(f"🔒 تیکت #{ticket_id} بسته شد.")
    await broadcast_closure_notice(ticket_id)
    await update.reply("⭐ لطفاً میزان رضایت خود از پشتیبانی را انتخاب کنید.",
                        inline_keypad=kb.rating_inline_keypad(ticket_id))
    await send_main_menu(update, guid)


async def finalize_staff_close(update, staff_guid, ticket_id, close_reason):
    user_guid, sid = db.close_ticket(ticket_id, staff_guid, close_reason=close_reason)
    db.clear_state(staff_guid)
    await update.reply(f"🔒 تیکت #{ticket_id} بسته شد.")
    await broadcast_closure_notice(ticket_id)
    if user_guid:
        db.clear_state(user_guid)
        try:
            await app.send_message(
                user_guid,
                f"این تیکت (#{ticket_id}) پشتیبانی بسته شد 🙏\n\n⭐ لطفاً میزان رضایت خود از پشتیبانی را انتخاب کنید.",
                inline_keypad=kb.rating_inline_keypad(ticket_id)
            )
        except Exception:
            pass


# ============================================================
# FAQ
# ============================================================
async def show_faq_list(update):
    items = db.list_faq()
    if not items:
        await update.reply("هنوز سوالی ثبت نشده است.")
        return
    await update.reply("📚 سوالات متداول:", inline_keypad=kb.faq_list_inline_keypad(items))


# ============================================================
# کال‌بک دکمه‌های شیشه‌ای
# ⚠️ TODO/VERIFY: اسم دقیق دکوراتور و ساختار داده‌ی کال‌بک رو با نسخه‌ی
# نصب‌شده‌ی rubpy چک کنید.
# ============================================================
@app.on_callback_query()  # TODO/VERIFY
async def on_callback(update):
    button_id = getattr(getattr(update, "aux_data", None), "button_id", None) or getattr(update, "button_id", "")
    guid = update.author_guid

    if button_id == "all_my_tickets":
        tickets = db.list_user_tickets(guid)
        if not tickets:
            await update.reply("هنوز تیکتی ندارید.")
            return
        await update.reply("تیکت‌های شما:", inline_keypad=kb.user_tickets_list_inline_keypad(tickets))
        return

    if m := re.match(r"^myticket_(\d+)$", button_id):
        await show_ticket_detail_for_user(update, guid, int(m.group(1)))
        return

    if m := re.match(r"^userclose_yes_(\d+)$", button_id):
        await finalize_user_close(update, guid, int(m.group(1)))
        return

    if m := re.match(r"^userclose_no_(\d+)$", button_id):
        await update.reply("باشه، به گفتگو ادامه بدید.")
        return

    if m := re.match(r"^rate_(\d+)_(\d)$", button_id):
        ticket_id, rating = int(m.group(1)), int(m.group(2))
        db.set_rating(ticket_id, rating)
        await update.reply("📝 اگر مایل هستید نظر خود را درباره پشتیبانی بنویسید.\nاین بخش اختیاری است.",
                            inline_keypad=kb.review_choice_inline_keypad(ticket_id))
        return

    if m := re.match(r"^revw_(\d+)$", button_id):
        db.set_state(guid, "AWAIT_REVIEW_TEXT", {"ticket_id": int(m.group(1))})
        await update.reply("لطفاً نظر خود را بنویسید:")
        return

    if m := re.match(r"^revs_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        db.clear_state(guid)
        await update.reply("متشکریم 🙏")
        await broadcast_rating_update(ticket_id)
        await send_main_menu(update, guid)
        return

    if button_id in ("faq_edit_q", "faq_edit_a", "faq_submit"):
        _, ctx = db.get_state(guid)
        if button_id == "faq_edit_q":
            db.set_state(guid, "AWAIT_FAQ_EDIT_Q", ctx)
            await update.reply("سوال جدید را وارد کنید.")
        elif button_id == "faq_edit_a":
            db.set_state(guid, "AWAIT_FAQ_EDIT_A", ctx)
            await update.reply("جواب جدید را وارد کنید.")
        else:
            db.create_faq(ctx.get("question"), ctx.get("answer"), guid)
            db.clear_state(guid)
            await update.reply("✅ سوال ثبت شد.")
        return

    if m := re.match(r"^faqv_(\d+)$", button_id):
        item = db.get_faq(int(m.group(1)))
        if item:
            await update.reply(f"❓ {item['question']}\n\n💬 {item['answer']}")
        return

    if db.is_staff(guid):
        await handle_staff_callback(update, guid, button_id)


# ============================================================
# متن‌های پنل Staff
# ============================================================
async def handle_staff_panel_text(update, guid, text):
    rank = db.get_staff_rank(guid)

    if text == kb.BTN_MANAGE:
        counts = {key: db.count_tickets_by_filter(key, staff_guid=guid) for _, key in kb.TICKET_FILTER_BUTTONS}
        await update.reply("🎫 مدیریت تیکت‌ها:", chat_keypad=kb.ticket_management_keypad(counts))
        return True

    for label, key in kb.TICKET_FILTER_BUTTONS:
        if text.startswith(label):
            tickets = db.list_tickets_by_filter(key, staff_guid=guid)
            if not tickets:
                await update.reply("موردی یافت نشد.")
            else:
                await update.reply(f"{label}:", inline_keypad=kb.tickets_list_inline_keypad(tickets))
            return True

    if text == kb.BTN_MINE:
        tickets = db.list_tickets_by_filter("mine", staff_guid=guid)
        if not tickets:
            await update.reply("در حال حاضر تیکتی به شما اختصاص داده نشده.")
        else:
            await update.reply("👤 تیکت‌های من:", inline_keypad=kb.tickets_list_inline_keypad(tickets))
        return True

    if text == kb.BTN_STATS_ME:
        s = db.get_staff_stats(guid)
        await update.reply(
            f"🎫 کل تیکت‌های دریافت‌شده: {s['total_assigned']}\n"
            f"✅ بسته‌شده: {s['closed']}\n🔴 باز: {s['open']}\n"
            f"⭐ میانگین امتیاز: {s['avg_rating'] or '-'}\n📝 تعداد نظرات: {s['review_count']}"
        )
        return True

    if text == kb.BTN_UNANSWERED:
        tickets = db.list_tickets_by_filter("no_response", staff_guid=guid)
        if not tickets:
            await update.reply("همه تیکت‌ها پاسخ داده شده‌اند 👌")
        else:
            await update.reply("🚨 تیکت‌های بدون پاسخ:", inline_keypad=kb.tickets_list_inline_keypad(tickets))
        return True

    if text == kb.BTN_STALE:
        stale = db.get_stale_tickets(config.STALE_THRESHOLD_MINUTES)
        if not stale:
            await update.reply("تیکت معطلی وجود ندارد 👌")
        else:
            lines = [f"🎫 #{t['id']}\n⏳ بدون پاسخ: {t['waited_minutes']} دقیقه" for t in stale]
            await update.reply("⏰ تیکت‌های معطل:\n\n" + "\n\n".join(lines))
        return True

    if text == kb.BTN_SEARCH:
        db.set_state(guid, "STAFF_SEARCH")
        await update.reply("شماره تیکت یا شناسه‌ی کاربر را وارد کنید:")
        return True

    if text == kb.BTN_STATS_SYS and db.has_rank(guid, config.PERMISSION["SYSTEM_STATS"]):
        s = db.get_system_stats()
        await update.reply(
            f"👥 کاربران: {s['users']}\n🎫 کل تیکت‌ها: {s['total_tickets']}\n"
            f"🔴 باز: {s['open_tickets']}\n🔒 بسته: {s['closed_tickets']}\n"
            f"⭐ میانگین امتیاز: {s['avg_rating'] or '-'}\n👨‍💼 Staffها: {s['staff_count']}"
        )
        return True

    if text == kb.BTN_ALERT and db.has_rank(guid, config.PERMISSION["BROADCAST"]):
        db.set_state(guid, "STAFF_ALERT_MENU")
        await update.reply("اعلان رو برای کی می‌خواید بفرستید؟", chat_keypad=kb.alert_menu_keypad())
        return True

    if text == kb.BTN_ALERT_STAFF:
        db.set_state(guid, "AWAIT_ALERT_TEXT", {"target": "staff"})
        await update.reply("متن اعلان برای همه Staffها رو بنویسید:")
        return True

    if text == kb.BTN_ALERT_USERS:
        db.set_state(guid, "AWAIT_ALERT_TEXT", {"target": "users"})
        await update.reply("متن اعلان همگانی برای کاربران رو بنویسید:")
        return True

    if text == kb.BTN_STAFF_MGMT and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        db.set_state(guid, None)
        await update.reply("👨‍💼 مدیریت Staff:", chat_keypad=kb.staff_mgmt_keypad())
        return True

    if text == kb.BTN_ADD_STAFF and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        db.set_state(guid, "AWAIT_STAFF_ID")
        await update.reply("آیدی Staff جدید رو با @ بنویسید (مثلاً @AmirSetfin_YT):")
        return True

    if text == kb.BTN_CHANGE_RANK and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        staff_guids = db.list_staff_guids()
        if not staff_guids:
            await update.reply("هنوز Staffای ثبت نشده.")
            return True
        await update.reply("رنک کدوم Staff رو می‌خواید تغییر بدید؟",
                            inline_keypad=kb.staff_pick_inline_keypad(staff_guids, display_name))
        return True

    if text == kb.BTN_REMOVE_STAFF and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        db.set_state(guid, "AWAIT_REMOVE_STAFF")
        await update.reply("آیدی Staffی که می‌خواید حذف کنید رو بنویسید:")
        return True

    if text == kb.BTN_LIST_STAFF and db.has_rank(guid, config.PERMISSION["STAFF_MANAGE"]):
        rows = db.list_staff()
        lines = []
        for s in rows:
            lock = db.get_staff_active_ticket(s["user_guid"])
            lines.append(f"{display_name(s['user_guid'])} ({s['user_guid']}) — "
                         f"{config.RANK_LABELS_FA.get(s['role'], s['role'])} — "
                         f"{'🔒 مشغول #' + str(lock) if lock else '🟢 آزاد'}")
        await update.reply("\n".join(lines) or "Staffای ثبت نشده.")
        return True

    if text == kb.BTN_BACK:
        await update.reply("🛠 پنل Staff", chat_keypad=kb.staff_panel_keypad(rank))
        return True

    if text == kb.BTN_CLOSE_TICKET:
        state, ctx = db.get_state(guid)
        if state == "STAFF_IN_TICKET":
            ticket_id = ctx.get("ticket_id")
            db.set_state(guid, "AWAIT_CLOSE_REASON", {"ticket_id": ticket_id})
            await update.reply("📝 لطفاً موضوع/دلیل بستن این تیکت رو بنویسید:")
            return True

    return False


async def send_ticket_detail_to_staff(update, staff_guid, ticket_id):
    t = db.get_ticket(ticket_id)
    if not t:
        await update.reply("تیکت پیدا نشد.")
        return
    messages = db.list_ticket_messages(ticket_id)
    history = "\n".join(f"[{'کاربر' if m['sender']=='user' else 'Staff'}] {m['text']}"
                         for m in messages) or "(پیامی ثبت نشده)"
    is_owner = t["staff_guid"] == staff_guid
    text = (
        f"🎫 تیکت #{t['id']}\n"
        f"وضعیت: {config.STATUS_LABELS_FA.get(t['status'], t['status'])}\n"
        f"👤 کاربر: {display_name(t['user_guid'])}\n"
        f"👨‍💼 Staff: {display_name(t['staff_guid']) if t['staff_guid'] else '-'}\n"
        f"📝 موضوع: {t['reason']}\n\n— پیام‌ها —\n{history}"
    )
    await update.reply(text, inline_keypad=kb.ticket_action_inline_keypad(ticket_id, is_owner))


# ============================================================
# کال‌بک‌های پنل Staff روی هر تیکت
# ============================================================
async def handle_staff_callback(update, guid, button_id):
    if m := re.match(r"^view_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        db.mark_seen_if_needed(ticket_id)
        t = db.get_ticket(ticket_id)
        await send_ticket_detail_to_staff(update, guid, ticket_id)
        if t and t["staff_guid"] == guid and t["status"] != config.STATUS_CLOSED:
            db.set_state(guid, "STAFF_IN_TICKET", {"ticket_id": ticket_id})
            await update.reply("هرچی بنویسید مستقیم برای کاربر می‌ره.", chat_keypad=kb.staff_in_ticket_keypad())
        return

    if m := re.match(r"^claim_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        active = db.get_staff_active_ticket(guid)
        if active and active != ticket_id:
            await update.reply(
                f"⚠️ شما در حال حاضر در حال پاسخ‌گویی به تیکت #{active} هستید.\nلطفاً ابتدا این تیکت را تعیین تکلیف کنید.",
                inline_keypad=kb.busy_staff_inline_keypad(active)
            )
            return
        ok, reason = db.claim_ticket(guid, ticket_id)
        if not ok:
            await update.reply(f"❌ امکان دریافت تیکت وجود ندارد ({reason}).")
            return
        db.set_state(guid, "STAFF_IN_TICKET", {"ticket_id": ticket_id})
        await update.reply(f"✅ تیکت #{ticket_id} به شما اختصاص یافت. هرچی بنویسید برای کاربر ارسال می‌شه.",
                            chat_keypad=kb.staff_in_ticket_keypad())
        await send_ticket_detail_to_staff(update, guid, ticket_id)
        return

    if m := re.match(r"^close_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        db.set_state(guid, "AWAIT_CLOSE_REASON", {"ticket_id": ticket_id})
        await update.reply("📝 لطفاً موضوع/دلیل بستن این تیکت رو بنویسید:")
        return

    if m := re.match(r"^transfer_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        others = [g for g in db.list_staff_guids() if g != guid]
        if not others:
            await update.reply("Staff دیگه‌ای برای انتقال وجود نداره.")
            return
        rows = [[{"type": "Simple", "button_id": f"doT_{ticket_id}_{g}", "button_text": f"➡️ {display_name(g)}"}]
                for g in others]
        await update.reply("مقصد را انتخاب کنید:", inline_keypad={"rows": rows})
        return

    if m := re.match(r"^doT_(\d+)_(.+)$", button_id):
        ticket_id, target = int(m.group(1)), m.group(2)
        ok, reason = db.transfer_ticket(ticket_id, guid, target)
        if ok:
            db.clear_state(guid)
            await update.reply(f"✅ تیکت #{ticket_id} منتقل شد.")
            try:
                await app.send_message(target, f"🔄 تیکت #{ticket_id} به شما منتقل شد.",
                                        inline_keypad=kb.new_ticket_notification_inline_keypad(ticket_id))
            except Exception:
                pass
        else:
            await update.reply(f"❌ انتقال ممکن نشد ({reason}).")
        return

    if m := re.match(r"^note_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        db.set_state(guid, "AWAIT_TICKET_NOTE", {"ticket_id": ticket_id})
        await update.reply("یادداشت داخلی خودتون رو بنویسید (فقط Staffها می‌بینن):")
        return

    if m := re.match(r"^uinfo_(\d+)$", button_id):
        t = db.get_ticket(int(m.group(1)))
        if t:
            info = db.get_user_info(t["user_guid"])
            await update.reply(
                f"👤 نام: {info['display_name'] or '-'}\n"
                f"🆔 شناسه: {info['user_guid']}\n"
                f"🎫 کل تیکت‌ها: {info['total_tickets']}\n"
                f"🔴 باز: {info['open_tickets']}\n✅ بسته: {info['closed_tickets']}\n"
                f"📅 اولین تیکت: {info['first_ticket_at'] or '-'}"
            )
        return

    if m := re.match(r"^hist_(\d+)$", button_id):
        ticket_id = int(m.group(1))
        activity = db.get_ticket_activity(ticket_id)
        notes = db.list_ticket_notes(ticket_id)
        lines = [f"{a['created_at']} — {a['event']} {a['detail'] or ''}" for a in activity]
        note_lines = [f"📝 {display_name(n['staff_guid'])}: {n['note']}" for n in notes]
        text = "📜 تاریخچه فعالیت:\n" + ("\n".join(lines) or "-")
        if note_lines:
            text += "\n\n— یادداشت‌های داخلی —\n" + "\n".join(note_lines)
        await update.reply(text)
        return

    if m := re.match(r"^pickrank_(.+)$", button_id):
        target = m.group(1)
        await update.reply(f"رنک جدید برای «{target}» رو انتخاب کنید:",
                            inline_keypad=kb.rank_pick_inline_keypad(target))
        return

    if m := re.match(rf"^setrank_(.+)_({'|'.join(config.RANK_LEVEL.keys())})$", button_id):
        target, new_rank = m.group(1), m.group(2)
        current_rank = db.get_staff_rank(target)
        if current_rank == config.RANK_OWNER and db.get_staff_rank(guid) != config.RANK_OWNER:
            await update.reply("❌ فقط یک Owner می‌تونه رنک Owner دیگه‌ای رو تغییر بده.")
            return
        db.set_rank(target, new_rank, set_by=guid)
        await update.reply(f"✅ رنک «{target}» روی {config.RANK_LABELS_FA[new_rank]} تنظیم شد.")
        db.set_state(guid, None)
        return


# ============================================================
# اجرا
# ============================================================
async def main():
    db.init_db()
    async with app:
        print("بات با موفقیت اجرا شد و منتظر پیام‌هاست...")
        await app.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
