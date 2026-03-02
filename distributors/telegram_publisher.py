import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import telegram
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger, StepTimer

MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024  # 50MB
SEND_TIMEOUT = 120


def _build_caption(selected_videos: list[dict]) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    lines = [
        f"📻 베트남 뉴스 브리핑 | {today}",
        "",
        "오늘의 주요 뉴스 3가지를 한국어로 전해드립니다.",
        "",
        "📌 오늘의 뉴스:",
    ]
    for i, v in enumerate(selected_videos, 1):
        lines.append(f"  {i}. {v['reason']} - {v['channel']}")

    lines += [
        "",
        "▶️ 아래 오디오를 탭하면 바로 재생됩니다",
        "",
        "#베트남뉴스 #한인뉴스 #베트남한국인",
    ]
    return "\n".join(lines)


async def _send(bot: telegram.Bot, channel_id: str, audio_path: str, caption: str, logger=None) -> None:
    file_size = os.path.getsize(audio_path)

    with open(audio_path, "rb") as f:
        if file_size <= MAX_AUDIO_SIZE_BYTES:
            if logger:
                logger.info(f"send_audio() 사용 ({file_size / 1024 / 1024:.1f}MB)")
            await bot.send_audio(
                chat_id=channel_id,
                audio=f,
                caption=caption,
                read_timeout=SEND_TIMEOUT,
                write_timeout=SEND_TIMEOUT,
                connect_timeout=30,
            )
        else:
            if logger:
                logger.warning(f"파일 크기 초과({file_size / 1024 / 1024:.1f}MB) → send_document() 사용")
            await bot.send_document(
                chat_id=channel_id,
                document=f,
                caption=caption,
                read_timeout=SEND_TIMEOUT,
                write_timeout=SEND_TIMEOUT,
                connect_timeout=30,
            )


def publish(audio_path: str, selected_videos: list[dict], logger=None) -> None:
    """Telegram 채널에 오디오 파일과 뉴스 요약 발송"""
    if logger is None:
        logger = get_logger()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not channel_id:
        raise ValueError("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHANNEL_ID가 설정되지 않았습니다.")

    if not Path(audio_path).exists():
        raise FileNotFoundError(f"오디오 파일이 없습니다: {audio_path}")

    caption = _build_caption(selected_videos)
    bot = telegram.Bot(token=token)

    with StepTimer(logger, "Step 5: Telegram 발송"):
        asyncio.run(_send(bot, channel_id, audio_path, caption, logger))

    logger.info("Telegram 발송 완료. 임시 파일 삭제 중...")
    try:
        os.remove(audio_path)
        logger.info(f"임시 파일 삭제: {audio_path}")
    except OSError as e:
        logger.warning(f"임시 파일 삭제 실패: {e}")


async def _send_text(bot: telegram.Bot, channel_id: str, text: str) -> None:
    await bot.send_message(chat_id=channel_id, text=text)


def send_error_notification(error_msg: str, logger=None) -> None:
    """파이프라인 실패 시 Telegram으로 에러 알림 발송"""
    if logger is None:
        logger = get_logger()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not channel_id:
        logger.warning("Telegram 설정 없음 - 에러 알림 발송 불가")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    text = f"[{today}] 파이프라인 실패\n{error_msg}"

    try:
        bot = telegram.Bot(token=token)
        asyncio.run(_send_text(bot, channel_id, text))
        logger.info("에러 알림 발송 완료")
    except Exception as e:
        logger.error(f"에러 알림 발송 실패: {e}")


if __name__ == "__main__":
    load_dotenv("/home/ubuntu/vietnam-podcast/.env")
    logger = get_logger()
    logger.info("=== telegram_publisher.py 단독 테스트 ===")

    # 테스트: 에러 알림 발송
    try:
        send_error_notification("실패 단계: 테스트\n에러: 단독 테스트 메시지", logger)
        print("에러 알림 테스트 발송 완료")
    except Exception as e:
        logger.error(f"테스트 실패: {e}", exc_info=True)
        sys.exit(1)
