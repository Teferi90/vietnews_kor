import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path


def get_logger(name: str = "vietnam-podcast") -> logging.Logger:
    log_dir = os.getenv("LOG_DIR", "/home/ubuntu/vietnam-podcast/logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"{today}.log")

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _cleanup_old_logs(log_dir, days=30)

    return logger


def _cleanup_old_logs(log_dir: str, days: int = 30) -> None:
    cutoff = datetime.now() - timedelta(days=days)
    for log_file in Path(log_dir).glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                log_file.unlink()
        except OSError:
            pass


class StepTimer:
    """각 Step의 시작/완료/소요시간을 로그에 기록하는 컨텍스트 매니저."""

    def __init__(self, logger: logging.Logger, step_name: str):
        self.logger = logger
        self.step_name = step_name
        self.start_time: float = 0.0

    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"[START] {self.step_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        if exc_type is None:
            self.logger.info(f"[DONE]  {self.step_name} (소요: {elapsed:.1f}s)")
        else:
            self.logger.error(
                f"[FAIL]  {self.step_name} (소요: {elapsed:.1f}s)",
                exc_info=True,
            )
        return False


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("/home/ubuntu/vietnam-podcast/.env")

    logger = get_logger()
    logger.info("Logger 초기화 테스트")
    logger.warning("경고 메시지 테스트")
    logger.error("에러 메시지 테스트")

    with StepTimer(logger, "Step 테스트"):
        time.sleep(0.5)

    print("logger.py 단독 테스트 완료")
