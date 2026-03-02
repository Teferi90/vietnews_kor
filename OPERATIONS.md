# 운영 가이드 - 베트남 뉴스 자동 팟캐스트 시스템

> 이 문서는 시스템의 일상 운영, 장애 대응, 유지보수, 비용 관리에 필요한 모든 사항을 정리한 운영자 참고 문서입니다.

---

## 목차

1. [일상 운영 체크리스트](#1-일상-운영-체크리스트)
2. [로그 확인 방법](#2-로그-확인-방법)
3. [장애 대응 가이드](#3-장애-대응-가이드)
4. [NotebookLM 재인증](#4-notebooklm-재인증)
5. [API 키 관리](#5-api-키-관리)
6. [비용 관리](#6-비용-관리)
7. [EC2 서버 관리](#7-ec2-서버-관리)
8. [설정 변경 방법](#8-설정-변경-방법)
9. [의존성 업데이트](#9-의존성-업데이트)
10. [보안 관리](#10-보안-관리)
11. [백업 및 복구](#11-백업-및-복구)

---

## 1. 일상 운영 체크리스트

### 매일 확인 (KST 오전 중)
- [ ] Telegram 채널(@vietnam_news_kr)에 오디오가 발송되었는지 확인
- [ ] 발송이 없을 경우 → 로그 확인 후 장애 대응

### 주 1회 확인
- [ ] API 사용량 확인 (YouTube, Anthropic)
- [ ] EC2 디스크 여유 공간 확인
- [ ] 로그 디렉토리 크기 확인

### 월 1회 확인
- [ ] NotebookLM 인증 상태 확인 (`nlm login --check`)
- [ ] Python 패키지 보안 취약점 확인
- [ ] AWS 비용 청구서 확인
- [ ] API 키 만료 여부 확인

---

## 2. 로그 확인 방법

### 오늘 로그 실시간 확인
```bash
cd /home/ubuntu/vietnam-podcast
tail -f logs/$(date +%Y%m%d).log
```

### 특정 날짜 로그 확인
```bash
cat logs/20260302.log
```

### 에러만 필터링
```bash
grep "\[ERROR\]" logs/$(date +%Y%m%d).log
```

### 각 Step 소요시간 확인
```bash
grep -E "\[START\]|\[DONE\]|\[FAIL\]" logs/$(date +%Y%m%d).log
```

### 최근 7일치 에러 한번에 보기
```bash
for f in logs/*.log; do echo "=== $f ==="; grep "\[ERROR\]" "$f"; done
```

### 로그 디렉토리 용량 확인
```bash
du -sh /home/ubuntu/vietnam-podcast/logs/
ls -lh logs/ | tail -10
```

---

## 3. 장애 대응 가이드

### 장애 감지
파이프라인이 실패하면 Telegram 채널에 아래 형식으로 자동 알림이 옵니다:
```
[2026-03-02] 파이프라인 실패
실패 단계: Step 3~4 (NotebookLM)
에러: nlm 명령 실패 (3회 재시도 후): ...
```

---

### Step별 장애 원인 및 해결

#### Step 1~2: YouTube 수집 / Claude 선별 실패

| 증상 | 원인 | 해결 |
|------|------|------|
| `quota exceeded` | YouTube API 일일 할당량 초과 | 다음날 자동 복구. 할당량 증설 신청 고려 |
| `YOUTUBE_API_KEY 미설정` | .env 파일 누락 | `.env` 파일 확인 및 키 입력 |
| `채널을 찾을 수 없음` | 채널 핸들 변경됨 | YouTube에서 최신 핸들 확인 후 코드 수정 |
| `수집된 영상이 없습니다` | 해당 날짜 영상 없음 (공휴일 등) | 정상 상황. 다음날 자동 실행 대기 |
| `anthropic.AuthenticationError` | Anthropic API 키 오류 | `.env`의 `ANTHROPIC_API_KEY` 확인 |

```bash
# Step 1~2만 단독 테스트
source venv/bin/activate && python collectors/youtube_collector.py
```

---

#### Step 3~4: NotebookLM 파이프라인 실패

| 증상 | 원인 | 해결 |
|------|------|------|
| `Authentication failed` | NotebookLM 인증 만료 | [4번 항목](#4-notebooklm-재인증) 참고하여 재인증 |
| `Failed to add url source` | YouTube URL 접근 불가 (지역 제한 등) | 다른 영상으로 교체 후 수동 실행 |
| `TimeoutError: 팟캐스트 생성 타임아웃` | NotebookLM 서버 지연 | 잠시 후 수동 재실행 |
| `nlm: command not found` | PATH 설정 문제 | `export PATH="/home/ubuntu/.local/bin:$PATH"` 확인 |
| `No sources found` | 소스 추가 실패 후 audio create 시도 | 로그에서 소스 추가 실패 원인 확인 |

```bash
# nlm 인증 상태 확인
export PATH="/home/ubuntu/.local/bin:$PATH"
nlm login --check

# NotebookLM에 생성된 노트북 목록 확인
nlm notebook list
```

---

#### Step 5: Telegram 발송 실패

| 증상 | 원인 | 해결 |
|------|------|------|
| `Unauthorized` | Bot 토큰 오류 | `.env`의 `TELEGRAM_BOT_TOKEN` 확인 |
| `Chat not found` | 채널 ID 오류 또는 봇이 채널 관리자가 아님 | 채널에서 봇 관리자 권한 확인 |
| `Request Entity Too Large` | 파일 50MB 초과 | 코드가 자동으로 `send_document()`로 전환됨 |
| `Timed out` | 네트워크 지연 | 잠시 후 수동 재실행 |

```bash
# Telegram 봇 연결 테스트 (에러 알림 발송)
source venv/bin/activate && python distributors/telegram_publisher.py
```

---

### 수동 파이프라인 재실행

```bash
cd /home/ubuntu/vietnam-podcast
source venv/bin/activate
export PATH="/home/ubuntu/.local/bin:$PATH"
python main.py
```

---

## 4. NotebookLM 재인증

NotebookLM 쿠키는 **약 3~6개월** 후 만료됩니다.
만료 시 `Authentication failed` 에러가 발생합니다.

### 재인증 절차

**1단계: Xvfb + VNC 서버 시작**

```bash
# 이미 실행 중인지 확인
ps aux | grep -E "Xvfb|x11vnc" | grep -v grep

# 실행 중이 아니면 아래 명령 실행
Xvfb :1 -screen 0 1280x800x24 &
DISPLAY=:1 openbox &
DISPLAY=:1 xterm &
x11vnc -display :1 -rfbauth ~/.vnc/passwd -rfbport 5900 -forever -shared &
```

**2단계: VNC 클라이언트로 접속**

- 호스트: EC2 Public IP
- 포트: `5900`
- 비밀번호: `vnc1234`

> EC2 보안그룹에서 5900 포트가 열려 있어야 합니다.

**3단계: VNC 터미널에서 재인증**

```bash
export PATH="/home/ubuntu/.local/bin:$PATH"
nlm login --clear    # 기존 인증 초기화 후 재로그인
```

**4단계: 인증 확인**

```bash
nlm login --check
# ✓ Authentication valid! 메시지 확인
```

### VNC 비밀번호 변경이 필요한 경우
```bash
x11vnc -storepasswd 새비밀번호 ~/.vnc/passwd
```

---

## 5. API 키 관리

### YouTube Data API v3

- **무료 할당량**: 10,000 units/일
- **본 시스템 소비량**: 약 100~300 units/회 (채널 검색 + 영상 상세 조회)
- **할당량 확인**: [Google Cloud Console](https://console.cloud.google.com/) → API 및 서비스 → 할당량
- **키 갱신**: Google Cloud Console → 사용자 인증 정보 → API 키 재생성 후 `.env` 업데이트

### Anthropic Claude API

- **요금**: 입력 토큰 + 출력 토큰 기준 (claude-sonnet-4-6)
- **본 시스템 소비량**: 약 1,000~2,000 토큰/회
- **사용량 확인**: [Anthropic Console](https://console.anthropic.com/) → Usage
- **키 갱신**: Anthropic Console → API Keys → 새 키 생성 후 `.env` 업데이트

### Telegram Bot Token

- **만료 없음** (수동 폐기 전까지 유효)
- **봇 관리**: [@BotFather](https://t.me/BotFather)에서 `/mybots` 명령으로 관리
- **토큰 재발급**: BotFather → 봇 선택 → API Token → Revoke current token

### API 키 교체 절차
```bash
# .env 파일 수정
nano /home/ubuntu/vietnam-podcast/.env

# 변경 후 테스트 실행으로 확인
source venv/bin/activate
python collectors/youtube_collector.py   # YouTube + Claude 확인
python distributors/telegram_publisher.py  # Telegram 확인
```

---

## 6. 비용 관리

### 월간 예상 비용

| 항목 | 비용 | 비고 |
|------|------|------|
| AWS EC2 t3.micro | ~$10/월 | 온디맨드 기준. 예약 인스턴스로 절감 가능 |
| YouTube Data API | 무료 | 10,000 units/일 무료 할당량 내 |
| Anthropic Claude API | ~$1~3/월 | 일 1회 실행, 약 2,000토큰 기준 |
| NotebookLM | 무료 | Google 계정 무료 한도 내 |
| Telegram Bot API | 무료 | |
| **합계** | **~$11~13/월** | |

### 비용 절감 팁
- EC2를 **예약 인스턴스**(1년)로 전환 시 약 40% 절감
- Anthropic API는 **claude-haiku** 모델로 교체 시 비용 약 10배 절감 (선별 품질은 다소 낮아질 수 있음)
- YouTube API 할당량이 부족하면 Google Cloud 프로젝트를 추가하여 할당량 확장

### AWS 비용 알람 설정 권장
```
AWS Console → Billing → Budgets → 월 $20 초과 시 이메일 알람 설정
```

---

## 7. EC2 서버 관리

### 서버 재시작 후 복구 절차

EC2 인스턴스가 재시작되면 cron은 자동 복구되지만, **VNC 서버는 수동으로 재시작**해야 합니다.

```bash
# cron 정상 동작 확인
crontab -l
sudo systemctl status cron

# VNC 재시작 (nlm login 재인증이 필요할 때만)
Xvfb :1 -screen 0 1280x800x24 &
DISPLAY=:1 openbox &
DISPLAY=:1 xterm &
x11vnc -display :1 -rfbauth ~/.vnc/passwd -rfbport 5900 -forever -shared &
```

### 디스크 공간 관리

```bash
# 전체 디스크 사용량 확인
df -h

# 팟캐스트 임시 파일 확인 (발송 후 자동 삭제되나 실패 시 잔류 가능)
ls -lh /tmp/podcasts/ 2>/dev/null

# 잔류 파일 수동 삭제
rm -f /tmp/podcasts/*.m4a /tmp/podcasts/*.mp3

# 로그 수동 정리 (30일치 초과분)
find /home/ubuntu/vietnam-podcast/logs/ -name "*.log" -mtime +30 -delete
```

### 서버 리소스 모니터링

```bash
# CPU / 메모리 확인
top -bn1 | head -20

# 실행 중인 관련 프로세스 확인
ps aux | grep -E "python|nlm|Xvfb|x11vnc" | grep -v grep
```

### cron 재등록 (초기화된 경우)

```bash
printf 'CRON_TZ=UTC\n\n0 17 * * * /home/ubuntu/vietnam-podcast/run.sh\n' | crontab -
crontab -l  # 확인
```

---

## 8. 설정 변경 방법

### 수집 채널 추가/변경

`collectors/youtube_collector.py` 상단의 `CHANNELS` 리스트를 수정합니다:

```python
CHANNELS = [
    {"name": "VTV24", "handle": "@vtv24"},
    {"name": "Tuổi Trẻ", "handle": "@baotuoitre"},
    # 채널 추가 예시:
    {"name": "VnExpress", "handle": "@vnexpress"},
]
```

### Claude 선별 기준 변경

`collectors/youtube_collector.py`의 `select_videos_with_claude()` 함수 내 프롬프트를 수정합니다. 카테고리 우선순위, 선별 규칙, 반환 개수 등을 조정할 수 있습니다.

### 발송 시간 변경

```bash
# crontab 편집
crontab -e

# 예: KST 07:00 (UTC 22:00)으로 변경
# 0 17 * * *  →  0 22 * * *
```

### Telegram 메시지 형식 변경

`distributors/telegram_publisher.py`의 `_build_caption()` 함수를 수정합니다.

### 팟캐스트 생성 대기 시간 변경

`notebooklm/notebook_pipeline.py` 상단 상수를 수정합니다:

```python
POLL_INTERVAL = 30       # 폴링 간격 (초)
MAX_WAIT_SEC = 30 * 60   # 최대 대기 시간 (초)
```

---

## 9. 의존성 업데이트

### 현재 주요 패키지 버전 확인

```bash
source /home/ubuntu/vietnam-podcast/venv/bin/activate
pip list | grep -E "anthropic|google-api|python-telegram-bot|python-dotenv"
```

### 패키지 업데이트

```bash
source venv/bin/activate

# 특정 패키지만 업데이트
pip install --upgrade anthropic
pip install --upgrade python-telegram-bot

# requirements.txt 최신화
pip freeze | grep -E "google-api-python-client|google-auth|anthropic|python-telegram-bot|python-dotenv|requests" > requirements.txt
```

### nlm (notebooklm-mcp-cli) 업데이트

```bash
export PATH="/home/ubuntu/.local/bin:$PATH"
nlm --version           # 현재 버전 확인
uv tool upgrade notebooklm-mcp-cli  # 업데이트
nlm --version           # 업데이트 후 버전 확인
```

> 업데이트 후 반드시 `nlm login --check`로 인증 상태 재확인

### 업데이트 후 테스트

```bash
cd /home/ubuntu/vietnam-podcast
source venv/bin/activate
python -c "from collectors.youtube_collector import run; from notebooklm.notebook_pipeline import run; from distributors.telegram_publisher import publish; print('모든 모듈 import 정상')"
```

---

## 10. 보안 관리

### .env 파일 보안

```bash
# 권한 확인 (소유자만 읽기/쓰기여야 함)
ls -la /home/ubuntu/vietnam-podcast/.env
# -rw------- 이어야 함

# 권한 재설정
chmod 600 /home/ubuntu/vietnam-podcast/.env
```

### EC2 보안그룹 관리

| 포트 | 용도 | 권장 설정 |
|------|------|----------|
| 22 (SSH) | 서버 접속 | **내 IP만 허용** (0.0.0.0/0 금지) |
| 5900 (VNC) | NotebookLM 재인증 시에만 사용 | 평소 **닫아두고** 재인증 필요 시만 오픈 |

> VNC(5900)는 사용하지 않을 때 반드시 보안그룹에서 닫아두세요.

### API 키 노출 방지

- `.env` 파일은 절대 git에 커밋하지 않습니다 (`.gitignore`에 포함됨)
- API 키가 노출된 경우 즉시 해당 서비스에서 키를 폐기하고 재발급합니다
- GitHub에 실수로 키가 올라간 경우:
  1. 해당 키 즉시 폐기 (각 서비스 콘솔에서)
  2. 새 키 발급 후 `.env` 업데이트
  3. git history에서 민감 정보 제거: `git filter-branch` 또는 `BFG Repo Cleaner` 사용

### GitHub 저장소 접근 관리

```bash
# GitHub PAT 갱신 시 credential 업데이트
echo "https://Teferi90:새_PAT_토큰@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials
```

---

## 11. 백업 및 복구

### 백업 대상

| 항목 | 위치 | 중요도 |
|------|------|--------|
| 코드 | GitHub (자동) | 높음 |
| .env (API 키) | 로컬 PC에 별도 보관 권장 | 매우 높음 |
| nlm 인증 쿠키 | `~/.config/notebooklm-mcp-cli/` | 중간 |

### .env 파일 백업

```bash
# 로컬 PC로 복사 (SSH 사용 시)
scp ubuntu@EC2_IP:/home/ubuntu/vietnam-podcast/.env ./env_backup.txt
```

### 전체 복구 절차 (새 EC2에서)

```bash
# 1. 코드 클론
git clone https://github.com/Teferi90/vietnews_kor.git
cd vietnews_kor

# 2. 환경 구성
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
uv tool install notebooklm-mcp-cli
sudo apt install -y google-chrome-stable xvfb x11vnc openbox xterm python3.12-venv

# 3. Python 패키지 설치
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 4. .env 파일 복원 (백업본 업로드)
nano .env   # API 키 입력

# 5. NotebookLM 재인증
Xvfb :1 -screen 0 1280x800x24 &
DISPLAY=:1 openbox &
DISPLAY=:1 xterm &
x11vnc -display :1 -rfbauth ~/.vnc/passwd -rfbport 5900 -forever &
# VNC 접속 후 nlm login 실행

# 6. cron 등록
printf 'CRON_TZ=UTC\n\n0 17 * * * /home/ubuntu/vietnam-podcast/run.sh\n' | crontab -

# 7. 테스트 실행
python main.py
```

---

## 빠른 참조

```bash
# 파이프라인 수동 실행
cd /home/ubuntu/vietnam-podcast && source venv/bin/activate && export PATH="/home/ubuntu/.local/bin:$PATH" && python main.py

# 오늘 로그 확인
tail -50 /home/ubuntu/vietnam-podcast/logs/$(date +%Y%m%d).log

# nlm 인증 상태 확인
export PATH="/home/ubuntu/.local/bin:$PATH" && nlm login --check

# cron 확인
crontab -l

# 디스크 확인
df -h && du -sh /home/ubuntu/vietnam-podcast/logs/
```
