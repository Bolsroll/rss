import os
import csv

BASE = "https://Bolsroll.github.io/rss/sakura/members_archive_xml/"
DIR = "members_archive_xml"

# --------------------------
# CSV読み込み（slug → name）
# --------------------------
slug_to_name = {}

with open("members.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        slug = row["slug"]
        name = row["name"]
        slug_to_name[slug] = name

# --------------------------
# HTML生成
# --------------------------
html = """<html>
<head>
<meta charset="UTF-8">
<title>櫻坂46 Archive RSS一覧</title>
</head>
<body>
<h2>櫻坂46 Archive RSS一覧</h2>
"""

files = os.listdir(DIR)

for f in sorted(files):
    if not f.endswith("_archive.xml"):
        continue

    slug = f.replace("_archive.xml", "")
    name = slug_to_name.get(slug, slug)

    url = BASE + f

    html += f'<a href="{url}" target="_blank">{name}</a><br>\n'

html += """
</body>
</html>
"""

with open("feedly_archive.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ Archive一覧生成（CSV基準）")