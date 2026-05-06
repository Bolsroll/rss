import asyncio
import os
import json
import re
import time
from datetime import datetime
from playwright.async_api import async_playwright

# ==========================
# ★共通ロック（サカミチ統一）
# ==========================
LOCK_FILE = "/tmp/sakamichi_rss.lock"

# ==========================
# ★ディレクトリ固定
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "https://sakurazaka46.com/s/s46/diary/blog/list?ima=0000"

DATA_FILE = os.path.join(BASE_DIR, "data.json")
MEMBER_DIR = os.path.join(BASE_DIR, "members")
RSS_FILE = os.path.join(BASE_DIR, "rss.xml")

FETCH_LIMIT = 12
MAX_ITEMS = 30

# --------------------------
# 初期化
# --------------------------
os.makedirs(MEMBER_DIR, exist_ok=True)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

# --------------------------
# utils
# --------------------------
def normalize_url(url):
    return url.split("?")[0]

def format_rss_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M")
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")
    except:
        return ""

# --------------------------
# data
# --------------------------
def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --------------------------
# scrape
# --------------------------
async def scrape(page):
    await page.goto(BASE_URL, timeout=60000)

    links = await page.locator("a[href*='/diary/detail/']").all()

    items = []
    seen = set()

    for link in links[:FETCH_LIMIT]:

        href = await link.get_attribute("href")
        if not href:
            continue

        url = "https://sakurazaka46.com" + href
        norm = normalize_url(url)

        if norm in seen:
            continue
        seen.add(norm)

        card = link.locator("xpath=ancestor::li").first

        # タイトル
        title = None
        try:
            el = card.locator("h3").first
            if await el.count():
                title = (await el.inner_text()).strip()
        except:
            pass

        if not title:
            try:
                raw = await link.inner_text()
                title = raw.split("\n")[0].strip()
            except:
                continue

        if not title or title in ["前へ", "次へ"]:
            continue

        # 余計な「公式ブログ」除外
        if "公式ブログ" in title:
            continue

        # メンバー
        name = "unknown"
        try:
            el = card.locator("p.name").first
            if await el.count():
                name = (await el.inner_text()).strip()
        except:
            pass

        # 日付
        text = await card.inner_text()
        m = re.search(r"\d{4}/\d{1,2}/\d{1,2}", text)

        if not m:
            continue

        y, mo, d = m.group(0).split("/")
        date = f"{y}/{mo.zfill(2)}/{d.zfill(2)} 00:00"

        print(f"取得: {title} / {name} / {date}")

        items.append({
            "title": title,
            "url": url,
            "date": date,
            "member": name
        })

    return items

# --------------------------
# メンバー別JSON生成（★追加）
# --------------------------
def rebuild_members(all_items):
    print("🔄 メンバー別JSON再構築開始")

    # 既存削除
    for f in os.listdir(MEMBER_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(MEMBER_DIR, f))

    bucket = {}

    for item in all_items:
        name = item.get("member")

        if not name or name == "unknown":
            continue

        bucket.setdefault(name, []).append(item)

    for name, items in bucket.items():
        safe = name.replace(" ", "").replace("/", "_")

        items_sorted = sorted(
            items,
            key=lambda x: datetime.strptime(x["date"], "%Y/%m/%d %H:%M") if x["date"] else datetime.min,
            reverse=True
        )

        path = os.path.join(MEMBER_DIR, f"{safe}.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(items_sorted[:MAX_ITEMS], f, ensure_ascii=False, indent=2)

        print(f"  → {name}: {len(items_sorted)}件")

    print("✅ メンバー別JSON再構築完了")

# --------------------------
# merge
# --------------------------
def merge_data(new_items, old_items):
    merged = {}

    for item in old_items:
        merged[normalize_url(item["url"])] = item

    for item in new_items:
        merged[normalize_url(item["url"])] = item

    return sorted(
        merged.values(),
        key=lambda x: datetime.strptime(x["date"], "%Y/%m/%d %H:%M") if x["date"] else datetime.min,
        reverse=True
    )

# --------------------------
# rss
# --------------------------
def generate_rss(items):
    rss_items = ""

    for item in items:
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
<title>Sakurazaka Blog</title>
<link>{BASE_URL}</link>
<description>櫻坂ブログRSS</description>
{rss_items}
</channel>
</rss>
"""

    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write(rss)

# --------------------------
# main
# --------------------------
async def main():
    old_data = load_data()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        new_items = await scrape(page)

        print("取得件数:", len(new_items))

        all_data = merge_data(new_items, old_data)

        save_data(all_data)

        # ★ここが今回の追加
        rebuild_members(all_data)

        generate_rss(all_data[:50])

        await browser.close()

    print("✅ 完了")

# --------------------------
# run
# --------------------------
if __name__ == "__main__":
    MAX_AGE = 30 * 60

    if os.path.exists(LOCK_FILE):
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age < MAX_AGE:
            print("⛔ 他プロセス実行中（共通ロック）")
            exit()
        else:
            print("⚠️ 古いlock削除")
            os.remove(LOCK_FILE)

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        asyncio.run(main())
    finally:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)