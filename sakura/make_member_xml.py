import os
import json
import csv
import time
from datetime import datetime

# ==========================
# ★共通ロック（サカミチ統一）
# ==========================
LOCK_FILE = "/tmp/sakamichi_rss.lock"

# ==========================
# ★ディレクトリ固定
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MEMBER_DIR = os.path.join(BASE_DIR, "members")
OUTPUT_DIR = os.path.join(BASE_DIR, "members_xml")
CSV_PATH = os.path.join(BASE_DIR, "members.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------
# CSV読み込み
# --------------------------
def load_member_map():
    mp = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["name"].replace(" ", "").replace("　", "")
            slug = row["slug"]
            mp[name] = slug
    return mp

member_map = load_member_map()

# --------------------------
# 日付変換
# --------------------------
def format_rss_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d %H:%M")
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")
    except:
        return None

# --------------------------
# URL正規化
# --------------------------
def normalize_url(url):
    return url.split("?")[0]

# --------------------------
# フィルタ
# --------------------------
def valid_item(item):
    if not item.get("url"):
        return False
    if "/diary/detail/" not in item["url"]:
        return False
    if not item.get("date") or item["date"] == "unknown":
        return False

    title = item.get("title", "").strip()
    if not title or title in ["前へ", "次へ"]:
        return False

    return True

# --------------------------
# XML生成
# --------------------------
def generate_xml(member_name, items):
    key = member_name.replace(" ", "").replace("　", "")
    slug = member_map.get(key, key)
    safe_name = slug

    print(f"  ▶ 処理対象: {member_name}")

    # --------------------------
    # フィルタ＋重複除去
    # --------------------------
    unique = {}
    for item in items:
        if not valid_item(item):
            continue
        norm = normalize_url(item["url"])
        unique[norm] = item

    items = list(unique.values())

    print(f"  → フィルタ後件数: {len(items)}")

    if not items:
        print("  ⚠️ 有効データ0件 → XMLスキップ")
        return

    # --------------------------
    # ソート
    # --------------------------
    def sort_key(x):
        try:
            return datetime.strptime(x["date"], "%Y/%m/%d %H:%M")
        except:
            return datetime.min

    items.sort(key=sort_key, reverse=True)

    # --------------------------
    # XML生成
    # --------------------------
    xml_items = ""

    for item in items:
        pub = format_rss_date(item["date"])
        if not pub:
            continue

        xml_items += f"""
        <item>
            <title>{item['title']}</title>
            <link>{item['url']}</link>
            <guid>{item['url']}</guid>
            <pubDate>{pub}</pubDate>
        </item>
        """

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{member_name} Blog</title>
<link>https://sakurazaka46.com/</link>
<description>{member_name}のブログRSS（{len(items)}件）</description>
{xml_items}
</channel>
</rss>
"""

    path = os.path.join(OUTPUT_DIR, f"{safe_name}.xml")

    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"  ✅ XML生成: {safe_name}.xml")

# --------------------------
# メイン
# --------------------------
def main():
    files = os.listdir(MEMBER_DIR)

    print(f"📂 JSONファイル数: {len(files)}")

    for file in files:
        if not file.endswith(".json"):
            continue

        path = os.path.join(MEMBER_DIR, file)
        print(f"\n📄 読み込み: {file}")

        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)

        print(f"  → 元データ件数: {len(items)}")

        if not items:
            print("  ⚠️ 空ファイル → スキップ")
            continue

        # ★安全なmember取得（先頭依存回避）
        member_name = next(
            (x.get("member") for x in items if x.get("member") and x.get("member") != "unknown"),
            None
        )

        print(f"  → 判定member: {member_name}")

        if not member_name:
            print("  ❌ member取得不可 → スキップ")
            continue

        generate_xml(member_name, items)

    print("\n✅ メンバー別XML生成完了")

# --------------------------
# 実行（共通ロック）
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
        main()
    finally:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)