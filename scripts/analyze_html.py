import re

with open('/Users/hycai/Downloads/Assignment2-ai_innovation/zotspot.uci.edu.html') as f:
    html = f.read()

# Find all mobileFileName values
matches = re.findall(r'mobileFileName["\s:=]+["\']([^"\']+)', html)
print(f'mobileFileName: {matches}')

# Find all getWebServiceUrl calls
matches2 = re.findall(r'getWebServiceUrl\(["\']([^"\']+)', html)
print(f'getWebServiceUrl: {matches2}')

# Find all mobile_ws endpoints
matches3 = re.findall(r'mobile_ws/v17/([^"\'\s]+)', html)
print(f'mobile_ws endpoints: {matches3}')