import requests
import re

url = 'https://zotspot.uci.edu/club_signup'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)
print(f'Status: {r.status_code}')
print(f'Length: {len(r.text)}')

# Find all mobile_ws API endpoints
matches = re.findall(r'mobile_ws/v17/([^"\']+)', r.text)
print(f'API endpoints found: {matches}')

# Find all mobileFileName references
matches2 = re.findall(r'mobileFileName["\s:=]+["\']([^"\']+)', r.text)
print(f'mobileFileName values: {matches2}')

# Find all getWebServiceUrl calls
matches3 = re.findall(r'getWebServiceUrl\(["\']([^"\']+)', r.text)
print(f'getWebServiceUrl calls: {matches3}')