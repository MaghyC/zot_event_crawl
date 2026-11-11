import requests
import re

url = 'https://zotspot.uci.edu/club_signup?group_type=9999'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)
print(f'Status: {r.status_code}')
print(f'Length: {len(r.text)}')

# Look for API endpoints
matches = re.findall(r'mobile_ws/v17/([^"\'\s]+)', r.text)
print(f'API endpoints: {matches}')

# Find script references
scripts = re.findall(r'src=["\']([^"\']+\.js)', r.text)
for s in scripts[:20]:
    print(s)