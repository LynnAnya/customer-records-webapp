"""Thai text for the activity log page. The database keeps English codes."""

from datetime import datetime

from django.utils import timezone
from django.utils.formats import date_format

from audit.models import ActivityLog

Action = ActivityLog.Action

ACTION_LABELS: dict[str, str] = {
    Action.LOGIN: "เข้าสู่ระบบ",
    Action.LOGIN_FAILED: "เข้าสู่ระบบไม่สำเร็จ",
    Action.CUSTOMER_CREATE: "เพิ่มลูกค้า",
    Action.CUSTOMER_EDIT: "แก้ไขลูกค้า",
    Action.CUSTOMER_DELETE: "ลบลูกค้า",
    Action.CUSTOMER_HIDE: "ซ่อนลูกค้า",
    Action.CUSTOMER_UNHIDE: "ยกเลิกการซ่อนลูกค้า",
    Action.COPY: "คัดลอกข้อมูล",
    Action.SHARE: "แชร์ข้อมูล",
    Action.PDF_EXPORT: "ส่งออก PDF",
    Action.STAFF_CREATED: "เพิ่มพนักงาน",
    Action.STAFF_PASSWORD_RESET: "รีเซ็ตรหัสผ่านพนักงาน",
    Action.STAFF_DEACTIVATED: "ปิดใช้งานพนักงาน",
    Action.STAFF_REACTIVATED: "เปิดใช้งานพนักงาน",
    Action.PASSWORD_CHANGED: "เปลี่ยนรหัสผ่าน",
    Action.EXCEL_IMPORT: "นำเข้าจาก Excel",
    Action.STAFF_EDITED: "แก้ไขข้อมูลพนักงาน",
    Action.LOG_EXPORTED: "ดาวน์โหลดบันทึกกิจกรรม",
    Action.LOG_ARCHIVED: "เก็บถาวรบันทึกกิจกรรม",
}

# Actions shown in red: worth a second look.
ALERT_ACTIONS = frozenset({Action.LOGIN_FAILED, Action.CUSTOMER_DELETE})

MAX_NAMES_SHOWN = 5


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def describe_details(details: dict) -> str:
    """One readable line from a log row's details, for example
    'สมชาย ใจดี, มานี มีนา (2 ราย)'. Empty when there is nothing to say."""
    parts: list[str] = []
    names = details.get("customer_names") or []
    count = details.get("count") or len(names)
    if names:
        shown = ", ".join(str(name) for name in names[:MAX_NAMES_SHOWN])
        if count > MAX_NAMES_SHOWN:
            shown += f" และอีก {count - MAX_NAMES_SHOWN} ราย"
        parts.append(shown)
    if count > 1 or (count and not names):
        parts.append(f"({count} ราย)")
    if details.get("previous_username"):
        parts.append(
            f"บัญชี {details['previous_username']} → {details['target_username']}"
        )
    elif details.get("target_username"):
        parts.append(f"บัญชี {details['target_username']}")
    return " ".join(parts)


def time_ago(moment: datetime, now: datetime | None = None) -> str:
    """Relative time in Thai, for example '2 นาทีที่แล้ว'.

    Written by hand because Django's Thai translation has no text for this.
    After 30 days the plain date is clearer than a large number of days.
    """
    seconds = int(((now or timezone.now()) - moment).total_seconds())
    if seconds < 60:
        return "เมื่อสักครู่"
    if seconds < 3600:
        return f"{seconds // 60} นาทีที่แล้ว"
    if seconds < 86400:
        return f"{seconds // 3600} ชั่วโมงที่แล้ว"
    if seconds < 30 * 86400:
        return f"{seconds // 86400} วันที่แล้ว"
    return date_format(timezone.localtime(moment), "j M Y")
