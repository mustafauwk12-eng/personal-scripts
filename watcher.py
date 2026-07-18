#!/usr/bin/env python3
"""
مراقب مشاريع مستقل (Mostaql) - يبعت إشعار على تلجرام أول ما ينزل مشروع جديد
"""

import os
import re
import sys
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

# ============ الإعدادات ============
PROJECTS_URL = "https://mostaql.com/projects"   # ممكن تغيرها لقسم معين، مثال:
# PROJECTS_URL = "https://mostaql.com/projects/support"   # دعم ومساعدة وإدخال بيانات
# PROJECTS_URL = "https://mostaql.com/projects/development"  # برمجة وتطوير

SEEN_FILE = "seen_ids.txt"
MAX_STORED_IDS = 1000  # عشان الملف ميكبرش من غير داعي

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch_projects(url: str):
    """يجيب المشاريع المفتوحة من صفحة مستقل، ويرجعهم بترتيب النزول (الأحدث الأول)."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    grouped = defaultdict(list)  # project_id -> [(نص الرابط, الرابط الكامل), ...]
    project_pattern = re.compile(r"^(?:https?://mostaql\.com)?/project/(\d+)-")

    for a in soup.find_all("a", href=True):
        match = project_pattern.match(a["href"])
        if not match:
            continue
        project_id = match.group(1)
        text = a.get_text(strip=True)
        href = a["href"]
        if href.startswith("/"):
            href = "https://mostaql.com" + href
        if text:
            grouped[project_id].append((text, href))

    projects = []
    for project_id, entries in grouped.items():
        # أقصر نص مرتبط بنفس المشروع غالباً بيكون العنوان (مش الوصف الطويل)
        entries.sort(key=lambda pair: len(pair[0]))
        title, link = entries[0]
        projects.append({"id": project_id, "title": title, "url": link})

    return projects


def load_seen_ids(path: str) -> set:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_seen_ids(path: str, ids_ordered: list):
    # نحتفظ بآخر MAX_STORED_IDS بس
    trimmed = ids_ordered[:MAX_STORED_IDS]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(trimmed))


def send_telegram_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("تحذير: TELEGRAM_TOKEN أو TELEGRAM_CHAT_ID مش متظبطين.", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=data, timeout=20)
    if not resp.ok:
        print(f"فشل إرسال رسالة تلجرام: {resp.status_code} {resp.text}", file=sys.stderr)


def main():
    try:
        projects = fetch_projects(PROJECTS_URL)
    except Exception as e:
        print(f"خطأ أثناء جلب المشاريع: {e}", file=sys.stderr)
        sys.exit(1)

    if not projects:
        print("لم يتم العثور على أي مشاريع في الصفحة.")
        return

    seen_ids = load_seen_ids(SEEN_FILE)
    is_first_run = len(seen_ids) == 0

    new_projects = [p for p in projects if p["id"] not in seen_ids]

    # أول مرة تشتغل السكريبت: نسجل كل اللي موجود من غير ما نبعت إشعارات
    # (عشان منغرقش نفسنا بعشرات الرسايل مرة واحدة)
    if not is_first_run and new_projects:
        # نبعتهم من الأقدم للأحدث عشان الترتيب يبقى منطقي في تلجرام
        for p in reversed(new_projects):
            message = (
                f"🆕 مشروع جديد على مستقل\n\n"
                f"<b>{p['title']}</b>\n"
                f"{p['url']}"
            )
            send_telegram_message(message)
        print(f"تم إرسال {len(new_projects)} إشعار.")
    elif is_first_run:
        print(f"أول تشغيل: تم تسجيل {len(projects)} مشروع من غير إرسال إشعارات.")
    else:
        print("مفيش مشاريع جديدة.")

    # نحدث قايمة اللي شفناهم (الأحدث فوق)
    all_ids_ordered = [p["id"] for p in projects] + [
        i for i in seen_ids if i not in {p["id"] for p in projects}
    ]
    save_seen_ids(SEEN_FILE, all_ids_ordered)


if __name__ == "__main__":
    main()
