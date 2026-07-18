import requests
import time

BASE_URL = "http://localhost:8000"

print("1. Registering test user...")
try:
    res = requests.post(f"{BASE_URL}/api/auth/register", json={"email": "live_test@pipeline.io", "password": "password"})
    if res.status_code == 400:
        print("User already exists, logging in instead.")
        res = requests.post(f"{BASE_URL}/api/auth/login", data={"username": "live_test@pipeline.io", "password": "password"})
    token = res.json().get("access_token")
    print(f"Token: {token[:10]}...")
except Exception as e:
    print("Auth failed:", e)
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

print("\n2. Discovering leads for 'design agency london'...")
res = requests.post(f"{BASE_URL}/api/discover", json={"keyword": "design agency london", "limit": 10})
data = res.json()
print("Discover response:", data)
csv_path = data.get("csv_path")

if csv_path:
    print(f"\n3. Starting pipeline with {csv_path}...")
    res = requests.post(f"{BASE_URL}/api/run?input_csv={csv_path}&campaign=design_test", headers=headers)
    print("Run response:", res.json())
    
    print("\n4. Polling stats for 15 seconds...")
    for _ in range(5):
        time.sleep(3)
        res = requests.get(f"{BASE_URL}/api/stats?campaign=design_test", headers=headers)
        print("Stats:", res.json())
