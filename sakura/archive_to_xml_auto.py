import asyncio
import os
import re
from datetime import datetime, timezone
from playwright.async_api import async_playwright

BASE_URL = "https://sakurazaka46.com/s/s46/diary/blog/list"
OUTPUT_DIR = "members_archive_xml"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --------------------------
# URL正規化
# --------------------------
def normalize_url(url):
    return url.split("?")[0]


# --------------------------
# CSV
# --------------------------
def load_members(csv_path="members.csv"):
    id_to_name = {}
    name_to_roma = {}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue

            parts = line.strip().split(",")
            if len(parts) < 3:
                continue

            member_id = parts[0].strip()
            jp_name = parts[1].strip().replace(" ", "").replace("　", "")
            roma = parts[2].strip()

            id_to_name[member_id] = jp_name
            name_to_roma[jp_name] = roma

    return id_to_name, name_to_roma


# --------------------------
# 日付
# --------------------------
def extract_date(text):
    m = re.search(r"\d{4}/\d{1,2}/\d{1,2}", text)
    if m:
        y, mth, d = m.group(0).split("/")
        return f"{y}/{mth.zfill(2)}/{d.zfill(2)} 00:00"
    return None


def format_rss_date(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M")
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")
    except:
        return None


def parse_rss_pubdate(pub):
    try:
        return datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
    except:
        return datetime.min.replace(tzinfo=timezone.utc)


# --------------------------
# 既存RSS読み込み
# --------------------------
def load_existing(path):
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    items = re.findall(r"<item>(.*?)</item>", xml, re.S)

    result = []
    for it in items:
        link = re.search(r"<link>(.*?)</link>", it)
        title = re.search(r"<title>(.*?)</title>", it)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", it)

        if link:
            result.append({
                "url": link.group(1),
                "title": title.group(1) if title else "",
                "pub": pub.group(1) if pub else ""
            })

    return result


# --------------------------
# ページ範囲
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


def merge_page_range(old_min, old_max, new_min, new_max):
    if old_min is None:
        return new_min, new_max
    return min(old_min, new_min), max(old_max, new_max)


# --------------------------
# メイン
# --------------------------
async def main(member_id, start_page, end_page):

    id_to_name, name_to_roma = load_members()

    MEMBER_NAME = id_to_name[member_id]
    roma = name_to_roma[MEMBER_NAME]
    output_path = os.path.join(OUTPUT_DIR, f"{roma}_archive.xml")

    print("================================")
    print("名前:", MEMBER_NAME)
    print("================================")

    # 既存
    existing = load_existing(output_path)
    existing_urls = set(normalize_url(x["url"]) for x in existing)

    # ページ履歴
    old_min, old_max = load_page_range(output_path)
    final_min, final_max = merge_page_range(old_min, old_max, start_page, end_page)

    print(f"ページ範囲: {final_min}-{final_max}")

    new_items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for pageno in range(start_page, end_page + 1):
            url = f"{BASE_URL}?ima=0000&ct={member_id}&page={pageno}"
            print("\nページ:", url)

            await page.goto(url, timeout=60000)

            cards = await page.locator("ul.com-blog-part > li.box").all()

            if not cards:
                print("カードなし → 終了")
                break

            cards = cards[:12]

            for card in cards:

                a = card.locator("a[href*='/diary/detail/']").first
                href = await a.get_attribute("href")

                if not href:
                    continue

                full_url = "https://sakurazaka46.com" + href
                norm = normalize_url(full_url)

                if norm in existing_urls:
                    continue

                # タイトル
                title = None

                el = card.locator("h3").first
                if await el.count():
                    title = (await el.inner_text()).strip()

                if not title:
                    el = card.locator("p.ttl").first
                    if await el.count():
                        title = (await el.inner_text()).strip()

                if not title:
                    raw = await a.inner_text()
                    title = raw.split("\n")[0].strip()

                if not title or title in ["前へ", "次へ"]:
                    continue

                # 日付
                text = await card.inner_text()
                date_raw = extract_date(text)
                pub = format_rss_date(date_raw)

                if not pub:
                    continue

                print("新規:", title, "/", date_raw)

                new_items.append({
                    "title": title,
                    "url": full_url,
                    "pub": pub
                })

        await browser.close()

    # --------------------------
    # マージ
    # --------------------------
    all_items = existing + new_items

    unique = {}
    for x in all_items:
        unique[normalize_url(x["url"])] = x

    all_items = list(unique.values())
    all_items.sort(key=lambda x: parse_rss_pubdate(x["pub"]), reverse=True)

    # --------------------------
    # RSS
    # --------------------------
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

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{MEMBER_NAME} Archive</title>
<link>{BASE_URL}</link>
<description>過去記事 {len(all_items)}件 Pages: {final_min}-{final_max}</description>
{rss_items}
</channel>
</rss>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss)

    print("\n==============================")
    print("完了:", output_path)
    print("合計:", len(all_items))
    print("==============================")


# --------------------------
# 実行
# --------------------------
if __name__ == "__main__":
    asyncio.run(main("50", 0, 2))