import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger, StepTimer

NLM_PATH = "/home/ubuntu/.local/bin/nlm"
MAX_RETRIES = 3
POLL_INTERVAL = 30       # 초
MAX_WAIT_SEC = 30 * 60   # 30분

# UUID 패턴
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _run_nlm(args: list[str], timeout: int = 120, logger=None) -> str:
    """nlm CLI 실행 후 stdout 반환. 실패 시 3회 재시도."""
    cmd = [NLM_PATH] + args
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if logger:
                logger.info(f"nlm 실행 (시도 {attempt}/{MAX_RETRIES}): {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            last_error = result.stderr.strip() or result.stdout.strip()
            if logger:
                logger.warning(f"nlm 실패 (시도 {attempt}): {last_error}")
        except subprocess.TimeoutExpired:
            last_error = f"타임아웃 ({timeout}s)"
            if logger:
                logger.warning(f"nlm 타임아웃 (시도 {attempt})")
        except Exception as e:
            last_error = str(e)
            if logger:
                logger.warning(f"nlm 오류 (시도 {attempt}): {e}")

        if attempt < MAX_RETRIES:
            time.sleep(5)

    raise RuntimeError(
        f"nlm 명령 실패 ({MAX_RETRIES}회 재시도 후): {last_error}\n"
        f"명령: {' '.join(cmd)}"
    )


def create_notebook(date_str: str, logger=None) -> str:
    """노트북 생성 후 notebook_id(UUID) 반환.
    출력 예시:
      ✓ Created notebook: 베트남 뉴스 2026-03-02
        ID: 7b19dba2-8f68-4e7f-a844-b5a8cd99519f
    """
    title = f"베트남 뉴스 {date_str}"
    output = _run_nlm(["notebook", "create", title], logger=logger)

    # "ID: UUID" 패턴에서 UUID 추출
    match = re.search(r"ID:\s+(" + UUID_RE.pattern + r")", output)
    if not match:
        raise RuntimeError(f"notebook_id(UUID) 추출 실패. 출력:\n{output}")
    notebook_id = match.group(1)
    if logger:
        logger.info(f"노트북 생성 완료: {notebook_id} ('{title}')")
    return notebook_id


def add_sources(notebook_id: str, youtube_urls: list[str], logger=None) -> None:
    """YouTube URL 3개를 순차적으로 소스로 추가.
    출력 예시:
      ✓ Added source: 제목 (ready)
      Source ID: UUID
    """
    for i, url in enumerate(youtube_urls, 1):
        if logger:
            logger.info(f"소스 추가 {i}/{len(youtube_urls)}: {url}")
        output = _run_nlm(
            ["source", "add", notebook_id, "--url", url, "--wait"],
            timeout=180,
            logger=logger,
        )
        if logger:
            logger.info(f"소스 {i} 추가 완료: {output.splitlines()[1] if len(output.splitlines()) > 1 else output}")


def request_podcast(notebook_id: str, logger=None) -> str:
    """팟캐스트 생성 요청 후 artifact_id(UUID) 반환.
    출력 예시:
      ✓ Audio generation started
        Artifact ID: 24e3385d-e30d-4856-8a8e-7d2ea394f69b
    """
    output = _run_nlm(
        ["audio", "create", notebook_id, "--confirm"],
        timeout=120,
        logger=logger,
    )

    # "Artifact ID: UUID" 패턴에서 UUID 추출
    match = re.search(r"Artifact ID:\s+(" + UUID_RE.pattern + r")", output)
    if not match:
        raise RuntimeError(f"artifact_id(UUID) 추출 실패. 출력:\n{output}")
    artifact_id = match.group(1)
    if logger:
        logger.info(f"팟캐스트 생성 요청 완료: artifact_id={artifact_id}")
    return artifact_id


def wait_for_podcast(notebook_id: str, logger=None) -> str:
    """팟캐스트 생성 완료 폴링. 완료 시 artifact_id 반환.
    studio status 출력 예시 (JSON 배열):
      [{"id": "UUID", "type": "audio", "status": "complete", ...}]
    """
    deadline = time.time() + MAX_WAIT_SEC
    poll_count = 0

    while time.time() < deadline:
        poll_count += 1
        output = _run_nlm(["studio", "status", notebook_id], timeout=60, logger=logger)

        try:
            artifacts = json.loads(output)
        except json.JSONDecodeError:
            if logger:
                logger.warning(f"studio status JSON 파싱 실패: {output[:200]}")
            artifacts = []

        for artifact in artifacts:
            status = artifact.get("status", "")
            artifact_id = artifact.get("id", "")
            if logger:
                logger.info(f"폴링 {poll_count}회: artifact={artifact_id} status={status}")
            if status == "complete" and artifact_id:
                if logger:
                    logger.info(f"팟캐스트 생성 완료: artifact_id={artifact_id}")
                return artifact_id

        remaining = int(deadline - time.time())
        if logger:
            logger.info(f"생성 중... {POLL_INTERVAL}초 후 재확인 (남은 대기: {remaining}s)")
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"팟캐스트 생성 타임아웃 ({MAX_WAIT_SEC // 60}분 초과)")


def download_audio(notebook_id: str, artifact_id: str, date_str: str, logger=None) -> str:
    """오디오 파일 다운로드 후 로컬 경로 반환.
    명령: nlm download audio {notebook_id} --id {artifact_id} --output {path}
    """
    download_dir = os.getenv("PODCAST_DOWNLOAD_DIR", "/tmp/podcasts")
    Path(download_dir).mkdir(parents=True, exist_ok=True)

    date_compact = date_str.replace("-", "")
    output_path = os.path.join(download_dir, f"vietnam_news_{date_compact}.m4a")

    _run_nlm(
        ["download", "audio", notebook_id, "--id", artifact_id, "--output", output_path],
        timeout=300,
        logger=logger,
    )

    if not os.path.exists(output_path):
        raise RuntimeError(f"다운로드 후 파일이 존재하지 않음: {output_path}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    if logger:
        logger.info(f"오디오 다운로드 완료: {output_path} ({size_mb:.1f}MB)")
    return output_path


def run(youtube_urls: list[str], logger=None) -> str:
    """NotebookLM 전체 파이프라인 실행 후 오디오 파일 경로 반환"""
    if logger is None:
        logger = get_logger()

    date_str = datetime.now().strftime("%Y-%m-%d")

    with StepTimer(logger, "Step 3-1: 노트북 생성"):
        notebook_id = create_notebook(date_str, logger)

    with StepTimer(logger, "Step 3-2: 소스 추가"):
        add_sources(notebook_id, youtube_urls, logger)

    with StepTimer(logger, "Step 4-1: 팟캐스트 생성 요청"):
        request_podcast(notebook_id, logger)

    with StepTimer(logger, "Step 4-2: 팟캐스트 완료 대기"):
        artifact_id = wait_for_podcast(notebook_id, logger)

    with StepTimer(logger, "Step 4-3: 오디오 다운로드"):
        audio_path = download_audio(notebook_id, artifact_id, date_str, logger)

    return audio_path


if __name__ == "__main__":
    load_dotenv("/home/ubuntu/vietnam-podcast/.env")
    logger = get_logger()
    logger.info("=== notebook_pipeline.py 단독 테스트 ===")

    test_urls = [
        "https://www.youtube.com/watch?v=ih-2Pcr64zA",
    ]

    try:
        audio_path = run(test_urls, logger)
        print(f"\n다운로드된 오디오: {audio_path}")
    except Exception as e:
        logger.error(f"테스트 실패: {e}", exc_info=True)
        sys.exit(1)
