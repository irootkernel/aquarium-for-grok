# Aquarium for Grok

Grok 플러그인 마켓플레이스로 패키징한 Aquarium 개발 스킬입니다. 이 저장소는 **생성 산출물**입니다. 원본은 [irootkernel/aquarium](https://github.com/irootkernel/aquarium) Codex 플러그인이며, 여기서는 서브모듈로 고정한 뒤 `scripts/sync.py`가 변환합니다.

[English](README.md) · 한국어

[Root Kernel](https://home.rootkernel.xyz) · 지원: [cs@rootkernel.xyz](mailto:cs@rootkernel.xyz)

설치, 스킬 표, 생성 모델, 업그레이드, 검증은 [영어 README](README.md)와 같습니다. 문서의 `/aquarium:<skill>`은 플러그인 한정 이름입니다. 설치 후 실제 입력은 `grok inspect --json`이 보고하는 형식(충돌이 없으면 `/<skill>`, 있으면 `/aquarium:<skill>`)을 따릅니다. Independent Review는 이 호스트에서 Grok `spawn_subagent` native 경로이며 Dolgorae를 쓰지 않습니다. `/aquarium:mulgae-review`는 핸들러 밖의 단독 Mulgae 검토입니다. Humanizer와 `humanize-korean`은 `~/.agents/skills/`에 설치하고 진단합니다. 개발 채널은 스킬이 아니라 플러그인 `.mcp.json`과 `tools/aquarium-dev/`입니다. Aquarium 플러그인 설치·업데이트는 `grok plugin` 마켓플레이스 흐름입니다.
