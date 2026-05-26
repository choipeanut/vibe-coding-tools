# vibe-coding-tools

Claude Code 세션 트랜스크립트를 한국어 블로그 포스트로 변환하는 도구 모음입니다.

`parse_transcript.py`는 세션 JSONL 파일을 읽어 막혔던 지점, 전환점, 결과를 포함한 구조화된 마크다운 초안을 stdout에 출력합니다.
`/blog` slash command를 Claude Code 세션 내에서 실행하면 초안이 `~/vibe-coding-drafts/`에 저장되고 (M2부터) Notion에 업로드됩니다.

## 빠른 시작

```
python parse_transcript.py <jsonl_path>
python extract_prompts.py --project <substring> --top 10
```

## 테스트

```
python -m pytest tests/ -v
```
