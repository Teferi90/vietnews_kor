# 🇻🇳 베트남 뉴스 자동 팟캐스트 시스템

베트남에 거주하는 한국인을 위해 매일 베트남 주요 뉴스를 자동으로 수집하고, AI 팟캐스트로 변환하여 Telegram 채널에 배포하는 완전 자동화 시스템입니다.

---

## 시스템 개요

```
[매일 KST 02:00 자동 실행 - cron]
            │
            ▼
┌─────────────────────────┐
│  Step 1                 │
│  YouTube 영상 수집       │  VTV24, Tuổi Trẻ 채널
│  후보 최대 20개 수집     │  YouTube Data API v3
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 2                 │
│  Claude AI 중요도 판단   │  카테고리 우선순위 기반
│  최종 3개 선별           │  Anthropic API
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 3                 │
│  NotebookLM 노트북 생성  │  notebooklm-mcp-cli
│  YouTube 소스 3개 추가   │  nlm CLI
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 4                 │
│  팟캐스트 생성 요청      │  nlm audio create
│  완료 대기 (최대 30분)   │  상태 폴링
│  오디오 파일 다운로드    │  nlm download audio
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Step 5                 │
│  Telegram 채널 발송      │  Bot API
│  오디오 파일 업로드      │  @vietnam_news_kr
└─────────────────────────┘
```

---

## 기술 스택

| 구성요소 | 기술 | 비고 |
|---------|------|------|
| 서버 | AWS EC2 t3.micro Ubuntu 22.04 | 상시 가동 |
| 언어 | Python 3.12 | 가상환경(venv) 사용 |
| YouTube 수집 | YouTube Data API v3 | google-api-python-client |
| 영상 선별 | Anthropic Claude API | claude-sonnet-4-6 |
| 팟캐스트 생성 | NotebookLM | notebooklm-mcp-cli (nlm) |
| 배포 | Telegram Bot API | python-telegram-bot |
| 스케줄링 | cron | 매일 UTC 17:00 (KST 02:00) |

---

## 수집 채널 및 선별 기준

### 수집 채널
| 채널 | URL |
|------|-----|
| VTV24 | https://www.youtube.com/@vtv24 |
| Tuổi Trẻ | https://www.youtube.com/@baotuoitre |

### 수집 조건
- 수집 기준일: 전날 00:00 ~ 23:59 (베트남 시간, UTC+7)
- 영상 길이: 3분 이상 ~ 30분 이하
- 각 채널 최대 10개 → 전체 후보 최대 20개

### Claude 선별 우선순위
1. **경제/비즈니스** - 베트남 경제지표, 기업 동향, 외국인 투자, 부동산, 금융
2. **베트남 정치** - 정부 정책, 인사, 법률 변경, 규제
3. **동남아 국제 정치** - 아세안, 미중관계, 지역 분쟁, 외교
4. **사회** - 생활, 문화, 사건사고, 인프라

> 같은 채널에서 최대 1개, 동일 주제 중복 선택 금지, 반드시 3개 선별

---

## 프로젝트 구조

```
vietnam-podcast/
├── main.py                          # 메인 오케스트레이터
├── run.sh                           # cron 실행 래퍼 스크립트
├── requirements.txt                 # Python 패키지 목록
├── .env                             # 환경변수 (git 제외)
├── collectors/
│   └── youtube_collector.py         # YouTube 수집 및 Claude 선별
├── notebooklm/
│   └── notebook_pipeline.py         # nlm CLI 래퍼 (NotebookLM 파이프라인)
├── distributors/
│   └── telegram_publisher.py        # Telegram 발송
├── utils/
│   └── logger.py                    # 로깅 유틸리티
└── logs/                            # 실행 로그 (날짜별, git 제외)
```

---

## 설치 및 환경 구성

### 1. 사전 요구사항

```bash
# Python 3.10 이상
python3 --version

# uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# notebooklm-mcp-cli 설치
uv tool install notebooklm-mcp-cli

# Google Chrome 설치 (nlm 인증용)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
  | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install -y google-chrome-stable
```

### 2. 프로젝트 클론 및 패키지 설치

```bash
git clone https://github.com/Teferi90/vietnews_kor.git
cd vietnews_kor

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env` 파일을 생성하고 아래 항목을 입력합니다:

```env
# YouTube Data API
YOUTUBE_API_KEY=

# Anthropic Claude API
ANTHROPIC_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=@channel_name

# NotebookLM 인증 확인용
GOOGLE_EMAIL=

# 실행 설정
PODCAST_DOWNLOAD_DIR=/tmp/podcasts
LOG_DIR=/home/ubuntu/vietnam-podcast/logs
```

| 키 | 발급처 |
|----|--------|
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) → YouTube Data API v3 |
| `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com/) |
| `TELEGRAM_BOT_TOKEN` | Telegram [@BotFather](https://t.me/BotFather) |

### 4. NotebookLM 인증

```bash
export PATH="$HOME/.local/bin:$PATH"
nlm login          # Chrome 브라우저로 Google 계정 로그인
nlm login --check  # 인증 상태 확인
```

> 헤드리스 서버 환경에서는 Xvfb + VNC를 사용합니다.
> ```bash
> sudo apt install -y xvfb x11vnc openbox xterm
> Xvfb :1 -screen 0 1280x800x24 &
> DISPLAY=:1 openbox &
> DISPLAY=:1 xterm &
> x11vnc -display :1 -rfbauth ~/.vnc/passwd -rfbport 5900 -forever -shared &
> ```

---

## 실행 방법

### 전체 파이프라인 실행

```bash
source venv/bin/activate
export PATH="$HOME/.local/bin:$PATH"
python main.py
```

### 모듈별 단독 테스트

```bash
# YouTube 수집 + Claude 선별 테스트
python collectors/youtube_collector.py

# NotebookLM 파이프라인 테스트
python notebooklm/notebook_pipeline.py

# Telegram 발송 테스트 (에러 알림)
python distributors/telegram_publisher.py
```

---

## cron 스케줄 등록

```bash
# 매일 KST 02:00 (UTC 17:00) 자동 실행
printf 'CRON_TZ=UTC\n\n0 17 * * * /home/ubuntu/vietnam-podcast/run.sh\n' | crontab -

# 등록 확인
crontab -l
```

---

## Telegram 채널 발송 형식

```
📻 베트남 뉴스 브리핑 | 2026년 03월 02일

오늘의 주요 뉴스 3가지를 한국어로 전해드립니다.

📌 오늘의 뉴스:
  1. 베트남 부동산 전자 신원코드 관리 제도 도입 - VTV24
  2. 부동산 중개 수수료 세금 납부 방식 안내 - Tuổi Trẻ
  3. 중동 분쟁 확산 및 국제 정세 동향 - VTV24

▶️ 아래 오디오를 탭하면 바로 재생됩니다

#베트남뉴스 #한인뉴스 #베트남한국인
```

---

## 로그

- 위치: `logs/YYYYMMDD.log`
- 레벨: INFO / WARNING / ERROR
- 각 Step 시작·완료·소요시간 기록
- 30일 이상 된 로그 자동 삭제
- 파이프라인 실패 시 Telegram 에러 알림 자동 발송

---

## 라이선스

MIT License
