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
# القسم الأساسي: أي مشروع جديد فيه يتبعت على طول من غير أي شرط
CATEGORY_URL = "https://mostaql.com/projects/support"   # دعم، مساعدة وإدخال بيانات
# لو عايز تغير القسم الأساسي، غير اللينك ده. أمثلة:
# "https://mostaql.com/projects/development"  # برمجة وتطوير
# "https://mostaql.com/projects"              # كل الأقسام (يلغي عملياً فكرة "باقي الأقسام")

ALL_PROJECTS_URL = "https://mostaql.com/projects"  # ثابت - بيستخدم لفحص "باقي الأقسام"

# الكلمات المفتاحية اللي بيتم البحث عنها في باقي الأقسام (غير القسم الأساسي)
# افصل بين كل كلمة والتانية بفاصلة. لو سبتها فاضية، مفيش بحث في باقي الأقسام خالص.
KEYWORDS = ["إدخال بيانات", "ادخال بيانات", "اكسيل", "Excel", "Data Entry"]

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
        # أطول نص مرتبط بنفس المشروع غالباً بيكون وصف المشروع الكامل
        description = entries[-1][0] if len(entries) > 1 else title
        projects.append({
            "id": project_id,
            "title": title,
            "description": description,
            "url": link,
        })

    return projects


def project_matches_keywords(project: dict, keywords: list) -> bool:
    """يرجع True لو مفيش كلمات مفتاحية أصلاً، أو لو لقى أي كلمة منهم في العنوان أو الوصف."""
    if not keywords:
        return False
    haystack = (project["title"] + " " + project["description"]).lower()
    return any(kw.lower().strip() in haystack for kw in keywords if kw.strip())


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
        category_projects = fetch_projects(CATEGORY_URL)
    except Exception as e:
        print(f"خطأ أثناء جلب مشاريع القسم الأساسي: {e}", file=sys.stderr)
        sys.exit(1)

    # لو القسم الأساسي مش "كل الأقسام"، نجيب باقي الأقسام كمان عشان ندور فيهم بالكلمات المفتاحية
    other_projects = []
    if CATEGORY_URL != ALL_PROJECTS_URL:
        try:
            all_projects = fetch_projects(ALL_PROJECTS_URL)
            category_ids = {p["id"] for p in category_projects}
            other_projects = [p for p in all_projects if p["id"] not in category_ids]
        except Exception as e:
            print(f"تحذير: تعذر جلب باقي الأقسام: {e}", file=sys.stderr)

    if not category_projects and not other_projects:
        print("لم يتم العثور على أي مشاريع.")
        return

    seen_ids = load_seen_ids(SEEN_FILE)
    is_first_run = len(seen_ids) == 0

    new_from_category = [p for p in category_projects if p["id"] not in seen_ids]
    new_from_other = [p for p in other_projects if p["id"] not in seen_ids]

    if not is_first_run:
        sent_count = 0

        # القسم الأساسي: يتبعت كل حاجة فيه من غير شرط
        for p in reversed(new_from_category):
            message = f"🆕 مشروع جديد (القسم الأساسي)\n\n<b>{p['title']}</b>\n{p
