"""
generate_commentary.py
-----------------------
디지털PB센터 주간 시황 브리핑 - AI 코멘터리 자동 생성 스크립트

update_market_data.py 가 숫자(지수/금리/환율 등)를 먼저 채운 뒤에 실행합니다.
이 스크립트는 docs/index.html 에서 이미 채워진 숫자 데이터를 읽어서,
Claude API(+ 웹검색)에게 아래 항목들을 생성하도록 요청하고 결과를 다시 파일에 반영합니다.

생성 대상 (모두 [AI:...] 마커로 표시된 구간):
  - HERO (이번주 시황 한줄 요약)
  - OVERSEAS / DOMESTIC_INDEX 의 comment 필드 (등락 배경 한줄 코멘트)
  - ISSUES (이번주 주요 이슈·일정) — 웹검색으로 실제 일정 탐색
  - IMPLICATIONS / IMPL_HIGHLIGHT (연계 시사점) — context/business_context.md 기반

필요 환경변수:
  - ANTHROPIC_API_KEY (필수) : console.anthropic.com 에서 발급
"""

import os
import re
import sys
import json
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "docs" / "index.html"
CONTEXT_MD = ROOT / "context" / "business_context.md"

MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# 1) 현재 파일에서 이미 채워진 숫자 데이터 파싱
# ---------------------------------------------------------------------------
def extract_block(html: str, start_marker: str, end_marker: str) -> str:
    pattern = re.compile(re.escape(start_marker) + r"(.*?)" + re.escape(end_marker), re.S)
    m = pattern.search(html)
    return m.group(1) if m else ""


def parse_market_rows(block_text: str):
    """name/value/chg/pct/history 형태의 JS 객체 배열을 파싱. history는 원본 텍스트 그대로 보존."""
    rows = []
    for m in re.finditer(
        r'name:\s*"([^"]*)",\s*value:\s*"([^"]*)",\s*chg:\s*"([^"]*)",\s*pct:\s*(-?[\d.]+),\s*history:\s*(\[[^\]]*\])',
        block_text,
    ):
        rows.append({
            "name": m.group(1),
            "value": m.group(2),
            "chg": m.group(3),
            "pct": float(m.group(4)),
            "history_raw": m.group(5),
        })
    return rows


def parse_simple_kv(block_text: str, key: str):
    m = re.search(rf'{key}:\s*"([^"]*)"', block_text)
    return m.group(1) if m else None


def build_data_summary(html: str) -> dict:
    overseas = parse_market_rows(extract_block(html, "// [AUTO:OVERSEAS_START]", "// [AUTO:OVERSEAS_END]"))
    domestic = parse_market_rows(extract_block(html, "// [AUTO:DOMESTIC_START]", "// [AUTO:DOMESTIC_END]"))

    rate_block = extract_block(html, "// [AUTO:RATE_START]", "// [AUTO:RATE_END]")
    gold_block = extract_block(html, "// [AUTO:GOLD_START]", "// [AUTO:GOLD_END]")
    fx_block = extract_block(html, "// [AUTO:FX_START]", "// [AUTO:FX_END]")

    fx_rows = []
    for m in re.finditer(r'name:\s*"([^"]*)",\s*value:\s*"([^"]*)",\s*chg:\s*"([^"]*)"', fx_block):
        fx_rows.append({"name": m.group(1), "value": m.group(2), "chg": m.group(3)})

    return {
        "overseas": overseas,
        "domestic": domestic,
        "rate": {
            "y30": parse_simple_kv(rate_block, "y30"),
            "y10": parse_simple_kv(rate_block, "y10"),
            "y2": parse_simple_kv(rate_block, "y2"),
        },
        "gold": {
            "price": parse_simple_kv(gold_block, "price"),
            "chg": parse_simple_kv(gold_block, "chg"),
        },
        "fx": fx_rows,
    }


# ---------------------------------------------------------------------------
# 2) Claude API 호출
# ---------------------------------------------------------------------------
SCHEMA_INSTRUCTIONS = """
필요한 조사(웹검색 등)는 먼저 끝내세요. 조사가 다 끝났으면, 마지막 답변 메시지는
반드시 아래 JSON 객체 하나로만 시작하고 끝내세요. "이제 정리하겠습니다" 같은 안내
문장이나 설명을 앞뒤에 절대 붙이지 마세요. 마크다운 코드블록(```)도 쓰지 마세요.
답변의 첫 글자는 반드시 { 여야 하고 마지막 글자는 반드시 } 여야 합니다.

{
  "hero_headline": "이번주 시황을 한 문장으로 요약 (결론형, 30자 내외)",
  "hero_sub": "부연 설명 한 줄",
  "overseas_comments": { "지수명": "등락 배경 한 줄 코멘트", ... },
  "domestic_comments": { "코스피": "...", "코스닥": "..." },
  "issues": [
    {"date": "8/12(화)", "importance": "mid", "flag": "🇰🇷", "title": "...", "desc": "..."},
    ... 이번주 평일 기준 4~6개. 해외 이벤트(FOMC, 미 경제지표 등)와
        국내 이벤트(한국은행 금통위, 국내 주요 기업 실적발표, 국내 경제지표 등)를
        균형 있게 섞어서 포함하세요. 해외 일정만 나열하지 마세요.
        importance는 high/mid/low 중 하나.
        flag는 해당 이슈의 국가를 나타내는 국기 이모지 하나 (예: 미국=🇺🇸, 한국=🇰🇷,
        유럽=🇪🇺, 일본=🇯🇵, 중국=🇨🇳). 국가가 명확하지 않으면 🌐 사용.
  ],
  "implications": [
    {"cat": "리스크관리", "text": "...", "action": "..."},
    {"cat": "세일즈 기회", "text": "...", "action": "..."},
    {"cat": "고객 커뮤니케이션", "text": "...", "action": "..."},
    {"cat": "자산배분 시사점", "text": "...", "action": "..."}
  ],
  "impl_highlight": "이번주 가장 중요한 연계 포인트 한 줄 결론"
}

- issues 는 실제 이번 주(오늘 날짜 기준)에 예정된 경제지표·이벤트를 웹검색으로 확인해서 채우세요.
  국내 일정(한국은행 금통위, 국내 기업 실적발표 등)을 반드시 포함하세요.
- implications 는 반드시 아래 business_context.md 내용에 근거해서, 이번주 시황 데이터와
  구체적으로 연결해 작성하세요.
"""


def build_weekday_dates() -> str:
    """이번 주 월~금의 정확한 날짜-요일 목록을 만든다 (AI가 요일 계산을 틀리는 것을 방지)."""
    today = dt.datetime.utcnow() + dt.timedelta(hours=9)
    monday = today - dt.timedelta(days=today.weekday())
    names = ["월", "화", "수", "목", "금"]
    parts = []
    for i in range(5):
        d = monday + dt.timedelta(days=i)
        parts.append(f"{d.month}/{d.day}({names[i]})")
    return ", ".join(parts)


def build_prompt(data: dict, week_label: str, today_str: str, context_md: str) -> str:
    weekday_dates = build_weekday_dates()
    return f"""당신은 미래에셋증권 디지털PB센터의 주간 시황 브리핑 작성을 돕는 애널리스트입니다.
오늘 날짜: {today_str}
이번 주: {week_label}
이번 주 날짜-요일 (정확함, 반드시 이 목록의 표기만 그대로 사용하세요 — 직접 요일을 계산하지 마세요):
{weekday_dates}

## 이번 주 시황 데이터 (이미 확정된 수치, 임의로 바꾸지 말고 코멘트만 작성)
해외지수: {json.dumps(data['overseas'], ensure_ascii=False)}
국내지수: {json.dumps(data['domestic'], ensure_ascii=False)}
미국채금리: {json.dumps(data['rate'], ensure_ascii=False)}
금(Gold): {json.dumps(data['gold'], ensure_ascii=False)}
환율: {json.dumps(data['fx'], ensure_ascii=False)}

## 우리 부서 업무 컨텍스트
{context_md}

## 작업 지시
필요하면 웹검색으로 이번 주 실제 경제지표 일정, 국내 업종별 등락 현황을 확인한 뒤,
{SCHEMA_INSTRUCTIONS}
"""


def call_claude(prompt: str) -> str:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [경고] ANTHROPIC_API_KEY 미설정 - AI 코멘터리 생성을 건너뜁니다.")
        return ""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [b.text for b in response.content if getattr(b, "type", "") == "text"]
        return "\n".join(text_parts)
    except Exception as e:
        print(f"  [경고] Claude API 호출 실패: {e}")
        return ""


def parse_json_response(text: str):
    text = text.strip()
    # 코드블록으로 감쌌으면 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # 모델이 JSON 앞뒤로 설명 문장을 덧붙이는 경우가 있어, 가장 바깥쪽 { ... } 만 추출
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    try:
        return json.loads(text)
    except Exception as e:
        print(f"  [경고] JSON 파싱 실패: {e}")
        print("  --- 응답 원문 (앞 500자) ---")
        print(text[:500])
        return None


# ---------------------------------------------------------------------------
# 3) JS 블록 재작성
# ---------------------------------------------------------------------------
def replace_block(html: str, start_marker: str, end_marker: str, new_code: str) -> str:
    pattern = re.compile(re.escape(start_marker) + r".*?" + re.escape(end_marker), re.S)
    replacement = f"{start_marker}\n{new_code}\n{end_marker}"
    new_html, n = pattern.subn(replacement, html)
    if n == 0:
        print(f"  [경고] 마커를 찾지 못했습니다: {start_marker} ~ {end_marker}")
    return new_html


def esc(s: str) -> str:
    s = str(s)
    s = s.replace("\\", "\\\\")   # 백슬래시 먼저 이스케이프 (순서 중요)
    s = s.replace('"', '\\"')
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")  # 줄바꿈은 문자열을 깨뜨리므로 공백으로 치환
    # AI가 생성한 문장에 "</script" 같은 문자열이 우연히 섞이면 브라우저가 <script> 블록을
    # 그 지점에서 통째로 닫아버려 페이지 전체가 하얗게 멈춘다. "</" 를 "<\/" 로 치환해 방지.
    s = s.replace("</", "<\\/")
    return s


def rebuild_market_block(const_name: str, existing_rows: list, comments: dict) -> str:
    lines = []
    for r in existing_rows:
        comment = comments.get(r["name"], "[코멘트 생성 실패]")
        hist = r.get("history_raw", "[0,0]")
        lines.append(
            f'  {{ name: "{esc(r["name"])}", value: "{esc(r["value"])}", '
            f'chg: "{esc(r["chg"])}", pct: {r["pct"]}, history: {hist}, comment: "{esc(comment)}" }}'
        )
    body = ",\n".join(lines)
    return f"const {const_name} = [\n{body}\n];"


def build_hero_js(headline, sub):
    return f'const HERO = {{\n  headline: "{esc(headline)}",\n  sub: "{esc(sub)}"\n}};'


def build_issues_js(issues):
    lines = [
        f'  {{ date: "{esc(i["date"])}", importance: "{esc(i["importance"])}", '
        f'flag: "{esc(i.get("flag", "🌐"))}", title: "{esc(i["title"])}", desc: "{esc(i["desc"])}" }}'
        for i in issues
    ]
    body = ",\n".join(lines)
    return (
        'const ISSUES_DESC = "발표 시점 기준 예정된 주요 이벤트 (중요도: 상/중/하)";\n'
        f"const ISSUES = [\n{body}\n];"
    )


def build_implications_js(implications, highlight):
    lines = [
        f'  {{ cat: "{esc(i["cat"])}", text: "{esc(i["text"])}", action: "{esc(i["action"])}" }}'
        for i in implications
    ]
    body = ",\n".join(lines)
    return (
        'const IMPL_HEADLINE = "시황이 우리 업무에 주는 시사점";\n'
        'const IMPL_DESC = "다이렉트 고객 · 카이로스 멤버십 · 세일즈 포인트로 연결";\n'
        f"const IMPLICATIONS = [\n{body}\n];\n"
        f'const IMPL_HIGHLIGHT = "{esc(highlight)}";'
    )


# ---------------------------------------------------------------------------
# 4) 메인
# ---------------------------------------------------------------------------
def main():
    print("== AI 코멘터리 생성 시작 ==")
    html = INDEX_HTML.read_text(encoding="utf-8")
    context_md = CONTEXT_MD.read_text(encoding="utf-8") if CONTEXT_MD.exists() else ""

    week_m = re.search(r'const WEEK_LABEL = "([^"]*)"', html)
    week_label = week_m.group(1) if week_m else ""
    today_str = (dt.datetime.utcnow() + dt.timedelta(hours=9)).strftime("%Y-%m-%d (%A)")

    data = build_data_summary(html)
    prompt = build_prompt(data, week_label, today_str, context_md)

    raw = call_claude(prompt)
    if not raw:
        print("== AI 응답 없음 - 기존 내용을 그대로 둡니다 ==")
        return

    result = parse_json_response(raw)
    if not result:
        print("== JSON 파싱 실패 - 기존 내용을 그대로 둡니다 ==")
        return

    # 해외/국내 지수 comment 채워서 AUTO 블록 재작성 (숫자는 그대로 유지)
    overseas_js = rebuild_market_block("OVERSEAS", data["overseas"], result.get("overseas_comments", {}))
    domestic_js = rebuild_market_block("DOMESTIC_INDEX", data["domestic"], result.get("domestic_comments", {}))
    html = replace_block(html, "// [AUTO:OVERSEAS_START]", "// [AUTO:OVERSEAS_END]", overseas_js)
    html = replace_block(html, "// [AUTO:DOMESTIC_START]", "// [AUTO:DOMESTIC_END]", domestic_js)

    html = replace_block(html, "// [AI:HERO_START]", "// [AI:HERO_END]",
                          build_hero_js(result.get("hero_headline", "[생성 실패]"), result.get("hero_sub", "")))
    html = replace_block(html, "// [AI:ISSUES_START]", "// [AI:ISSUES_END]",
                          build_issues_js(result.get("issues", [])))
    html = replace_block(html, "// [AI:IMPLICATIONS_START]", "// [AI:IMPLICATIONS_END]",
                          build_implications_js(result.get("implications", []), result.get("impl_highlight", "")))

    INDEX_HTML.write_text(html, encoding="utf-8")
    print("== 완료: AI 코멘터리 반영됨 ==")


if __name__ == "__main__":
    main()
