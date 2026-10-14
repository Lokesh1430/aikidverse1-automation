
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

base_url = os.environ["SUPABASE_URL"].rstrip("/")
api_key = os.environ["SUPABASE_SECRET_KEY"]

tables = ["story_history", "production_jobs"]

for table in tables:
    query = urllib.parse.urlencode({
        "select": "id",
        "limit": "1"
    })
    url = f"{base_url}/rest/v1/{table}?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"PASS: {table} is accessible (HTTP {response.status})")
    except urllib.error.HTTPError as error:
        # Do not print response headers or credentials.
        print(f"FAIL: {table} returned HTTP {error.code}")
        print(error.read().decode("utf-8", errors="replace")[:500])
        sys.exit(1)
    except Exception as error:
        print(f"Connection failed for {table}: {type(error).__name__}")
        sys.exit(1)

print("Supabase connection test completed.")
