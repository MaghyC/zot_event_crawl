import requests
import re

url = 'https://zotspot.uci.edu/club_signup'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)

# Find API references in the response
matches = re.findall(r'/mobile_ws/v17/([^"\'\s\?]+)', r.text)
print(f'API endpoints: {matches}')

# Find getWebServiceUrl calls
matches2 = re.findall(r'getWebServiceUrl\(["\']([^"\']+)', r.text)
print(f'getWebServiceUrl: {matches2}')

# Find mobileFileName
matches3 = re.findall(r'mobileFileName["\s:=]+["\']([^"\']+)', r.text)
print(f'mobileFileName: {matches3}')

# Find where group data might be loaded
if 'mobile_groups' in r.text:
    print('Found mobile_groups reference')
if 'groups_list' in r.text:
    print('Found groups_list reference')
if 'groupId' in r.text:
    print('Found groupId reference')