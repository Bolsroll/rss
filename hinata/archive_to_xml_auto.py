import asyncio
import os
import re
import time
from html import escape
from datetime import datetime, timezone
from playwright.async_api import async_playwright

# ==========================
# ★共通ロック
# ==========================
LOCK_FILE = "/tmp/sakamichi_rss.lock"

# ==========================
# 設定
# ==========================
BASE_URL = "https://www.hinatazaka46.com/s/official/diary/member/list"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR = os.path.join(BASE_DIR, "members_archive_xml")
CSV_PATH = os.path.join(BASE_DIR, "members.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================
# URL正規化
# ==========================
def normalize_url(url):
    return url.split("?")[0]

# ==========================
# CSV読み込み
# ==========================
def load_members():

    id_to_name = {}
    name_to_roma = {}

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:

        for i, line in enumerate(f):

            if i == 0:
                continue

            parts = line.strip().split(",")

            if len(parts) < 3:
                continue

            member_id = parts[0].strip()

            jp_name = (
                parts[1]
                .strip()
                .replace(" ", "")
                .replace("　", "")
            )

            roma = parts[2].strip()

            id_to_name[member_id] = jp_name
            name_to_roma[jp_name] = roma

    return id_to_name, name_to_roma

# ==========================
# 日付抽出
# ==========================
def extract_date(text):

    m = re.search(r"\d{4}[./]\d{1,2}[./]\d{1,2}", text)

    if not m:
        return None

    raw = m.group(0).replace(".", "/")

    y, mo, d = raw.split("/")

    return f"{y}/{mo.zfill(2)}/{d.zfill(2)} 00:00"

# ==========================
# RSS日付
# ==========================
def format_rss_date(date_str):

    if not date_str:
        return None

    try:

        dt = datetime.strptime(
            date_str,
            "%Y/%m/%d %H:%M"
        )

        return dt.strftime(
            "%a, %d %b %Y %H:%M:%S +0900"
        )

    except:
        return None

# ==========================
# sort用
# ==========================
def parse_rss_pubdate(pub):

    try:

        return datetime.strptime(
            pub,
            "%a, %d %b %Y %H:%M:%S %z"
        )

    except:

        return datetime.min.replace(
            tzinfo=timezone.utc
        )

# ==========================
# 既存XML読み込み
# ==========================
def load_existing(path):

    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    items = re.findall(
        r"<item>(.*?)</item>",
        xml,
        re.S
    )

    result = []

    for it in items:

        link = re.search(r"<link>(.*?)</link>", it)
        title = re.search(r"<title>(.*?)</title>", it)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", it)

        if not link:
            continue

        result.append({
            "url": link.group(1),
            "title": title.group(1) if title else "",
            "pub": pub.group(1) if pub else ""
        })

    return result

# ==========================
# ページ範囲
# ==========================
def load_page_range(path):

    if not os.path.exists(path):
        return None, None

    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    m = re.search(r"Pages:\s*(\d+)-(\d+)", xml)

    if not m:
        return None, None

    return int(m.group(1)), int(m.group(2))

def merge_page_range(old_min, old_max, new_min, new_max):

    if old_min is None:
        return new_min, new_max

    return (
        min(old_min, new_min),
        max(old_max, new_max)
    )

# ==========================
# main
# ==========================
async def main(member_id, start_page, end_page):

    id_to_name, name_to_roma = load_members()

    if member_id not in id_to_name:
        print("❌ member_id 不明")
        return

    MEMBER_NAME = id_to_name[member_id]

    roma = name_to_roma[MEMBER_NAME]

    output_path = os.path.join(
        OUTPUT_DIR,
        f"{roma}_archive.xml"
    )

    print("================================")
    print("名前:", MEMBER_NAME)
    print("member_id:", member_id)
    print("ページ:", start_page, "-", end_page)
    print("出力:", output_path)
    print("================================")

    # --------------------------
    # 既存読み込み
    # --------------------------
    existing = load_existing(output_path)

    existing_urls = set(
        normalize_url(x["url"])
        for x in existing
    )

    print("既存件数:", len(existing))

    # --------------------------
    # ページ範囲
    # --------------------------
    old_min, old_max = load_page_range(output_path)

    final_min, final_max = merge_page_range(
        old_min,
        old_max,
        start_page,
        end_page
    )

    print(f"ページ範囲: {final_min}-{final_max}")

    # --------------------------
    # scrape
    # --------------------------
    new_items = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context()

        page = await context.new_page()

        for pageno in range(start_page, end_page + 1):

            url = (
                f"{BASE_URL}"
                f"?ima=0000"
                f"&ct={member_id}"
                f"&page={pageno}"
            )

            print("\n================================")
            print("アクセス:", url)
            print("================================")

            try:

                await page.goto(
                    url,
                    timeout=60000
                )

                await page.wait_for_timeout(2000)

                cards = await page.locator(
                    "div.p-blog-article"
                ).all()

                print("取得カード数:", len(cards))

                if not cards:
                    print("⚠️ カード0件")
                    continue

                for idx, card in enumerate(cards, start=1):

                    try:

                        # --------------------------
                        # title
                        # --------------------------
                        title = ""

                        el = card.locator(
                            "div.c-blog-article__title"
                        ).first

                        if await el.count():

                            title = (
                                await el.inner_text()
                            ).strip()

                        if not title:
                            continue

                        # --------------------------
                        # link
                        # --------------------------
                        a = card.locator(
                            "a[href*='/detail/']"
                        ).first

                        href = await a.get_attribute("href")

                        if not href:
                            continue

                        if href.startswith("http"):

                            full_url = href

                        else:

                            full_url = (
                                "https://www.hinatazaka46.com"
                                + href
                            )

                        print(f"[{idx}] {full_url}")

                        norm = normalize_url(full_url)

                        if norm in existing_urls:
                            continue

                        # --------------------------
                        # date
                        # --------------------------
                        date_text = ""

                        el = card.locator(
                            "div.c-blog-article__date"
                        ).first

                        if await el.count():

                            date_text = (
                                await el.inner_text()
                            ).strip()

                        date_raw = extract_date(date_text)

                        pub = format_rss_date(date_raw)

                        if not pub:
                            print("⚠️ 日付失敗:", title)
                            continue

                        print(
                            "新規:",
                            title,
                            "/",
                            date_raw
                        )

                        new_items.append({
                            "title": title,
                            "url": full_url,
                            "pub": pub
                        })

                    except Exception as e:

                        print("❌ card解析失敗")
                        print(e)

            except Exception as e:

                print("❌ page失敗")
                print(e)

        await browser.close()

    # ==========================
    # merge
    # ==========================
    all_items = existing + new_items

    unique = {}

    for x in all_items:
        unique[normalize_url(x["url"])] = x

    all_items = list(unique.values())

    all_items.sort(
        key=lambda x: parse_rss_pubdate(x["pub"]),
        reverse=True
    )

    print("\n合計:", len(all_items))

    # ==========================
    # RSS生成
    # ==========================
    rss_items = ""

    for item in all_items:

        rss_items += f"""
        <item>
            <title>{escape(item['title'])}</title>
            <link>{escape(item['url'])}</link>
            <guid>{escape(item['url'])}</guid>
            <pubDate>{item['pub']}</pubDate>
        </item>
        """

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{escape(MEMBER_NAME)} Archive</title>
<link>{escape(BASE_URL)}</link>
<description>過去記事 {len(all_items)}件 Pages: {final_min}-{final_max}</description>
{rss_items}
</channel>
</rss>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss)

    print("\n==============================")
    print("保存完了")
    print(output_path)
    print("==============================")

# ==========================
# 実行（共通ロック）
# ==========================
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

        # page=0 と 1 が重複するケース回避
        asyncio.run(main("14", 1, 3))

    finally:

        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)