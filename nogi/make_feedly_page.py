import csv

BASE = "https://Bolsroll.github.io/rss/nogi/members_xml/"

html = "<html><body><h2>乃木坂RSS一覧</h2>\n"

with open("members.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        name = row["name"]
        slug = row["slug"]
        url = BASE + slug + ".xml"

        html += f'<a href="{url}" target="_blank">{name}</a><br>\n'

html += "</body></html>"

with open("feedly.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ feedly.html 作成完了")