# -*- coding: utf-8 -*-
"""
لایه دیتابیس.
مهاجرت بدون حذف داده: اگه از نسخه‌ی قبلی آپگرید می‌کنید (چه نسخه‌ی خیلی اول با
جداول ساده، چه نسخه‌ی دوم با staff/role قدیمی)، این فایل ستون‌های جدید رو اضافه
می‌کنه و رنک‌های قدیمی (STAFF/SENIOR_STAFF/ADMIN) رو به رنک‌های جدید نگاشت می‌کنه.
"""

import sqlite3
import json
from datetime import datetime, timedelta

from config import (
    DB_PATH, INITIAL_OWNER_IDS,
    RANK_HELPER, RANK_MOD, RANK_ADMIN, RANK_MANAGER, RANK_OWNER, RANK_LEVEL,
    STATUS_NEW, STATUS_CLOSED,
)

# نگاشت رنک‌های نسخه‌ی قبلی (در صورت وجود) به سیستم رنک جدید -- برای مهاجرت امن
_LEGACY_ROLE_MAP = {
    "STAFF": RANK_HELPER,
    "SENIOR_STAFF": RANK_MOD,
    "ADMIN": RANK_MANAGER,
}


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso():
    return datetime.utcnow().isoformat()


def _column_exists(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cur.fetchall())


def _add_column_if_missing(conn, table, column, coltype):
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


# ============================================================
# ساخت / مهاجرت جداول
# ============================================================
def init_db():
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_guid TEXT PRIMARY KEY,
                display_name TEXT,
                first_seen TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS staff (
                user_guid TEXT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'HELPER',
                active INTEGER NOT NULL DEFAULT 1,
                added_at TEXT
            )
        """)
        # مهاجرت رنک‌های قدیمی به رنک‌های جدید (اگر وجود داشته باشن)
        for old, new in _LEGACY_ROLE_MAP.items():
            conn.execute("UPDATE staff SET role=? WHERE role=?", (new, old))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_guid TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'NEW',
                created_at TEXT
            )
        """)
        _add_column_if_missing(conn, "tickets", "staff_guid", "TEXT")
        _add_column_if_missing(conn, "tickets", "reason", "TEXT")
        _add_column_if_missing(conn, "tickets", "closed_at", "TEXT")
        _add_column_if_missing(conn, "tickets", "closed_by", "TEXT")
        _add_column_if_missing(conn, "tickets", "close_reason", "TEXT")
        _add_column_if_missing(conn, "tickets", "seen_at", "TEXT")
        _add_column_if_missing(conn, "tickets", "rating", "INTEGER")
        _add_column_if_missing(conn, "tickets", "review", "TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender TEXT,
                text TEXT,
                created_at TEXT
            )
        """)
        _add_column_if_missing(conn, "messages", "sender_guid", "TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                event TEXT,
                detail TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                answer TEXT,
                created_by TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                user_guid TEXT PRIMARY KEY,
                active_ticket_id INTEGER,
                state TEXT,
                context TEXT
            )
        """)
        _add_column_if_missing(conn, "user_state", "state", "TEXT")
        _add_column_if_missing(conn, "user_state", "context", "TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS staff_lock (
                staff_guid TEXT PRIMARY KEY,
                ticket_id INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                staff_guid TEXT,
                note TEXT,
                created_at TEXT
            )
        """)

        conn.commit()
    finally:
        conn.close()

    _ensure_initial_owners()


def _ensure_initial_owners():
    conn = get_conn()
    try:
        for uid in INITIAL_OWNER_IDS:
            if not uid or "YOUR_OWNER_ID_HERE" in uid:
                continue
            conn.execute("""
                INSERT INTO staff (user_guid, role, active, added_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_guid) DO UPDATE SET role=excluded.role, active=1
            """, (uid, RANK_OWNER, now_iso()))
        conn.commit()
    finally:
        conn.close()


# ============================================================
# کاربران عادی
# ============================================================
def ensure_user(user_guid, display_name=None):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO users (user_guid, display_name, first_seen)
            VALUES (?, ?, ?)
            ON CONFLICT(user_guid) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, users.display_name)
        """, (user_guid, display_name, now_iso()))
        conn.commit()
    finally:
        conn.close()


def list_all_user_guids():
    """برای اعلان همگانی: همه‌ی کسانی که حداقل یک‌بار با بات تعامل داشتن."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT user_guid FROM users").fetchall()
        return [r["user_guid"] for r in rows]
    finally:
        conn.close()


def get_user_ticket_stats(user_guid):
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM tickets WHERE user_guid=?", (user_guid,)).fetchone()["c"]
        closed = conn.execute("SELECT COUNT(*) c FROM tickets WHERE user_guid=? AND status='CLOSED'",
                               (user_guid,)).fetchone()["c"]
        return {"total": total, "open": total - closed, "closed": closed}
    finally:
        conn.close()


def get_user_info(user_guid):
    conn = get_conn()
    try:
        user = conn.execute("SELECT * FROM users WHERE user_guid=?", (user_guid,)).fetchone()
        stats = get_user_ticket_stats(user_guid)
        first_ticket = conn.execute(
            "SELECT MIN(created_at) t FROM tickets WHERE user_guid=?", (user_guid,)
        ).fetchone()["t"]
        return {
            "user_guid": user_guid,
            "display_name": user["display_name"] if user else None,
            "total_tickets": stats["total"],
            "open_tickets": stats["open"],
            "closed_tickets": stats["closed"],
            "first_ticket_at": first_ticket,
        }
    finally:
        conn.close()


# ============================================================
# Staff / رنک‌ها
# ============================================================
def get_staff_rank(user_guid):
    conn = get_conn()
    try:
        row = conn.execute("SELECT role, active FROM staff WHERE user_guid=?", (user_guid,)).fetchone()
        if row and row["active"]:
            return row["role"]
        return None
    finally:
        conn.close()


def is_staff(user_guid):
    return get_staff_rank(user_guid) is not None


def has_rank(user_guid, min_rank):
    rank = get_staff_rank(user_guid)
    if not rank:
        return False
    return RANK_LEVEL.get(rank, 0) >= RANK_LEVEL.get(min_rank, 999)


def set_rank(user_guid, rank, set_by=None):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO staff (user_guid, role, active, added_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_guid) DO UPDATE SET role=excluded.role, active=1
        """, (user_guid, rank, now_iso()))
        conn.commit()
    finally:
        conn.close()


def remove_staff(user_guid):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM staff WHERE user_guid=?", (user_guid,))
        conn.execute("DELETE FROM staff_lock WHERE staff_guid=?", (user_guid,))
        conn.commit()
    finally:
        conn.close()


def list_staff():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM staff WHERE active=1 ORDER BY added_at").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_staff_guids():
    return [s["user_guid"] for s in list_staff()]


# ============================================================
# FSM ساده
# ============================================================
def get_state(user_guid):
    conn = get_conn()
    try:
        row = conn.execute("SELECT state, context FROM user_state WHERE user_guid=?", (user_guid,)).fetchone()
        if not row:
            return None, {}
        ctx = json.loads(row["context"]) if row["context"] else {}
        return row["state"], ctx
    finally:
        conn.close()


def set_state(user_guid, state, context=None):
    conn = get_conn()
    try:
        ctx_json = json.dumps(context or {}, ensure_ascii=False)
        conn.execute("""
            INSERT INTO user_state (user_guid, state, context)
            VALUES (?, ?, ?)
            ON CONFLICT(user_guid) DO UPDATE SET state=excluded.state, context=excluded.context
        """, (user_guid, state, ctx_json))
        conn.commit()
    finally:
        conn.close()


def clear_state(user_guid):
    set_state(user_guid, None, {})


# ============================================================
# تیکت‌ها
# ============================================================
def create_ticket(user_guid, reason):
    conn = get_conn()
    try:
        now = now_iso()
        cur = conn.execute("""
            INSERT INTO tickets (user_guid, status, created_at, reason)
            VALUES (?, ?, ?, ?)
        """, (user_guid, STATUS_NEW, now, reason))
        ticket_id = cur.lastrowid
        conn.commit()
        _log_activity(conn, ticket_id, "CREATED", f"reason={reason}")
        return ticket_id
    finally:
        conn.close()


def get_open_ticket_for_user(user_guid):
    """برای جلوگیری از ساخت تیکت تکراری: اگه یک تیکت باز داره برش گردون."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM tickets WHERE user_guid=? AND status != 'CLOSED' ORDER BY id DESC LIMIT 1",
            (user_guid,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_ticket(ticket_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_user_tickets(user_guid):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE user_guid=? ORDER BY id DESC", (user_guid,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_message(ticket_id, sender_type, sender_guid, text):
    conn = get_conn()
    try:
        now = now_iso()
        conn.execute("""
            INSERT INTO messages (ticket_id, sender, sender_guid, text, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (ticket_id, sender_type, sender_guid, text, now))
        conn.commit()
        _log_activity(conn, ticket_id, "USER_MSG" if sender_type == "user" else "STAFF_MSG")
    finally:
        conn.close()


def list_ticket_messages(ticket_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE ticket_id=? ORDER BY id", (ticket_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_seen_if_needed(ticket_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT seen_at FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if row and not row["seen_at"]:
            conn.execute("UPDATE tickets SET seen_at=? WHERE id=?", (now_iso(), ticket_id))
            conn.commit()
    finally:
        conn.close()


def user_new_message_transition(ticket_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT staff_guid FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not row:
            return
        new_status = STATUS_IN_PROGRESS if row["staff_guid"] else STATUS_WAITING_STAFF
        conn.execute("UPDATE tickets SET status=? WHERE id=?", (new_status, ticket_id))
        conn.commit()
        _log_activity(conn, ticket_id, "STATUS_CHANGE", new_status)
    finally:
        conn.close()


def staff_reply_transition(ticket_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE tickets SET status=? WHERE id=?", ("WAITING_USER", ticket_id))
        conn.commit()
        _log_activity(conn, ticket_id, "STATUS_CHANGE", "WAITING_USER")
    finally:
        conn.close()


def close_ticket(ticket_id, closed_by_guid, close_reason=None):
    """
    بستن تیکت -- توسط کاربر (بدون نیاز به دلیل) یا Staff (با دلیل اجباری).
    خروجی: (user_guid, staff_guid) صاحبان تیکت، برای اطلاع‌رسانی.
    """
    conn = get_conn()
    try:
        row = conn.execute("SELECT user_guid, staff_guid FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not row:
            return None, None
        conn.execute("UPDATE tickets SET status=?, closed_at=?, closed_by=?, close_reason=? WHERE id=?",
                     (STATUS_CLOSED, now_iso(), closed_by_guid, close_reason, ticket_id))
        if row["staff_guid"]:
            conn.execute("DELETE FROM staff_lock WHERE staff_guid=? AND ticket_id=?",
                         (row["staff_guid"], ticket_id))
        conn.commit()
        _log_activity(conn, ticket_id, "CLOSED", f"by={closed_by_guid} reason={close_reason}")
        return row["user_guid"], row["staff_guid"]
    finally:
        conn.close()


def set_display_name(user_guid, name):
    ensure_user(user_guid, display_name=name)


def add_ticket_note(ticket_id, staff_guid, note):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO ticket_notes (ticket_id, staff_guid, note, created_at) VALUES (?, ?, ?, ?)
        """, (ticket_id, staff_guid, note, now_iso()))
        conn.commit()
    finally:
        conn.close()


def list_ticket_notes(ticket_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM ticket_notes WHERE ticket_id=? ORDER BY id", (ticket_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_rating(ticket_id, rating):
    conn = get_conn()
    try:
        conn.execute("UPDATE tickets SET rating=? WHERE id=?", (rating, ticket_id))
        conn.commit()
        _log_activity(conn, ticket_id, "RATED", str(rating))
    finally:
        conn.close()


def set_review(ticket_id, review):
    conn = get_conn()
    try:
        conn.execute("UPDATE tickets SET review=? WHERE id=?", (review, ticket_id))
        conn.commit()
        _log_activity(conn, ticket_id, "REVIEWED")
    finally:
        conn.close()


# ---------------- قفل Staff / Claim / Transfer (اتمیک) ----------------
def get_staff_active_ticket(staff_guid):
    conn = get_conn()
    try:
        row = conn.execute("SELECT ticket_id FROM staff_lock WHERE staff_guid=?", (staff_guid,)).fetchone()
        return row["ticket_id"] if row else None
    finally:
        conn.close()


def claim_ticket(staff_guid, ticket_id):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        my_lock = conn.execute("SELECT ticket_id FROM staff_lock WHERE staff_guid=?",
                                (staff_guid,)).fetchone()
        if my_lock and my_lock["ticket_id"] != ticket_id:
            conn.execute("ROLLBACK")
            return False, f"already_locked:{my_lock['ticket_id']}"

        t = conn.execute("SELECT staff_guid, status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not t:
            conn.execute("ROLLBACK")
            return False, "not_found"
        if t["status"] == STATUS_CLOSED:
            conn.execute("ROLLBACK")
            return False, "closed"
        if t["staff_guid"] and t["staff_guid"] != staff_guid:
            conn.execute("ROLLBACK")
            return False, "already_assigned"

        now = now_iso()
        conn.execute("""
            UPDATE tickets SET staff_guid=?, status=?, seen_at=COALESCE(seen_at, ?)
            WHERE id=?
        """, (staff_guid, STATUS_IN_PROGRESS, now, ticket_id))
        conn.execute("""
            INSERT INTO staff_lock (staff_guid, ticket_id) VALUES (?, ?)
            ON CONFLICT(staff_guid) DO UPDATE SET ticket_id=excluded.ticket_id
        """, (staff_guid, ticket_id))
        conn.execute("COMMIT")
        _log_activity_standalone(ticket_id, "ASSIGNED", staff_guid)
        return True, None
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def transfer_ticket(ticket_id, from_staff, to_staff):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        t = conn.execute("SELECT staff_guid, status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not t or t["staff_guid"] != from_staff:
            conn.execute("ROLLBACK")
            return False, "not_owner"
        if t["status"] == STATUS_CLOSED:
            conn.execute("ROLLBACK")
            return False, "closed"
        target_lock = conn.execute("SELECT ticket_id FROM staff_lock WHERE staff_guid=?",
                                    (to_staff,)).fetchone()
        if target_lock and target_lock["ticket_id"] != ticket_id:
            conn.execute("ROLLBACK")
            return False, f"target_busy:{target_lock['ticket_id']}"

        conn.execute("DELETE FROM staff_lock WHERE staff_guid=?", (from_staff,))
        conn.execute("UPDATE tickets SET staff_guid=? WHERE id=?", (to_staff, ticket_id))
        conn.execute("""
            INSERT INTO staff_lock (staff_guid, ticket_id) VALUES (?, ?)
            ON CONFLICT(staff_guid) DO UPDATE SET ticket_id=excluded.ticket_id
        """, (to_staff, ticket_id))
        conn.execute("COMMIT")
        _log_activity_standalone(ticket_id, "TRANSFERRED", f"{from_staff} -> {to_staff}")
        return True, None
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


# ---------------- فیلترهای پنل Staff ----------------
def list_tickets_by_filter(filter_name, staff_guid=None, limit=30):
    conn = get_conn()
    try:
        base = "SELECT * FROM tickets"
        where = []
        params = []

        if filter_name == "new":
            where.append("status='NEW'")
        elif filter_name == "waiting_staff":
            where.append("status='WAITING_STAFF'")
        elif filter_name == "in_progress":
            where.append("status='IN_PROGRESS'")
        elif filter_name == "waiting_user":
            where.append("status='WAITING_USER'")
        elif filter_name == "no_response":
            base = """
                SELECT t.* FROM tickets t
                WHERE t.status != 'CLOSED' AND (
                    SELECT m.sender FROM messages m WHERE m.ticket_id = t.id
                    ORDER BY m.id DESC LIMIT 1
                ) IS NOT 'staff'
            """
        elif filter_name == "open":
            where.append("status != 'CLOSED'")
        elif filter_name == "closed":
            where.append("status='CLOSED'")
        elif filter_name == "mine" and staff_guid:
            where.append("staff_guid=? AND status != 'CLOSED'")
            params.append(staff_guid)
        elif filter_name == "all":
            pass

        if where and "no_response" not in filter_name:
            base += " WHERE " + " AND ".join(where)
        base += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(base, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_tickets_by_filter(filter_name, staff_guid=None):
    return len(list_tickets_by_filter(filter_name, staff_guid=staff_guid, limit=100000))


def get_stale_tickets(threshold_minutes):
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM tickets WHERE status IN ('WAITING_STAFF', 'WAITING_USER') ORDER BY id
        """).fetchall()
        cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)
        stale = []
        for r in rows:
            last = conn.execute(
                "SELECT created_at FROM messages WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (r["id"],)
            ).fetchone()
            last_time_str = last["created_at"] if last else r["created_at"]
            try:
                last_time = datetime.fromisoformat(last_time_str)
            except Exception:
                continue
            if last_time <= cutoff:
                d = dict(r)
                d["waited_minutes"] = int((datetime.utcnow() - last_time).total_seconds() // 60)
                stale.append(d)
        return stale
    finally:
        conn.close()


def search_ticket_by_id(ticket_id):
    return get_ticket(ticket_id)


def search_tickets_by_user(user_guid):
    return list_user_tickets(user_guid)


# ============================================================
# FAQ
# ============================================================
def create_faq(question, answer, created_by):
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO faq (question, answer, created_by, created_at)
            VALUES (?, ?, ?, ?)
        """, (question, answer, created_by, now_iso()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_faq():
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM faq ORDER BY id").fetchall()]
    finally:
        conn.close()


def get_faq(faq_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM faq WHERE id=?", (faq_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ============================================================
# لاگ فعالیت
# ============================================================
def _log_activity(conn, ticket_id, event, detail=""):
    conn.execute("""
        INSERT INTO ticket_activity (ticket_id, event, detail, created_at) VALUES (?, ?, ?, ?)
    """, (ticket_id, event, detail, now_iso()))
    conn.commit()


def _log_activity_standalone(ticket_id, event, detail=""):
    conn = get_conn()
    try:
        _log_activity(conn, ticket_id, event, detail)
    finally:
        conn.close()


def get_ticket_activity(ticket_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM ticket_activity WHERE ticket_id=? ORDER BY id", (ticket_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ============================================================
# آمار
# ============================================================
def get_staff_stats(staff_guid):
    conn = get_conn()
    try:
        total_assigned = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE staff_guid=?", (staff_guid,)
        ).fetchone()["c"]
        closed = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE staff_guid=? AND status='CLOSED'", (staff_guid,)
        ).fetchone()["c"]
        avg_rating = conn.execute(
            "SELECT AVG(rating) a FROM tickets WHERE staff_guid=? AND rating IS NOT NULL", (staff_guid,)
        ).fetchone()["a"]
        review_count = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE staff_guid=? AND review IS NOT NULL AND review != ''",
            (staff_guid,)
        ).fetchone()["c"]
        return {
            "total_assigned": total_assigned,
            "closed": closed,
            "open": total_assigned - closed,
            "avg_rating": round(avg_rating, 2) if avg_rating else None,
            "review_count": review_count,
        }
    finally:
        conn.close()


def get_system_stats():
    conn = get_conn()
    try:
        users_count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_tickets = conn.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
        open_tickets = conn.execute("SELECT COUNT(*) c FROM tickets WHERE status!='CLOSED'").fetchone()["c"]
        avg_rating = conn.execute("SELECT AVG(rating) a FROM tickets WHERE rating IS NOT NULL").fetchone()["a"]
        staff_count = len(list_staff())
        return {
            "users": users_count,
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "closed_tickets": total_tickets - open_tickets,
            "avg_rating": round(avg_rating, 2) if avg_rating else None,
            "staff_count": staff_count,
        }
    finally:
        conn.close()
