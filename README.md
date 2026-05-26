# vibe-coding-tools

Claude Code 세션 트랜스크립트를 한국어 블로그 포스트로 자동 변환하고 Notion에 발행하는 도구 모음입니다.

---

## 포함된 도구

| 파일 | 역할 |
|------|------|
| `parse_transcript.py` | 세션 JSONL → 구조화된 JSON 추출 |
| `extract_prompts.py` | history.jsonl에서 베스트 프롬프트 추출 |
| `filters.py` | 공통 상수 (STUCK_WORDS 등) |
| `claude/commands/blog.md` | `/blog` slash command 정의 |
| `claude/hooks/archive_session.py` | 세션 종료 시 transcript 자동 보관 훅 |
| `install.ps1` | 새 컴퓨터 설치 스크립트 |

---

## 새 컴퓨터에 설치하기

### 사전 조건

- Windows + PowerShell 5.1 이상
- [Python 3.8+](https://www.python.org/downloads/) (PATH 등록 필수)
- [Claude Code](https://claude.ai/download) 설치
- Notion MCP 연결 (아래 참고)

---

### 1단계 — 레포 클론

```powershell
git clone https://github.com/choipeanut/vibe-coding-tools.git $env:USERPROFILE\vibe-coding-tools
```

> 반드시 `%USERPROFILE%\vibe-coding-tools` 경로에 클론해야 `/blog`가 `parse_transcript.py`를 찾을 수 있습니다.

---

### 2단계 — 설치 스크립트 실행

```powershell
cd $env:USERPROFILE\vibe-coding-tools
.\install.ps1
```

스크립트가 자동으로 처리하는 것:

- `/blog` slash command → `%USERPROFILE%\.claude\commands\blog.md` 복사
- SessionEnd 훅 → `%USERPROFILE%\.claude\hooks\archive_session.py` 복사
- `%USERPROFILE%\.claude\settings.json` 에 훅 자동 등록

성공 시 출력:

```
=== vibe-coding-tools installer ===
[1/5] Checking Python...      OK: Python 3.x.x
[2/5] Checking repo location... OK
[3/5] Installing /blog command... OK
[4/5] Installing SessionEnd hook... OK
[5/5] Registering hook in settings.json... OK
=== Installation complete ===
```

---

### 3단계 — Notion MCP 연결

1. Claude Code 실행
2. 좌측 사이드바 **Settings → MCP** 탭
3. **Notion** 커넥터 추가 → Notion 계정으로 로그인
4. `바이브 코딩 일지` 데이터베이스 접근 권한 허용

> Notion DB(`바이브 코딩 일지`)는 이미 `choipeanut`의 Notion에 존재합니다.  
> 같은 Notion 계정으로 로그인하면 별도 DB 생성 없이 바로 업로드됩니다.

---

### 4단계 — Claude Code 재시작 후 /blog 실행

```
Claude Code 재시작 → 아무 프로젝트에서 /blog 입력
```

---

## 사용법

### /blog — 세션 → Notion 자동 발행

Claude Code 세션 중 언제든지:

```
/blog
```

1. 가장 최근 transcript 자동 탐색
2. 세션 데이터 JSON 추출
3. Claude가 한국어 블로그 포스트 작성 (프롬프트 전문가 버전으로 다듬기 포함)
4. `%USERPROFILE%\vibe-coding-drafts\YYYY-MM-DD_HHMM.md` 로컬 저장
5. Notion `바이브 코딩 일지` DB에 자동 업로드

---

### parse_transcript.py — 트랜스크립트 직접 파싱

```powershell
# 마크다운 출력
python parse_transcript.py <jsonl_path>

# 구조화된 JSON 출력 (/blog 내부에서 사용)
python parse_transcript.py <jsonl_path> --json
```

---

### extract_prompts.py — 베스트 프롬프트 추출

```powershell
# 프로젝트명 기준 top 10 출력 (마크다운)
python extract_prompts.py --project myproject --top 10

# JSON 형식
python extract_prompts.py --project myproject --top 10 --format json

# 날짜 필터
python extract_prompts.py --project myproject --since 2026-01-01
```

---

## 테스트

```powershell
cd $env:USERPROFILE\vibe-coding-tools
python -m pytest tests/ -v
```

---

## 업데이트

이 컴퓨터에서 변경 후 다른 컴퓨터에 반영:

```powershell
# 변경 사항 push (이 컴퓨터)
cd $env:USERPROFILE\vibe-coding-tools
git add .
git commit -m "update"
git push

# 다른 컴퓨터에서 pull + 재설치
cd $env:USERPROFILE\vibe-coding-tools
git pull
.\install.ps1
```
