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
CATEGORY_URL = "https://mostaql.com/projects/support"
ALL_PROJECTS_URL = "https://mostaql.com/projects"
KEYWORDS = ["إدخال بيانات", "ادخال بيانات", "اكسيل", "Excel", "Data Entry"]

SEEN_FILE = "seen_ids.txt"
MAX_STORED_IDS = 1000

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch_projects(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    grouped = defaultdict(list)
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
        entries.sort(key=lambda pair: len(pair[0]))
        title, link = entries[0]
        description = entries[-1][0] if len(entries) > 1 else title
        projects.append({
            "id": project_id,
            "title": title,
            "description": description,
            "url": link,
        })

    return projects


def project_matches_keywords(project, keywords):
    if not keywords:
        return False
    haystack = (project["title"] + " " + project["description"]).lower()
    return any(kw.lower().strip() in haystack for kw in keywords if kw.strip())


def load_seen_ids(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_seen_ids(path, ids_ordered):
    trimmed = ids_ordered[:MAX_STORED_IDS]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(trimmed))


def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("تحذير: التوكن أو الشات آيدي مش متظبطين.", file=sys.stderr)
        return
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=data, timeout=20)
    if not resp.ok:
        print("فشل إرسال رسالة تلجرام: " + str(resp.status_code) + " " + resp.text, file=sys.stderr)


def build_message(tag, project):
    title = project["title"]
    url = project["url"]
    return "🆕 مشروع جديد (" + tag + ")\n\n<b>" + title + "</b>\n" + url


def main():
    try:
        category_projects = fetch_projects(CATEGORY_URL)
    except Exception as e:
        print("خطأ أثناء جلب مشاريع القسم الأساسي: " + str(e), file=sys.stderr)
        sys.exit(1)

    other_projects = []
    if CATEGORY_URL != ALL_PROJECTS_URL:
        try:
            all_projects = fetch_projects(ALL_PROJECTS_URL)
            category_ids = set(p["id"] for p in category_projects)
            other_projects = [p for p in all_projects if p["id"] not in category_ids]
        except Exception as e:
            print("تحذير: تعذر جلب باقي الأقسام: " + str(e), file=sys.stderr)

    if not category_projects and not other_projects:
        print("لم يتم العثور على أي مشاريع.")
        return

    seen_ids = load_seen_ids(SEEN_FILE)
    is_first_run = len(seen_ids) == 0

    new_from_category = [p for p in category_projects if p["id"] not in seen_ids]
    new_from_other = [p for p in other_projects if p["id"] not in seen_ids]

    if not is_first_run:
        sent_count = 0

        for p in reversed(new_from_category):
            send_telegram_message(build_message("القسم الأساسي", p))
            sent_count = sent_count + 1

        matching_other = [p for p in new_from_other if project_matches_keywords(p, KEYWORDS)]
        for p in reversed(matching_other):
            send_telegram_message(build_message("كلمة مطابقة", p))
            sent_count = sent_count + 1

        skipped = len(new_from_other) - len(matching_other)
        print("تم إرسال " + str(sent_count) + " إشعار. (تم تجاهل " + str(skipped) + " مشروع لعدم التطابق)")
    else:
        total_first = len(category_projects) + len(other_projects)
        print("أول تشغيل: تم تسجيل " + str(total_first) + " مشروع من غير إرسال إشعارات.")

    all_current_ids = [p["id"] for p in category_projects] + [p["id"] for p in other_projects]
    seen_in_this_run = set()
    deduped_ids = []
    for pid in all_current_ids:
        if pid not in seen_in_this_run:
            seen_in_this_run.add(pid)
            deduped_ids.append(pid)

    all_ids_ordered = deduped_ids + [i for i in seen_ids if i not in seen_in_this_run]
    save_seen_ids(SEEN_FILE, all_ids_ordered)


if __name__ == "__main__":
    main()
