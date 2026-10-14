
import json
import os
from datetime import date, timedelta, datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main():
    token_json = os.environ["YOUTUBE_TOKEN_JSON"]
    token_info = json.loads(token_json)

    credentials = Credentials.from_authorized_user_info(
        token_info,
        scopes=SCOPES,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    youtube = build(
        "youtube", "v3",
        credentials=credentials,
        cache_discovery=False,
    )
    analytics = build(
        "youtubeAnalytics", "v2",
        credentials=credentials,
        cache_discovery=False,
    )

    channel_response = youtube.channels().list(
        part="snippet,statistics",
        mine=True,
    ).execute()

    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError(
            "No YouTube channel was found for the authorized account."
        )

    channel = channels[0]
    today = date.today()
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=6)

    report = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics="views,likes,comments,shares,subscribersGained",
        dimensions="day",
        sort="day",
    ).execute()

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel_title": channel["snippet"]["title"],
        "channel_id": channel["id"],
        "channel_statistics": channel.get("statistics", {}),
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "analytics_column_headers": report.get("columnHeaders", []),
        "daily_analytics_rows": report.get("rows", []),
    }

    with open("analytics_report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Analytics report created successfully.")
    print("Channel:", result["channel_title"])
    print("Period:", start_date, "to", end_date)
    print("Daily rows:", len(result["daily_analytics_rows"]))


if __name__ == "__main__":
    main()
