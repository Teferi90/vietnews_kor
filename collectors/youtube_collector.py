import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
from dotenv import load_dotenv
from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger, StepTimer

CHANNELS = [
    {"name": "VTV24", "handle": "@vtv24"},
    {"name": "Tuổi Trẻ", "handle": "@baotuoitre"},
]

# 영상 길이 필터 (초 단위)
MIN_DURATION_SEC = 3 * 60
MAX_DURATION_SEC = 30 * 60

# 채널당 최대 수집 수
MAX_PER_CHANNEL = 10


def _parse_iso8601_duration(duration: str) -> int:
    """ISO 8601 duration 문자열을 초로 변환. 예: PT10M30S → 630"""
    pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    m = re.match(pattern, duration)
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _get_channel_id(youtube, handle: str) -> str:
    """채널 핸들(@xxx)로 채널 ID 조회"""
    response = youtube.search().list(
        part="snippet",
        q=handle,
        type="channel",
        maxResults=1,
    ).execute()
    items = response.get("items", [])
    if not items:
        raise ValueError(f"채널을 찾을 수 없음: {handle}")
    return items[0]["snippet"]["channelId"]


def _collect_videos_from_channel(
    youtube, channel_id: str, channel_name: str, published_after: str, published_before: str
) -> list[dict]:
    """한 채널에서 조건에 맞는 영상 목록 수집"""
    search_response = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        type="video",
        order="date",
        publishedAfter=published_after,
        publishedBefore=published_before,
        maxResults=MAX_PER_CHANNEL * 2,  # 길이 필터 여유분
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
    if not video_ids:
        return []

    details_response = youtube.videos().list(
        part="snippet,contentDetails",
        id=",".join(video_ids),
    ).execute()

    videos = []
    for item in details_response.get("items", []):
        duration_sec = _parse_iso8601_duration(item["contentDetails"]["duration"])
        if not (MIN_DURATION_SEC <= duration_sec <= MAX_DURATION_SEC):
            continue
        vid = item["id"]
        videos.append({
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": item["snippet"]["title"],
            "channel": channel_name,
            "duration": _format_duration(duration_sec),
            "published_at": item["snippet"]["publishedAt"],
        })
        if len(videos) >= MAX_PER_CHANNEL:
            break

    return videos


def collect_videos(logger=None) -> list[dict]:
    """VTV24, Tuổi Trẻ 채널에서 어제 영상을 수집하여 반환"""
    if logger is None:
        logger = get_logger()

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY 환경변수가 설정되지 않았습니다.")

    youtube = build("youtube", "v3", developerKey=api_key)

    # 베트남 시간 기준 어제 (UTC+7)
    vn_tz = timezone(timedelta(hours=7))
    now_vn = datetime.now(vn_tz)
    yesterday_vn = now_vn - timedelta(days=1)
    published_after = yesterday_vn.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    published_before = yesterday_vn.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    logger.info(f"수집 기간: {published_after} ~ {published_before} (베트남 시간)")

    all_videos = []
    for channel in CHANNELS:
        with StepTimer(logger, f"채널 수집: {channel['name']}"):
            channel_id = _get_channel_id(youtube, channel["handle"])
            logger.info(f"{channel['name']} 채널 ID: {channel_id}")
            videos = _collect_videos_from_channel(
                youtube, channel_id, channel["name"], published_after, published_before
            )
            logger.info(f"{channel['name']}: {len(videos)}개 수집")
            all_videos.extend(videos)

    logger.info(f"전체 후보 영상: {len(all_videos)}개")
    return all_videos


def select_videos_with_claude(videos: list[dict], logger=None) -> list[dict]:
    """Claude API로 카테고리 우선순위 기반 상위 3개 선별"""
    if logger is None:
        logger = get_logger()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=api_key)

    videos_json = json.dumps(
        [{"index": i, **v} for i, v in enumerate(videos)],
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""당신은 베트남 뉴스 큐레이터입니다. 아래 YouTube 영상 목록에서 베트남에 거주하는 한국인에게 가장 유익한 영상 3개를 선별해주세요.

카테고리 우선순위:
1. 경제/비즈니스 (베트남 경제지표, 기업 동향, 외국인 투자, 부동산, 금융)
2. 베트남 정치 (정부 정책, 인사, 법률 변경, 규제)
3. 동남아 국제 정치 (아세안, 미중관계, 지역 분쟁, 외교)
4. 사회 (생활, 문화, 사건사고, 인프라)

선별 규칙:
- 같은 채널에서 최대 1개만 선택 (2개 이상 금지)
- 동일 주제 중복 선택 금지
- 반드시 정확히 3개 선택 (부족하면 차순위 카테고리에서 추가)
- 선택 이유를 한국어로 명확하게 작성

영상 목록:
{videos_json}

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
[
  {{
    "video_id": "영상ID",
    "url": "https://www.youtube.com/watch?v=영상ID",
    "title": "영상 제목",
    "channel": "채널명",
    "duration": "재생시간",
    "category": "카테고리명",
    "reason": "선택 이유 (한국어)"
  }},
  ...
]"""

    with StepTimer(logger, "Claude API 영상 선별"):
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

    response_text = message.content[0].text.strip()

    # JSON 파싱
    json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"Claude 응답에서 JSON을 찾을 수 없음: {response_text}")

    selected = json.loads(json_match.group())
    if len(selected) != 3:
        raise ValueError(f"Claude가 3개가 아닌 {len(selected)}개를 선별했습니다.")

    logger.info(f"Claude 선별 완료: {len(selected)}개")
    for i, v in enumerate(selected, 1):
        logger.info(f"  {i}. [{v['category']}] {v['title']} ({v['channel']}) - {v['reason']}")

    return selected


def run(logger=None) -> list[dict]:
    """YouTube 수집 및 Claude 선별 전체 실행"""
    if logger is None:
        logger = get_logger()

    with StepTimer(logger, "Step 1: YouTube 영상 수집"):
        videos = collect_videos(logger)

    if not videos:
        raise RuntimeError("수집된 영상이 없습니다. 내일 다시 시도하세요.")

    with StepTimer(logger, "Step 2: Claude API 영상 선별"):
        selected = select_videos_with_claude(videos, logger)

    return selected


if __name__ == "__main__":
    load_dotenv("/home/ubuntu/vietnam-podcast/.env")
    logger = get_logger()
    logger.info("=== youtube_collector.py 단독 테스트 ===")
    try:
        result = run(logger)
        print("\n선별된 영상:")
        for i, v in enumerate(result, 1):
            print(f"{i}. {v['title']}")
            print(f"   채널: {v['channel']} | 길이: {v['duration']} | 카테고리: {v['category']}")
            print(f"   URL: {v['url']}")
            print(f"   이유: {v['reason']}")
            print()
    except Exception as e:
        logger.error(f"테스트 실패: {e}", exc_info=True)
        sys.exit(1)
