---
description: 세션 데이터를 분석해 한국어 바이브 코딩 블로그 포스트를 작성하고 Notion에 업로드
---

세션 데이터를 분석해서 전문적인 한국어 바이브 코딩 블로그 포스트를 직접 작성하고 Notion에 업로드한다.

> **OS 자동 판단**: Windows(로컬)면 PowerShell, Linux/Mac(클라우드 세션 VM)이면 bash 블록을 쓴다. 한쪽이 실패하면 다른 쪽을 시도한다.

---

## Step 1 — transcript 찾기

**Windows (PowerShell):**
```powershell
$cwd = (Get-Location).Path
$cwdEnc = $cwd -replace '[\\:/\s]', '-' -replace '-+', '-'
$transcript = Get-ChildItem "$env:USERPROFILE\.claude\projects\$cwdEnc\*.jsonl" -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $transcript) {
    $transcript = Get-ChildItem "$env:USERPROFILE\.claude\projects\*\*.jsonl" -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $transcript) { Write-Host "transcript를 찾지 못했습니다."; exit 0 }
Write-Host $transcript
```

**Linux/Mac (bash):**
```bash
transcript=$(ls -t "$HOME/.claude/projects/"*/*.jsonl 2>/dev/null | head -1)
if [ -z "$transcript" ]; then echo "transcript를 찾지 못했습니다."; exit 0; fi
echo "$transcript"
```

찾은 transcript 경로를 보여주고 "이 transcript로 진행할까요?" 확인을 받는다.

---

## Step 2 — 세션 데이터 추출

확인 후 실행:

**Windows (PowerShell):**
```powershell
$data = python "$env:USERPROFILE\vibe-coding-tools\parse_transcript.py" $transcript --json
Write-Host $data
```

**Linux/Mac (bash):**
```bash
python3 "$HOME/vibe-coding-tools/parse_transcript.py" "$transcript" --json
```

`too_short: true`이면 "이 세션은 블로그로 올리기에는 프롬프트/수정 내용이 너무 적습니다."라고 한국어로 알리고 종료한다.

---

## Step 3 — 블로그 글 직접 작성 (Claude가 담당)

추출된 JSON 데이터를 바탕으로 아래 형식에 맞게 **처음부터** 한국어 블로그 포스트를 작성한다.

### 작성 규칙

**프롬프트 다듬기**: `steps[].prompt`의 원본 텍스트(예: "ㅇㅇ", "여기 있는 md에 맞춰서 개발해.")를 그대로 쓰지 말고, 해당 단계에서 실제로 일어난 일과 파일 변경 내역을 보고 **전문 개발자가 처음부터 작성했을 법한 명확한 프롬프트**로 재작성한다.

**예시**:
- 원본 `"ㅇㅇ"` (다음 단계로 진행 승인) → `"M1 로컬 초안 품질 확인 완료. T5(Notion 스키마 확인)로 진행해줘."`
- 원본 `"여기 있는 md에 맞춰서 개발해."` → `"AGENTS.md, TASKS.md, TRANSCRIPT_SPEC.md 명세를 읽고 T1부터 순서대로 vibe-coding-tools 레포를 구현해줘. Python stdlib만 사용하고, 각 태스크 완료 후 검증 명령어를 실행해줘."`

**단계 제목**: 각 step에 짧은 한국어 제목을 붙인다 (예: "레포 초기화 및 fixture 생성", "파서 구현 및 테스트").

**막혔던 지점**: `stuck_pairs`가 비어 있으면 해당 섹션을 생략한다.

**전환점**: `turning_point`가 null이면 해당 섹션을 생략한다.

### 출력 형식

```markdown
# {project} — {한 줄 핵심 요약, 40자 이내}

> {datetime} · 프롬프트 {prompt_count}개 · 파일 {edit_count}개 수정 · {duration}

## 목표
{이 세션에서 무엇을 만들었는지 2-3문장 요약}

## 개발 과정

### 1. {단계 제목}
**프롬프트:** "{다듬어진 전문 프롬프트}"
**변경 파일:** {files_changed 목록, 없으면 생략}

### 2. {단계 제목}
...

(모든 steps에 대해 반복)

## 막혔던 지점  ← stuck_pairs가 있을 때만
...

## 전환점  ← turning_point가 있을 때만
...

## 결과물
- 수정/생성된 파일: {all_files, 최대 10개. 초과 시 "외 N개"}
- 가장 많이 수정된 파일: {hottest_file} ({hottest_file_count}회)

## 회고
{이 세션의 핵심 패턴 1-2문장. 다음에 같은 작업 시 쓸 수 있는 시작 프롬프트 템플릿 1개를 코드블록으로.}

---

*세션 ID: `{session_id}` · 원본 transcript: `{transcript_path}`*
```

---

## Step 4 — 로컬 파일 저장

작성한 마크다운을 저장:

**Windows (PowerShell):**
```powershell
$draftDir = "$env:USERPROFILE\vibe-coding-drafts"
New-Item -ItemType Directory -Force -Path $draftDir | Out-Null
$draftPath = Join-Path $draftDir "$(Get-Date -Format 'yyyy-MM-dd_HHmm').md"
# 작성한 마크다운을 $draftPath에 저장
```

**Linux/Mac (bash):**
```bash
mkdir -p "$HOME/vibe-coding-drafts"
draftPath="$HOME/vibe-coding-drafts/$(date +%Y-%m-%d_%H%M).md"
# 작성한 마크다운을 $draftPath에 저장
```

---

## Step 5 — Notion 업로드

저장한 마크다운의 properties를 추출해 `mcp__notion__create-pages`를 호출한다:
- **parent**: data_source_id = `8ea0ceb0-f6f0-461e-acdd-f6a82af327da`
- **Title**: 첫 H1 (`# ` 제거)
- **`date:Date:start`**: JSON의 `date` 필드 (`YYYY-MM-DD`)
- **Project**: `project` 값을 `asset` / `AI-Term` / `NotionGenerator` 중 매핑, 없으면 `etc`
- **Tags**: 편집된 파일 확장자 기반 — `.py`→`python`, `.tsx/.jsx`→`react`, `.html`→`web`, `.md`→`docs`, `.ipynb`→`notebook`. 항상 `vibe-coding` 포함. JSON 배열 형식.
- **Status**: `"Draft"`
- **Source Session ID**: `session_id`
- **content**: H1 이후 전체 마크다운 본문

MCP 오류 시:
1. `$env:USERPROFILE\.claude\hooks\errors.log`에 추가: `{ISO timestamp}\tnotion_upload_failed\t{error}\t{draftPath}`
2. 사용자에게: "노션 업로드 실패, 로컬에 저장됨: `{draftPath}`"

---

## Step 6 — 결과 보고

성공 시:
```
노션 페이지 생성됨: {url}
로컬 초안: {draftPath}
```

작성한 글의 `## 개발 과정` 섹션을 미리보기로 보여준다.
