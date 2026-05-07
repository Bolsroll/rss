import csv

BASE = "https://Bolsroll.github.io/rss/sakura/members_xml/"

html = """<html>
<head>
<meta charset="UTF-8">
<title>櫻坂46 RSS一覧</title>
</head>
<body>
<h2>櫻坂46 RSS一覧</h2>
"""

with open("members.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        name = row["name"]
        slug = row["slug"]

        url = BASE + slug + ".xml"

        html += f'<a href="{url}" target="_blank">{name}</a><br>\n'

html += """
</body>
</html>
"""

with open("feedly.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ 通常RSS一覧生成（CSV完全一致）")