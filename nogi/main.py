import asyncio
import os
import json
import re
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ==========================
# 共通ロック
# ==========================
LOCK_FILE = "/tmp/sakamichi_rss.lock"

# ==========================
# ★ディレクトリ固定（ここ追加）
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "https://www.nogizaka46.com/s/n46/diary/MEMBER/list"

DATA_FILE = os.path.join(BASE_DIR, "data.json")
MEMBER_DIR = os.path.join(BASE_DIR, "members")
RSS_FILE = os.path.join(BASE_DIR, "rss.xml")

FETCH_LIMIT = 50
MAX_ITEMS = 30

# --------------------------
# 初期化
# --------------------------
os.makedirs(MEMBER_DIR, exist_ok=True)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

# unknown削除
unknown_path = os.path.join(MEMBER_DIR, "unknown.json")
if os.path.exists(unknown_path):
    os.remove(unknown_path)
    print("🧹 unknown.json削除")

# --------------------------
# utils
# --------------------------
def clean_text(s):
    if not s:
        return ""
    return s.replace("\u00A0", " ").strip()

def normalize_url(url):
    return url.split("?")[0]

def format_rss_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y.%m.%d %H:%M")
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")
    except:
        return ""

# --------------------------
# data
# --------------------------
def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --------------------------
# scrape（変更なし）
# --------------------------
async def scrape(page, context):
    await page.goto(BASE_URL, timeout=60000)
    await page.wait_for_selector("a[href*='/diary/detail/']", timeout=10000)

    links = await page.locator("a[href*='/diary/detail/']").all()

    items = []
    seen = set()

    for link in links[:FETCH_LIMIT]:
        url = await link.get_attribute("href")
        if not url:
            continue

        if not url.startswith("http"):
            url = "https://www.nogizaka46.com" + url

        norm = normalize_url(url)
        if norm in seen:
            continue
        seen.add(norm)

        detail = None
        try:
            detail = await context.new_page()
            await detail.goto(url, timeout=60000)

            await detail.wait_for_load_state("networkidle")
            await detail.wait_for_timeout(1000)

            title = "no title"
            try:
                t = await detail.title()
                title = re.sub(r"\d{4}\.\d{2}\.\d{2}.*", "", t).strip()
            except:
                pass

            date = "unknown"
            try:
                body = await detail.inner_text("body")
                m = re.search(r"\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}", body)
                if m:
                    date = m.group(0)
            except:
                pass

            name = "unknown"
            try:
                name = await detail.locator("p.bd--prof__name").inner_text(timeout=2000)
                name = clean_text(name)
            except:
                pass

            if name == "unknown":
                try:
                    t = await detail.title()
                    if "｜" in t:
                        name = t.split("｜")[-1].strip()
                    elif "|" in t:
                        name = t.split("|")[-1].strip()
                except:
                    pass

            print(f"取得: {title} / {name} / {date}")

            items.append({
                "title": title,
                "url": url,
                "date": date,
                "member": name
            })

        except:
            print("⚠️ 取得失敗:", url)

        finally:
            if detail:
                try:
                    await detail.close()
                except:
                    pass

    return items

# --------------------------
# merge
# --------------------------
def merge_data(new_items, old_items):
    merged = {}

    for item in old_items:
        merged[normalize_url(item["url"])] = item

    for item in new_items:
        merged[normalize_url(item["url"])] = item

    def sort_key(x):
        try:
            return datetime.strptime(x["date"], "%Y.%m.%d %H:%M")
        except:
            return datetime.min

    return sorted(merged.values(), key=sort_key, reverse=True)

# --------------------------
# rebuild
# --------------------------
def rebuild_members(all_items):
    print("🔄 メンバー別JSON再構築開始")

    for f in os.listdir(MEMBER_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(MEMBER_DIR, f))

    bucket = {}

    for item in all_items:
        name = item["member"]
        if not name or name == "unknown":
            continue

        bucket.setdefault(name, []).append(item)

    for name, items in bucket.items():
        safe = name.replace(" ", "").replace("/", "_")

        items_sorted = sorted(
            items,
            key=lambda x: datetime.strptime(x["date"], "%Y.%m.%d %H:%M") if x["date"] != "unknown" else datetime.min,
            reverse=True
        )

        path = os.path.join(MEMBER_DIR, f"{safe}.json")

        with open(path, "w") as f:
            json.dump(items_sorted[:MAX_ITEMS], f, ensure_ascii=False, indent=2)

    print("✅ 再構築完了")

# --------------------------
# rss
# --------------------------
def generate_rss(items):
    rss_items = ""
    seen = set()

    for item in items:
        norm = normalize_url(item["url"])
        if norm in seen:
            continue
        seen.add(norm)

        pub = format_rss_date(item["date"])

        rss_items += f"""
        <item>
            <title>{item['title']}</title>
            <link>{item['url']}</link>
            <guid>{item['url']}</guid>
            <pubDate>{pub}</pubDate>
        </item>
        """

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Nogizaka Blog</title>
<link>{BASE_URL}</link>
<description>乃木坂ブログRSS</description>
{rss_items}
</channel>
</rss>
"""

    with open(RSS_FILE, "w") as f:
        f.write(rss)

# --------------------------
# main
# --------------------------
async def main():
    old_data = load_data()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()

        new_items = await scrape(page, context)

        print("取得件数:", len(new_items))

        all_data = merge_data(new_items, old_data)

        save_data(all_data)

        rebuild_members(all_data)

        generate_rss(all_data[:50])

        await browser.close()

    print("✅ 完了")

# --------------------------
# run（共通ロック）
# --------------------------
if __name__ == "__main__":
    MAX_AGE = 30 * 60

    if os.path.exists(LOCK_FILE):
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age < MAX_AGE:
            print("⛔ 実行中（共通ロック）")
            exit()
        else:
            os.remove(LOCK_FILE)

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        asyncio.run(main())
    finally:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)