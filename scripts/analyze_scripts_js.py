import requests
import re

url = 'https://zotspot.uci.edu/static/js/scripts.js'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)
print(f'Status: {r.status_code}')
print(f'Length: {len(r.text)}')

# Find API endpoints
matches = re.findall(r'mobile_ws/v17/([^"\'\s]+)', r.text)
print(f'API endpoints: {matches}')

# Find mobileFileName
matches2 = re.findall(r'mobileFileName["\s:=]+["\']([^"\']+)', r.text)
print(f'mobileFileName: {matches2}')

# Find getWebServiceUrl calls
matches3 = re.findall(r'getWebServiceUrl\(["\']([^"\']+)', r.text)
print(f'getWebServiceUrl: {matches3}')