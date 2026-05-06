import asyncio
import os
import re
import time
from datetime import datetime
from playwright.async_api import async_playwright

# 共通ロック（ここだけ変更）
LOCK_FILE = "/tmp/rss_global.lock"

BASE_URL = "https://www.nogizaka46.com/s/n46/diary/MEMBER/list"
OUTPUT_DIR = "members_archive_xml"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --------------------------
# URL正規化
# --------------------------
def normalize_url(url):
    return url.split("?")[0]


# --------------------------
# CSV読み込み
# --------------------------
def load_members(csv_path="members.csv"):
    id_to_name = {}
    name_to_roma = {}

    with open(csv_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue

            member_id, jp_name, roma = parts
            jp_name = jp_name.replace(" ", "").replace("　", "")

            id_to_name[member_id] = jp_name
            name_to_roma[jp_name] = roma

    return id_to_name, name_to_roma


# --------------------------
# 日付処理
# --------------------------
def format_rss_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y.%m.%d %H:%M")
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")
    except:
        return ""


def parse_rss_pubdate(pub):
    try:
        return datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
    except:
        return datetime.min


# --------------------------
# 既存XML読み込み
# --------------------------
def load_existing_items(path):
    items = []
    if not os.path.exists(path):
        return items

    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    blocks = re.findall(r"<item>(.*?)</item>", xml, re.S)

    for b in blocks:
        link = re.search(r"<link>(.*?)</link>", b)
        title = re.search(r"<title>(.*?)</title>", b)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", b)

        items.append({
            "url": link.group(1) if link else "",
            "title": title.group(1) if title else "",
            "pub": pub.group(1) if pub else ""
        })

    return items


# --------------------------
# ページ範囲読み込み
# --------------------------
def load_page_range(path):
    if not os.path.exists(path):
        return None, None

    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    m = re.search(r"Pages:\s*(\d+)-(\d+)", xml)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


# --------------------------
# ページ範囲マージ
# --------------------------
def merge_page_range(old_min, old_max, new_min, new_max):
    if old_min is None:
        return new_min, new_max
    return min(old_min, new_min), max(old_max, new_max)


# --------------------------
# メイン処理
# --------------------------
async def main(member_id, start_page, end_page):

    id_to_name, name_to_roma = load_members()

    MEMBER_NAME = id_to_name.get(member_id)
    if not MEMBER_NAME:
        raise Exception(f"CSVに存在しないID: {member_id}")

    roma = name_to_roma[MEMBER_NAME]
    output_path = os.path.join(OUTPUT_DIR, f"{roma}_archive.xml")

    print("名前:", MEMBER_NAME)

    existing_items = load_existing_items(output_path)
    existing_urls = set(normalize_url(i["url"]) for i in existing_items)

    old_min, old_max = load_page_range(output_path)
    final_min, final_max = merge_page_range(old_min, old_max, start_page, end_page)

    print(f"ページ範囲: {final_min}-{final_max}")

    new_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for pageno in range(start_page, end_page + 1):
            url = f"{BASE_URL}?ct={member_id}&page={pageno}"
            print("ページ:", url)

            await page.goto(url, timeout=60000)

            links = await page.locator("a[href*='/diary/detail/']").all()
            if not links:
                break

            for a in links:
                href = await a.get_attribute("href")
                if not href:
                    continue

                full_url = normalize_url("https://www.nogizaka46.com" + href)

                if full_url in existing_urls:
                    continue

                detail = await context.new_page()
                await detail.goto(full_url, timeout=60000)

                html = await detail.content()
                body = await detail.inner_text("body")

                title = "no title"
                t = re.search(r"<title>(.*?)</title>", html, re.S)
                if t:
                    title = re.sub(r"\d{4}\.\d{2}\.\d{2}.*", "", t.group(1)).strip()

                date = ""
                m = re.search(r"\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}", body)
                if m:
                    date = m.group(0)

                print("取得:", title)

                new_items.append({
                    "title": title,
                    "url": full_url,
                    "date": date
                })

                await detail.close()

        await browser.close()

    # --------------------------
    # 統合
    # --------------------------
    all_items = []

    for i in existing_items:
        all_items.append({
            "title": i["title"],
            "url": normalize_url(i["url"]),
            "pub": i["pub"]
        })

    for n in new_items:
        all_items.append({
            "title": n["title"],
            "url": n["url"],
            "pub": format_rss_date(n["date"])
        })

    unique = {}
    for item in all_items:
        unique[normalize_url(item["url"])] = item

    all_items = list(unique.values())
    all_items.sort(key=lambda x: parse_rss_pubdate(x["pub"]), reverse=True)

    rss_items = ""

    for item in all_items:
        rss_items += f"""
        <item>
            <title>{item['title']}</title>
            <link>{item['url']}</link>
            <guid>{item['url']}</guid>
            <pubDate>{item['pub']}</pubDate>
        </item>
        """

    total_count = len(all_items)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{MEMBER_NAME} Archive</title>
<link>{BASE_URL}</link>
<description>過去記事 {total_count}件 Pages: {final_min}-{final_max}</description>
{rss_items}
</channel>
</rss>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"✅ 完了: {output_path}（{total_count}件）")


# --------------------------
# ロック処理
# --------------------------
if __name__ == "__main__":
    MAX_AGE = 30 * 60

    if os.path.exists(LOCK_FILE):
        age = time.time() - os.path.getmtime(LOCK_FILE)

        if age < MAX_AGE:
            print("⛔ 他の処理が動いてるので停止")
            exit()
        else:
            print("⚠️ 古いlock削除")
            os.remove(LOCK_FILE)

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        asyncio.run(main("48008", 3, 11))
    finally:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)