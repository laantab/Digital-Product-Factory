import requests
r = requests.get('http://127.0.0.1:5000/download-launch-package/250', timeout=15)
print(f"ZIP status: {r.status_code}")
ct = r.headers.get("Content-Type", "")
print(f"Content-Type: {ct}")
print(f"Size: {len(r.content)} bytes")
if r.status_code == 200:
    path = r"C:\Users\user\Desktop\The Factory\test_launch_package.zip"
    open(path, 'wb').write(r.content)
    print(f"Saved to {path}")
else:
    print(f"Error: {r.text[:300]}")
