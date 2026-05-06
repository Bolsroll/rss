import os

BASE = "https://Bolsroll.github.io/rss/nogi/members_archive_xml/"
DIR = "members_archive_xml"

html = "<html><body><h2>乃木坂Archive RSS一覧</h2>\n"

files = os.listdir(DIR)

for f in sorted(files):
    if not f.endswith("_archive.xml"):
        continue

    name = f.replace("_archive.xml", "")
    url = BASE + f

    html += f'<a href="{url}" target="_blank">{name}</a><br>\n'

html += "</body></html>"

with open("feedly_archive.html", "w", encoding="utf-8") as f:
    f.write(html)

print("✅ feedly_archive.html 作成完了")