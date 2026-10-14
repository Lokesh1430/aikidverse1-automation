
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path

TZ = ZoneInfo("Asia/Kolkata")
now = datetime.now(TZ)

report = {
    "channel": "AIKidVerse1",
    "status": "success",
    "message": "GitHub Actions cloud automation is running!",
    "timestamp_ist": now.isoformat(),
    "next_stage": "Connect Supabase and build the video pipeline"
}

Path("run_report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print(json.dumps(report, indent=2))
