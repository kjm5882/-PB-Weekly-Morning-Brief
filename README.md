# 디지털PB센터 주간 시황 브리핑

매주 초 본부 주간회의에서 사용하는 시황 브리핑 페이지입니다.
회사 업무용으로, 개인 프로젝트(stock-alert-system)와는 별도로 관리합니다.

- 페이지: `docs/index.html` (GitHub Pages로 배포)
- 매일 08:00 KST, GitHub Actions가 시세를 자동 수집해 `docs/index.html`을 갱신합니다.
- 링크는 Pages 활성화 후 `https://<계정명>.github.io/<repo명>/` 형태로 생성됩니다.
- **이 저장소는 Public입니다.** 시황 숫자·일반적인 영업방향 코멘트 정도만 다루고,
  고객정보나 미공개 실적 등 민감한 내용은 절대 커밋하지 않습니다.

## 처음 설정하는 방법

1. **새 저장소 생성**
   - GitHub에서 새 저장소를 만듭니다. (**Public**으로 생성 — 별도 플랜 필요 없이 바로 Pages 사용 가능)
   - 이 폴더 전체를 그대로 그 저장소에 push 하세요.
     ```bash
     git init
     git add .
     git commit -m "init: 주간 시황 브리핑 셋업"
     git branch -M main
     git remote add origin <새 저장소 URL>
     git push -u origin main
     ```

2. **GitHub Pages 활성화**
   - 저장소 Settings → Pages → Build and deployment → Source: **GitHub Actions** 선택
   - Public 저장소라 플랜 제약 없이 바로 설정 가능합니다.
   - 참고: Public 저장소이므로 저장소 코드와 발행된 페이지 모두 인터넷에 공개됩니다.
     민감한 고객정보·미공개 실적 등은 절대 커밋하지 마세요. (시황 숫자, 일반적인 영업방향
     코멘트 정도는 무방하다는 판단 하에 Public으로 진행합니다.)

3. **워크플로우 확인**
   - `.github/workflows/daily-update.yml` 이 매일 08:00 KST(평일)에 자동 실행됩니다.
   - Actions 탭에서 `Run workflow` 버튼으로 언제든 수동 실행도 가능합니다.
   - 최초 1회는 수동 실행해서 정상적으로 데이터가 채워지는지 확인하세요.

## 매주 직접 확인/보정하면 되는 부분

이제 대부분의 텍스트가 **AI가 자동으로 채웁니다.** 아래는 마커별 역할 정리입니다.

| 항목 | 위치 (JS 변수명) | 채우는 방식 |
|---|---|---|
| 이번주 한줄 요약 | `HERO` | 🤖 AI 자동 생성 |
| 지수별 코멘트(등락 배경) | 각 배열의 `comment` 필드 | 🤖 AI 자동 생성 |
| 이번주 주요 이슈·일정 | `ISSUES` | 🤖 AI 자동 생성 (웹검색 기반) |
| 연계 시사점 카드 | `IMPLICATIONS`, `IMPL_HIGHLIGHT` | 🤖 AI 자동 생성 (`context/business_context.md` 참고) |
| 지수·금리·환율·금 수치 | `OVERSEAS`, `DOMESTIC_INDEX`, `RATE_CARD`, `GOLD_CARD`, `FX` | 📊 실제 데이터 자동 수집 |

**AI가 쓴 문장이 마음에 안 들면**: 직접 고쳐서 커밋해도 되지만, 다음 자동 실행 때 다시 AI가
덮어씁니다. 매주 그대로 쓰고 싶은 문구가 있다면 `context/business_context.md`에 규칙을
추가해서 AI가 그 방향으로 쓰도록 유도하는 걸 권장합니다.

`// [AUTO:...]`, `// [AI:...]` 마커로 감싸진 구간은 전부 스크립트가 자동으로 덮어씁니다.
그 바깥의 레이아웃/CSS 코드는 건드리지 않으니 안심하고 그대로 두세요.

## AI 코멘터리 생성 설정 (필수)

`scripts/generate_commentary.py` 가 Claude API를 사용해 위 표의 🤖 항목들을 작성합니다.

1. https://console.anthropic.com 에서 계정 생성 후 API 키 발급 (결제수단 등록 필요,
   이 정도 분량이면 1회 실행당 비용이 매우 적습니다)
2. 저장소 Settings → Secrets and variables → Actions → **New repository secret**
   - `ANTHROPIC_API_KEY` : 발급받은 키
3. 별도 코드 수정 없이 바로 작동합니다 (워크플로우에 이미 연결되어 있음)

키를 설정하지 않으면 이 단계는 조용히 건너뛰고 예시 텍스트(`[대괄호]`)가 그대로 남습니다 —
에러로 전체 파이프라인이 멈추지는 않습니다.

### AI가 참고하는 컨텍스트 수정하기

`context/business_context.md` 파일에 우리 부서 업무 배경(다이렉트 고객, 카이로스 멤버십,
세무 VOC, 온라인세미나 등)과 "연계 시사점 작성 규칙"이 정리되어 있습니다. 부서 상황이
바뀌면 **이 파일만 수정**하면 됩니다 (코드는 건드릴 필요 없음).

## 자동 갱신되는 데이터

| 데이터 | 출처 | 비교 기준 |
|---|---|---|
| 해외지수 (S&P500·나스닥·다우·STOXX600·니케이225·상해종합) | Yahoo Finance | 지난주 대비 |
| 국내지수 (코스피·코스닥) | Yahoo Finance (`^KS11`/`^KQ11`), 실패 시 네이버 금융으로 현재가만 보정 | 지난주 대비 |
| 미국채 10Y·2Y 금리, 장단기 스프레드 | **FRED**(미 연준 공식, API키 불필요) | - |
| 달러인덱스, WTI유가, 금가격, 환율 | Yahoo Finance | 지난주 대비 |
| 수급(외국인/기관/개인) | pykrx — **KRX 계정 로그인 필요** (아래 참고) | 당일 |

지수·환율 등락률은 전부 **"지난주 동일 시점 대비"**(약 5영업일 전) 기준으로 계산됩니다.

### 수급(외국인/기관/개인) 데이터를 자동화하려면 (선택사항)

최신 pykrx는 KRX 데이터 조회 시 로그인을 요구합니다. 이 부분만 자동화하고 싶다면:

1. https://data.krx.co.kr 에서 무료 회원가입
2. 저장소 Settings → Secrets and variables → Actions → **New repository secret**
   - `KRX_ID` : 가입한 아이디
   - `KRX_PW` : 비밀번호

워크플로우에 이미 연결되어 있어 별도 코드 수정 없이 바로 작동합니다.
로그인 정보를 설정하지 않으면 수급 카드만 갱신되지 않고, 나머지는 정상 동작합니다.

- 장중 이슈 등으로 당일 데이터 수집이 일부 실패해도, **직전에 성공한 값이 그대로 유지**됩니다
  (실패했다고 값을 `[N/A]`로 덮어쓰지 않도록 처리되어 있습니다). `REPORT_DATE` 문구로 기준 시각을 확인하세요.

## 다른 자료로 확장하고 싶을 때 (부문 주간회의자료, 일간실적 등)

이 저장소의 패턴(📊 실데이터 수집 스크립트 + 🤖 AI 코멘터리 스크립트 + `[AUTO]`/`[AI]` 마커)은
다른 정기 보고서에도 그대로 재사용할 수 있는 구조예요. 새 보고서를 추가하고 싶으면
Claude에게 "이 저장소 구조 그대로, OO 보고서용으로 새 템플릿·스크립트 만들어줘" 라고
요청하시면 됩니다.

## 로컬에서 테스트하기

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # AI 코멘터리까지 테스트하려면 필요
python scripts/update_market_data.py
python scripts/generate_commentary.py
# 이후 docs/index.html 을 브라우저로 열어 확인
```
