import asyncio
import os
import re
import time
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from playwright.async_api import async_playwright

# =========================================
# 共通ロック
# =========================================
LOCK_FILE = "/tmp/sakamichi_rss.lock"

# =========================================
# ディレクトリ固定
# =========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "https://www.hinatazaka46.com/s/official/diary/member/list"

OUTPUT_DIR = os.path.join(BASE_DIR, "members_archive_xml")
CSV_PATH = os.path.join(BASE_DIR, "members.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================================
# URL正規化
# =========================================
def normalize_url(url):
    return url.split("?")[0]


# =========================================
# CSV
# =========================================
def load_members(csv_path=CSV_PATH):

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


# =========================================
# 日付
# =========================================
def extract_date(text):

    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)

    if not m:
        return None

    y, mo, d = m.groups()

    return f"{y}/{mo.zfill(2)}/{d.zfill(2)} 00:00"


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


# =========================================
# XML既存読み込み
# =========================================
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

        link = re.search(
            r"<link>(.*?)</link>",
            it
        )

        title = re.search(
            r"<title>(.*?)</title>",
            it
        )

        pub = re.search(
            r"<pubDate>(.*?)</pubDate>",
            it
        )

        if link:

            result.append({
                "url": link.group(1),
                "title": title.group(1) if title else "",
                "pub": pub.group(1) if pub else ""
            })

    return result


# =========================================
# ページ履歴
# =========================================
def load_page_range(path):

    if not os.path.exists(path):
        return None, None

    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    m = re.search(
        r"Pages:\s*(\d+)-(\d+)",
        xml
    )

    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


def merge_page_range(
    old_min,
    old_max,
    new_min,
    new_max
):

    if old_min is None:
        return new_min, new_max

    return (
        min(old_min, new_min),
        max(old_max, new_max)
    )


# =========================================
# メイン
# =========================================
async def main(member_id, start_page, end_page):

    id_to_name, name_to_roma = load_members()

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

    # =========================================
    # 既存
    # =========================================
    existing = load_existing(output_path)

    existing_urls = set(
        normalize_url(x["url"])
        for x in existing
    )

    print("既存件数:", len(existing))

    # =========================================
    # ページ履歴
    # =========================================
    old_min, old_max = load_page_range(output_path)

    final_min, final_max = merge_page_range(
        old_min,
        old_max,
        start_page,
        end_page
    )

    print(
        f"ページ範囲: {final_min}-{final_max}"
    )

    new_items = []

    # =========================================
    # Playwright
    # =========================================
    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context()

        page = await context.new_page()

        for pageno in range(
            start_page,
            end_page + 1
        ):

            url = (
                f"{BASE_URL}"
                f"?ima=0000"
                f"&ct={member_id}"
                f"&page={pageno}"
            )

            print()
            print("================================")
            print("アクセス:", url)
            print("================================")

            try:

                await page.goto(
                    url,
                    timeout=60000,
                    wait_until="domcontentloaded"
                )

            except Exception as e:

                print("ページアクセス失敗:", e)
                continue

            # =========================================
            # 記事カード
            # =========================================
            cards = await page.locator(
                "div.p-blog-article"
            ).all()

            print("取得カード数:", len(cards))

            # 0件なら終了
            if not cards:

                print("⚠️ カード0件 → 終了")
                break

            for idx, card in enumerate(cards, start=1):

                try:

                    # =========================================
                    # タイトル
                    # =========================================
                    title_el = card.locator(
                        ".c-blog-article__title"
                    ).first

                    if not await title_el.count():

                        print("⚠️ title無し")
                        continue

                    raw_title = (
                        await title_el.inner_text()
                    ).strip()

                    if not raw_title:
                        continue

                    title = escape(raw_title)

                    # =========================================
                    # diary/detail URL探索
                    # =========================================
                    link_els = await card.locator(
                        "a[href*='/diary/detail/']"
                    ).all()

                    href = None

                    print("LINKS:")

                    candidate_urls = []

                    for link_el in link_els:

                        try:

                            test_href = await link_el.get_attribute(
                                "href"
                            )

                            if not test_href:
                                continue

                            print(" ", test_href)

                            # diary/detailのみ
                            if "/diary/detail/" not in test_href:
                                continue

                            candidate_urls.append(test_href)

                        except:
                            pass

                    # =========================================
                    # URL選択
                    # =========================================

                    # 相対URL優先
                    relative_urls = [
                        x for x in candidate_urls
                        if x.startswith("/s/")
                    ]

                    if relative_urls:

                        href = relative_urls[-1]

                        print(
                            "相対URL採用:",
                            href
                        )

                    # fallback
                    elif candidate_urls:

                        href = candidate_urls[-1]

                        print(
                            "fallback採用:",
                            href
                        )

                    if not href:

                        print("⚠️ href無し")
                        continue

                    # 相対URL補完
                    if href.startswith("/"):

                        full_url = (
                            "https://www.hinatazaka46.com"
                            + href
                        )

                    else:

                        full_url = href

                    print(f"[{idx}] {full_url}")

                    # =========================================
                    # 重複
                    # =========================================
                    norm = normalize_url(full_url)

                    if norm in existing_urls:

                        print("既存スキップ")
                        continue

                    # =========================================
                    # 日付
                    # =========================================
                    text = await card.inner_text()

                    date_raw = extract_date(text)

                    if not date_raw:

                        print("⚠️ 日付取得失敗")
                        continue

                    pub = format_rss_date(date_raw)

                    if not pub:

                        print("⚠️ pubDate失敗")
                        continue

                    print(
                        "新規:",
                        raw_title,
                        "/",
                        date_raw
                    )

                    new_items.append({
                        "title": title,
                        "url": full_url,
                        "pub": pub
                    })

                except Exception as e:

                    print(
                        "カード処理失敗:",
                        e
                    )

        await browser.close()

    # =========================================
    # マージ
    # =========================================
    all_items = existing + new_items

    unique = {}

    for x in all_items:

        unique[
            normalize_url(x["url"])
        ] = x

    all_items = list(unique.values())

    all_items.sort(
        key=lambda x: parse_rss_pubdate(
            x["pub"]
        ),
        reverse=True
    )

    # =========================================
    # 件数
    # =========================================
    added_count = (
        len(all_items) - len(existing)
    )

    duplicate_removed = (
        len(new_items) - added_count
    )

    print()
    print("================================")
    print("新規取得:", len(new_items))
    print("追加保存:", added_count)
    print("重複除外:", duplicate_removed)
    print("総件数:", len(all_items))
    print("================================")

    # =========================================
    # RSS
    # =========================================
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

    print()
    print("==============================")
    print("保存完了")
    print(output_path)
    print("==============================")


# =========================================
# 実行
# =========================================
if __name__ == "__main__":

    MAX_AGE = 30 * 60

    if os.path.exists(LOCK_FILE):

        age = (
            time.time()
            - os.path.getmtime(LOCK_FILE)
        )

        if age < MAX_AGE:

            print("⛔ 他プロセス実行中")
            exit()

        else:

            print("⚠️ 古いlock削除")
            os.remove(LOCK_FILE)

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:

        asyncio.run(
            main("28", 0, 10)
        )

    finally:

        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)