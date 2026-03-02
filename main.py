import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from collectors.youtube_collector import run as collect_and_select
from distributors.telegram_publisher import publish, send_error_notification
from notebooklm.notebook_pipeline import run as run_notebooklm
from utils.logger import StepTimer, get_logger

REQUIRED_ENV = [
    "YOUTUBE_API_KEY",
    "ANTHROPIC_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHANNEL_ID",
]


def validate_env() -> None:
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        raise EnvironmentError(f"필수 환경변수 누락: {', '.join(missing)}")


def main() -> None:
    logger = get_logger()
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"{'='*50}")
    logger.info(f"파이프라인 시작: {today}")
    logger.info(f"{'='*50}")

    selected_videos = None
    failed_step = None

    try:
        # Step 0: 환경변수 검증
        with StepTimer(logger, "Step 0: 환경변수 검증"):
            validate_env()

        # Step 1~2: YouTube 수집 및 Claude 선별
        with StepTimer(logger, "Step 1~2: YouTube 수집 및 선별"):
            selected_videos = collect_and_select(logger)

        # Step 3~4: NotebookLM 파이프라인
        youtube_urls = [v["url"] for v in selected_videos]
        with StepTimer(logger, "Step 3~4: NotebookLM 파이프라인"):
            failed_step = "Step 3~4 (NotebookLM)"
            audio_path = run_notebooklm(youtube_urls, logger)

        # Step 5: Telegram 발송
        with StepTimer(logger, "Step 5: Telegram 발송"):
            failed_step = "Step 5 (Telegram)"
            publish(audio_path, selected_videos, logger)

        logger.info(f"{'='*50}")
        logger.info("파이프라인 완료!")
        logger.info(f"{'='*50}")

    except Exception as e:
        step_label = failed_step or "Step 1~2 (YouTube/Claude)"
        error_detail = traceback.format_exc()
        logger.error(f"파이프라인 실패 - {step_label}: {e}")
        logger.error(error_detail)

        error_msg = f"실패 단계: {step_label}\n에러: {e}"
        send_error_notification(error_msg, logger)
        sys.exit(1)


if __name__ == "__main__":
    main()
