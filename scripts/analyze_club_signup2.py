import requests
import re

url = 'https://zotspot.uci.edu/club_signup?group_type=9999'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)

# Find all JavaScript API references
matches = re.findall(r'/mobile_ws/v17/([^"\'\s\?]+)', r.text)
print(f'API endpoints: {matches}')

# Find getWebServiceUrl calls
matches2 = re.findall(r'getWebServiceUrl\(["\']([^"\']+)', r.text)
print(f'getWebServiceUrl: {matches2}')

# Find mobileFileName
matches3 = re.findall(r'mobileFileName["\s:=]+["\']([^"\']+)', r.text)
print(f'mobileFileName: {matches3}')