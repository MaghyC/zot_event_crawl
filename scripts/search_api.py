import re

with open('/Users/hycai/Downloads/Assignment2-ai_innovation/zotspot.uci.edu.html') as f:
    html = f.read()

# Find all unique mobileFileName values in the file
matches = re.findall(r'mobileFileName\s*[=:]\s*["\']([^"\']+)', html)
print(f'mobileFileName assignments: {set(matches)}')

# Find all getWebServiceUrl calls
matches2 = re.findall(r'getWebServiceUrl\(["\']([^"\']+)', html)
print(f'getWebServiceUrl calls: {set(matches2)}')

# Search for 'groups' in API context
matches3 = re.findall(r'mobile_ws/v17/([^"\'\s\?]+)', html)
print(f'mobile_ws endpoints: {set(matches3)}')