import re

with open('/Users/hycai/Downloads/Assignment2-ai_innovation/zotspot.uci.edu.html') as f:
    html = f.read()

# Find script src
scripts = re.findall(r'src=["\']([^"\']+\.js)', html)
for s in scripts[:30]:
    print(s)