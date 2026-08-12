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

## 매주 직접 수정해야 하는 부분

`docs/index.html` 안에서 아래 항목은 **자동 갱신되지 않습니다.** 회의 전 직접 채워주세요.

| 항목 | 위치 (JS 변수명) |
|---|---|
| 이번주 한줄 요약 | `HERO` |
| 이번주 최대 이벤트 / Focus 카드 | `SUMMARY_MANUAL` |
| 지수별 코멘트(등락 배경) | 각 배열의 `comment` 필드 |
| 이번주 주요 이슈·일정 | `ISSUES` |
| 연계 시사점 카드 | `IMPLICATIONS`, `IMPL_HIGHLIGHT` |
| 이번주 영업방향 체크리스트 | `DIRECTION` |
| 업종 Top Movers | `SECTORS` |

파일 안에 `// [AUTO:...]` 로 표시된 구간은 스크립트가 자동으로 덮어쓰므로 직접 수정해도
다음 실행 시 사라집니다. `// [MANUAL]` 또는 마커가 없는 위 항목들만 편집하세요.

## 자동 갱신되는 데이터

| 데이터 | 출처 |
|---|---|
| 해외지수 (S&P500·나스닥·다우·STOXX600·니케이225·상해종합) | Yahoo Finance |
| 미국채 10Y·2Y 금리, 장단기 스프레드 | **FRED**(미 연준 공식, API키 불필요) |
| 달러인덱스, WTI유가, 금가격 | Yahoo Finance |
| 원/달러·엔/달러·유로/달러 환율 | Yahoo Finance |
| 코스피·코스닥 지수 | **네이버 금융** (로그인 불필요) |
| 수급(외국인/기관/개인) | pykrx — **KRX 계정 로그인 필요** (아래 참고) |

### 수급(외국인/기관/개인) 데이터를 자동화하려면 (선택사항)

최신 pykrx는 KRX 데이터 조회 시 로그인을 요구합니다. 이 부분만 자동화하고 싶다면:

1. https://data.krx.co.kr 에서 무료 회원가입
2. 저장소 Settings → Secrets and variables → Actions → **New repository secret**
   - `KRX_ID` : 가입한 아이디
   - `KRX_PW` : 비밀번호
3. `.github/workflows/daily-update.yml` 의 "Fetch market data" 스텝에 아래 env 추가:
   ```yaml
   - name: Fetch market data & update docs/index.html
     env:
       KRX_ID: ${{ secrets.KRX_ID }}
       KRX_PW: ${{ secrets.KRX_PW }}
     run: python scripts/update_market_data.py
   ```

로그인 정보를 설정하지 않으면 수급 카드는 자동 갱신되지 않고 이전 값(또는 예시 값)이 유지됩니다 —
에러가 나서 페이지가 깨지지는 않으니, 굳이 급하게 설정 안 하셔도 됩니다.

- 장중 이슈 등으로 당일 데이터 수집이 일부 실패해도, **직전에 성공한 값이 그대로 유지**됩니다
  (실패했다고 값을 `[N/A]`로 덮어쓰지 않도록 처리되어 있습니다). `REPORT_DATE` 문구로 기준 시각을 확인하세요.

## 로컬에서 테스트하기

```bash
pip install -r requirements.txt
python scripts/update_market_data.py
# 이후 docs/index.html 을 브라우저로 열어 확인
```
