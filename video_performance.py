
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
    token_info = json.loads(os.environ["YOUTUBE_TOKEN_JSON"])

    credentials = Credentials.from_authorized_user_info(
        token_info, scopes=SCOPES
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    youtube = build(
        "youtube", "v3", credentials=credentials,
        cache_discovery=False
    )
    analytics = build(
        "youtubeAnalytics", "v2", credentials=credentials,
        cache_discovery=False
    )

    channel_response = youtube.channels().list(
        part="contentDetails,snippet",
        mine=True,
    ).execute()

    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError("No channel found for the authorized account.")

    channel = channels[0]
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = []
    page_token = None

    # Read up to 50 recent uploads for the first report.
    while len(videos) < 50:
        response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=min(50, 50 - len(videos)),
            pageToken=page_token,
        ).execute()

        for item in response.get("items", []):
            videos.append({
                "video_id": item["contentDetails"]["videoId"],
                "title": item["snippet"]["title"],
                "published_at": item["contentDetails"].get("videoPublishedAt"),
            })

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if not videos:
        raise RuntimeError("No uploaded videos found.")

    today = date.today()
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=27)

    # The Analytics API returns video-level results for the selected period.
    report = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained",
        dimensions="video",
        sort="-views",
        maxResults=200,
    ).execute()

    headers = [
        column["name"] for column in report.get("columnHeaders", [])
    ]
    analytics_by_id = {}

    for row in report.get("rows", []):
        values = dict(zip(headers, row))
        video_id = values.pop("video", None)
        if video_id:
            analytics_by_id[video_id] = values

    for video in videos:
        video["analytics"] = analytics_by_id.get(
            video["video_id"], {}
        )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel_title": channel["snippet"]["title"],
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "videos": videos,
        "top_videos": sorted(
            videos,
            key=lambda item: item["analytics"].get("views", 0),
            reverse=True,
        )[:10],
    }

    with open("video_performance.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Video performance report created.")
    print("Channel:", result["channel_title"])
    print("Uploaded videos found:", len(videos))
    print("Top videos with analytics:",
          sum(bool(v["analytics"]) for v in videos))


if __name__ == "__main__":
    main()
