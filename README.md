# ⚽ Football Recording

축구 영상을 보며 경기 중 주요 장면을 기록하고, 선수별 이벤트를 태깅할 수 있는 데스크탑 분석 도구입니다.

---

## 📌 주요 기능

- **영상 재생 및 탐색** — MP4, MKV, MOV 등 다양한 포맷 지원, 타임라인 기반 장면 이동
- **이벤트 태깅** — 패스, 슈팅, 골, 드리블 등 다양한 액션을 선수별로 기록
- **북마크** — 중요한 장면을 즉시 저장하고 스크린샷 캡처 및 자동 클립(전후 5초) 생성
- **선수 명단 자동 로딩** — FotMob 연동으로 홈/어웨이 선수 명단을 경기 시간대에 맞춰 불러오기
- **프로젝트 저장 및 불러오기** — 분석 내용을 파일로 저장하고 이어서 작업 가능

---

## 🚀 업데이트 내역

### v1.1.2 (2026-04-18)
**✨ 신규 기능 및 편의성 개선**
- **프로젝트 타임라인 시점 보존:** 프로젝트를 다시 불러올 때, 마지막으로 저장했던 타임라인 위치가 그대로 유지됩니다.
- **과거 시즌 명단 데이터 지원:** 2024-25 시즌 이전 경기도 FotMob을 통해 선수 명단을 정상적으로 불러올 수 있습니다.

---

### v1.1.1 (2026-04-17)
**🛠️ 버그 수정 및 개선**
- **북마크 시각적 식별성 강화:** 타임라인과 리스트에서 북마크가 일반 마커와 명확히 구분되도록 표시 방식을 개선했습니다.
- **단축키 로직 정상화:** 특정 상황에서 단축키 `2`를 누르면 의도와 무관하게 북마크가 선택되던 버그를 수정했습니다.
- **시스템 안정성 향상:** 단축키 반응 속도와 처리 신뢰도를 높여 전반적인 조작 편의성을 개선했습니다.

---

### v1.1.0 (2026-04-15)
**✨ 주요 신규 기능**
- **북마크 스마트 기능 확장:** 북마크 지점에서 스크린샷 캡처 및 전후 5초 자동 클립 생성 기능 추가
- **선수 명단 시간대별 로딩:** 경기 시간에 따라 실시간으로 선수 명단을 불러와 메모리 효율 개선
- **타임라인 동기화:** 후반전 시작 시점과 UI 타임라인이 정확히 동기화되도록 개선
- **UI 개선:** 팀 선택 버튼 추가

---

---

# ⚽ Football Recording

A desktop analysis tool for reviewing football footage — tag key moments by player, capture bookmarks, and organize your match analysis in one place.

---

## 📌 Key Features

- **Video Playback & Navigation** — Supports MP4, MKV, MOV and more; timeline-based scene navigation
- **Event Tagging** — Log passes, shots, goals, dribbles, and more, assigned to individual players
- **Bookmarks** — Instantly mark important moments with screenshot capture and auto-clip generation (±5 seconds)
- **Auto Squad Loading** — Pulls home/away lineups from FotMob in sync with match time
- **Project Save & Load** — Save your analysis to a file and resume at any point

---

## 🚀 Update History

### v1.1.2 (2026-04-18)
**✨ New Features & Improvements**
- **Project Timeline Persistence:** When reloading a project, the timeline is automatically restored to the exact position where it was last saved.
- **Historical Squad Data Support:** Player lineups for matches prior to the 2024-25 season can now be fetched correctly via FotMob.

---

### v1.1.1 (2026-04-17)
**🛠️ Bug Fixes & Improvements**
- **Enhanced Bookmark Visibility:** Bookmarks are now clearly distinguished from regular markers on both the timeline and the event list.
- **Hotkey Logic Fix:** Fixed a bug where pressing hotkey `2` would always select a bookmark regardless of the current context.
- **Stability Improvements:** Improved hotkey responsiveness and processing reliability for a smoother experience.

---

### v1.1.0 (2026-04-15)
**✨ Key New Features**
- **Smart Bookmark Extensions:** Added screenshot capture and automatic clip creation (10 seconds total) at any bookmarked moment.
- **Time-based Squad Loading:** Player lineups are loaded dynamically based on match time, improving memory efficiency.
- **Timeline Synchronization:** The UI timeline is now perfectly synchronized with the start of the second half.
- **UI Improvements:** Added Team Selection Buttons.