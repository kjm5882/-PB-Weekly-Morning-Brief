"""
update_market_data.py
----------------------
디지털PB센터 주간 시황 브리핑 - 시세 자동 갱신 스크립트

역할:
  - Yahoo Finance(yfinance)에서 해외지수/환율/금/유가/달러인덱스/미국채금리를 가져오고
  - pykrx(KRX/네이버 기반)에서 코스피·코스닥 지수 및 수급(외국인/기관/개인)을 가져와서
  - docs/index.html 안의 [AUTO:...] 마커 구간만 최신 값으로 교체합니다.

주의:
  - [MANUAL] 로 표시된 부분(헤드라인, 이슈 캘린더, 연계 시사점, 영업방향 등)은
    이 스크립트가 건드리지 않습니다. 매주 직접 수정하세요.
  - 티커 심볼은 Yahoo Finance 정책에 따라 바뀔 수 있어 최초 실행 시 한 번은
    직접 값이 잘 나오는지 확인하는 것을 권장합니다. (특히 2년물 국채금리 티커)
"""

import re
import sys
import json
import datetime as dt
import os
from pathlib import Path

import requests
import yfinance as yf

try:
    from pykrx import stock as krx
    HAS_PYKRX = True
except ImportError:
    HAS_PYKRX = False

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "docs" / "index.html"

# ---------------------------------------------------------------------------
# 1) 티커 정의 (Yahoo Finance)
#    확인이 필요하면 https://finance.yahoo.com 에서 종목명 검색 후 심볼 확인
# ---------------------------------------------------------------------------
OVERSEAS_TICKERS = [
    ("S&P 500",        "^GSPC", "pt"),
    ("나스닥",          "^IXIC", "pt"),
    ("다우존스",        "^DJI",  "pt"),
    ("유럽 STOXX600",   "^STOXX", "pt"),   # 심볼 불일치 시 "^SXXP" 등으로 교체 확인 필요
    ("일본 니케이225",  "^N225", "pt"),
    ("중국 상해종합",   "000001.SS", "pt"),
    ("달러인덱스(DXY)", "DX-Y.NYB", ""),
    ("WTI 유가",        "CL=F", "$"),
]

DOMESTIC_TICKERS = [
    ("코스피", "^KS11", "pt"),
    ("코스닥", "^KQ11", "pt"),
]

RATE_TICKERS = {
    # Yahoo Finance의 국채금리 티커(특히 2년물)는 불안정해서 FRED(연준 공식, 무료, API키 불필요)로 대체
    "10y": "DGS10",
    "2y":  "DGS2",
}

GOLD_TICKER = "GC=F"

FX_TICKERS = [
    ("원/달러 (USD-KRW)", "KRW=X"),
    ("엔/달러 (USD-JPY)", "JPY=X"),
    ("유로/달러 (EUR-USD)", "EURUSD=X"),
]


# ---------------------------------------------------------------------------
# 2) 데이터 수집 유틸
# ---------------------------------------------------------------------------
import urllib.request
import csv
import io


def fetch_fred_series(series_id: str):
    """FRED(연준 공식) CSV를 API키 없이 받아온다. [(date, value), ...] 반환, 결측치('.')는 제외."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            text = resp.read().decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        out = []
        for row in reader:
            if len(row) < 2 or row[1] == ".":
                continue
            try:
                out.append((row[0], float(row[1])))
            except ValueError:
                continue
        return out
    except Exception as e:
        print(f"  [경고] FRED {series_id} 조회 실패: {e}")
        return []


def monthly_downsample(series, months=36):
    """일별 시계열에서 각 (연,월)의 마지막 값만 남겨 월별 시계열로 축소, 최근 N개월만 반환."""
    if not series:
        return []
    by_month = {}
    for date_str, value in series:
        ym = date_str[:7]  # "YYYY-MM"
        by_month[ym] = value  # 같은 달이면 뒤에 나온(=더 최근) 값으로 덮어씀
    values = list(by_month.values())
    return values[-months:] if len(values) > months else values


def fetch_history_3y(ticker: str, interval: str = "1mo"):
    """3년치 히스토리(월봉 기준)를 리스트로 반환. 실패 시 빈 리스트."""
    try:
        df = yf.Ticker(ticker).history(period="3y", interval=interval)
        if df.empty:
            return []
        return [round(float(v), 4) for v in df["Close"].tolist()]
    except Exception as e:
        print(f"  [경고] {ticker} 히스토리 조회 실패: {e}")
        return []


def fetch_last_and_chg(ticker: str):
    """가장 최근 종가와 '지난주 대비' 등락률(%)을 반환 (약 5영업일 전 종가와 비교)."""
    try:
        df = yf.Ticker(ticker).history(period="1mo", interval="1d")
        if len(df) < 6:
            return None, None
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-6])  # 약 1주일(5영업일) 전
        pct = (last - prev) / prev * 100 if prev else 0
        return last, pct
    except Exception as e:
        print(f"  [경고] {ticker} 시세 조회 실패: {e}")
        return None, None


def fmt_pct(pct):
    if pct is None:
        return "[N/A]"
    arrow = "▲" if pct >= 0 else "▼"
    sign = "+" if pct >= 0 else ""
    return f"{arrow} {sign}{pct:.1f}%"


def js_array(nums):
    return "[" + ",".join(f"{n:.4g}" for n in nums) + "]"


# ---------------------------------------------------------------------------
# 3) 각 섹션 데이터 조립
# ---------------------------------------------------------------------------
def build_overseas():
    rows = []
    for name, ticker, unit in OVERSEAS_TICKERS:
        last, pct = fetch_last_and_chg(ticker)
        hist = fetch_history_3y(ticker)
        if last is None:
            rows.append({"name": name, "value": "[N/A]", "chg": "[N/A]", "pct": 0, "history": hist or [0, 0]})
            continue
        value = f"{last:,.1f}{unit}"
        rows.append({"name": name, "value": value, "chg": fmt_pct(pct), "pct": round(pct, 2), "history": hist or [0, 0]})
    return rows


def build_rate_card():
    s10 = fetch_fred_series(RATE_TICKERS["10y"])
    s2 = fetch_fred_series(RATE_TICKERS["2y"])

    y10 = s10[-1][1] if s10 else None
    y2 = s2[-1][1] if s2 else None
    spread = round(y10 - y2, 3) if (y10 is not None and y2 is not None) else None

    # 3년 월간 스프레드 곡선: 같은 날짜 기준으로 매칭해서 계산
    spread_hist = []
    if s10 and s2:
        map10 = dict(s10)
        map2 = dict(s2)
        common_dates = sorted(set(map10) & set(map2))
        merged = [(d, round(map10[d] - map2[d], 3)) for d in common_dates]
        spread_hist = monthly_downsample(merged, months=36)

    return {
        "y10": f"{y10:.2f}%" if y10 is not None else "[N/A]",
        "y2": f"{y2:.2f}%" if y2 is not None else "[N/A]",
        "spreadValue": spread if spread is not None else 0,
        "spreadLabel": (f"{'+' if spread >= 0 else ''}{spread:.2f}%p" if spread is not None else "[N/A]"),
        "history": spread_hist or [0] * 36,
    }


def build_gold_card():
    last, pct = fetch_last_and_chg(GOLD_TICKER)
    hist = fetch_history_3y(GOLD_TICKER)
    return {
        "price": f"{last:,.1f}$" if last else "[N/A]",
        "chg": fmt_pct(pct),
        "pct": round(pct, 2) if pct is not None else 0,
        "history": hist or [0] * 36,
    }


def build_fx():
    out = []
    for name, ticker in FX_TICKERS:
        last, pct = fetch_last_and_chg(ticker)
        hist = fetch_history_3y(ticker)
        value = f"{last:,.2f}" if last else "[N/A]"
        out.append({
            "name": name,
            "value": value,
            "chg": fmt_pct(pct),
            "pct": round(pct, 2) if pct is not None else 0,
            "history": hist or [0] * 36,
        })
    return out


def fetch_naver_index(code: str):
    """네이버 금융에서 코스피/코스닥 지수를 로그인 없이 직접 가져온다.
    code: 'KOSPI' 또는 'KOSDAQ'
    반환: (현재가, 등락률%) 또는 (None, None)
    """
    import requests
    url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "euc-kr"
        html = resp.text

        m_val = re.search(r'id="now_value">\s*([\d,\.]+)', html)
        if not m_val:
            return None, None
        value = float(m_val.group(1).replace(",", ""))

        # 등락률(%) 추출 - 페이지 구조 변경에 취약할 수 있어 실패해도 지수값은 살린다
        m_rate = re.search(r'([+-]?\d+\.\d+)%', html)
        pct = float(m_rate.group(1)) if m_rate else None

        return value, pct
    except Exception as e:
        print(f"  [경고] 네이버 {code} 지수 조회 실패: {e}")
        return None, None


def build_domestic():
    """1순위: Yahoo Finance(^KS11/^KQ11)로 코스피/코스닥 지수 + 지난주 대비 등락 계산.
    2순위(현재가만 보정용): 네이버 금융으로 교차 확인.
    수급(외국인/기관/개인)은 pykrx로 가져온다 — 단, 최신 pykrx는 KRX 로그인이 필요해
    KRX_ID / KRX_PW 환경변수(GitHub Secrets)가 없으면 이 부분은 건너뛴다."""
    domestic_index = [
        {"name": "코스피", "value": "[N/A]", "chg": "[N/A]", "pct": 0, "history": [0, 0], "comment": "[등락 배경 한 줄 코멘트]"},
        {"name": "코스닥", "value": "[N/A]", "chg": "[N/A]", "pct": 0, "history": [0, 0], "comment": "[등락 배경 한 줄 코멘트]"},
    ]
    flow = [
        {"name": "외국인", "value": "[N/A]", "dir": "up",   "top": "[순매수 상위 업종/종목]"},
        {"name": "기관",   "value": "[N/A]", "dir": "down", "top": "[순매도 상위 업종/종목]"},
        {"name": "개인",   "value": "[N/A]", "dir": "up",   "top": "[순매수 상위 업종/종목]"},
    ]

    for i, (name, ticker, unit) in enumerate(DOMESTIC_TICKERS):
        last, pct = fetch_last_and_chg(ticker)
        hist = fetch_history_3y(ticker)
        if hist:
            domestic_index[i]["history"] = hist
        if last is not None:
            domestic_index[i]["value"] = f"{last:,.1f}{unit}"
            domestic_index[i]["chg"] = fmt_pct(pct)
            domestic_index[i]["pct"] = round(pct, 2) if pct is not None else 0
        else:
            # Yahoo 실패 시 네이버로 현재가만이라도 보정 (등락률은 지난주 대비 계산 불가하므로 비워둠)
            code = "KOSPI" if name == "코스피" else "KOSDAQ"
            naver_val, _ = fetch_naver_index(code)
            if naver_val is not None:
                domestic_index[i]["value"] = f"{naver_val:,.1f}pt"

    if not HAS_PYKRX:
        print("  [안내] pykrx 미설치로 수급 데이터는 건너뜁니다.")
        return domestic_index, flow

    krx_id = os.environ.get("KRX_ID")
    krx_pw = os.environ.get("KRX_PW")
    if not (krx_id and krx_pw):
        print("  [안내] KRX_ID/KRX_PW 미설정으로 수급 데이터는 건너뜁니다. (README 참고)")
        return domestic_index, flow

    today = dt.datetime.utcnow() + dt.timedelta(hours=9)  # KST 기준으로 명시 (서버는 UTC로 동작)
    # 최근 영업일 찾기 (최대 7일 역산)
    d_found = None
    for i in range(7):
        d = (today - dt.timedelta(days=i)).strftime("%Y%m%d")
        try:
            df_flow = krx.get_market_trading_value_by_date(d, d, "KOSPI")
            if not df_flow.empty:
                d_found = (d, df_flow)
                break
        except Exception:
            continue

    if d_found:
        d, df_flow = d_found
        try:
            row = df_flow.iloc[-1]
            def fmt_amt(v):
                v_eok = v / 100_000_000
                sign = "+" if v_eok >= 0 else ""
                return f"{sign}{v_eok:,.0f}억"
            if "외국인합계" in row:
                flow[0]["value"] = fmt_amt(row["외국인합계"])
                flow[0]["dir"] = "up" if row["외국인합계"] >= 0 else "down"
            if "기관합계" in row:
                flow[1]["value"] = fmt_amt(row["기관합계"])
                flow[1]["dir"] = "up" if row["기관합계"] >= 0 else "down"
            if "개인" in row:
                flow[2]["value"] = fmt_amt(row["개인"])
                flow[2]["dir"] = "up" if row["개인"] >= 0 else "down"
        except Exception as e:
            print(f"  [경고] 수급 데이터 조회 실패: {e}")

    return domestic_index, flow


# ---------------------------------------------------------------------------
# 4) JS 리터럴 문자열 생성
# ---------------------------------------------------------------------------
def js_row(r):
    hist = js_array(r.get("history") or [0, 0])
    return (f'  {{ name: "{r["name"]}", value: "{r["value"]}", '
            f'chg: "{r["chg"]}", pct: {r["pct"]}, history: {hist}, comment: "[등락 배경 한 줄 코멘트]" }}')


def build_overseas_js(rows):
    body = ",\n".join(js_row(r) for r in rows)
    return f"const OVERSEAS = [\n{body}\n];"


def build_rate_js(rc):
    return (
        "const RATE_CARD = {\n"
        f'  y10: "{rc["y10"]}",\n'
        f'  y2: "{rc["y2"]}",\n'
        f'  spreadValue: {rc["spreadValue"]},\n'
        f'  spreadLabel: "{rc["spreadLabel"]}",\n'
        f'  history: {js_array(rc["history"])}\n'
        "};"
    )


def build_gold_js(gc):
    return (
        "const GOLD_CARD = {\n"
        f'  price: "{gc["price"]}",\n'
        f'  chg: "{gc["chg"]}",\n'
        f'  pct: {gc["pct"]},\n'
        f'  history: {js_array(gc["history"])}\n'
        "};"
    )


def build_fx_js(fx_list):
    items = []
    for f in fx_list:
        items.append(
            f'  {{ name: "{f["name"]}", value: "{f["value"]}", chg: "{f["chg"]}", '
            f'pct: {f["pct"]}, history: {js_array(f["history"])} }}'
        )
    return "const FX = [\n" + ",\n".join(items) + "\n];"


def build_domestic_js(rows):
    body = ",\n".join(js_row(r) for r in rows)
    return f"const DOMESTIC_INDEX = [\n{body}\n];"


def build_flow_js(rows):
    items = []
    for r in rows:
        items.append(f'  {{ name: "{r["name"]}", value: "{r["value"]}", dir: "{r["dir"]}", top: "{r["top"]}" }}')
    return "const FLOW = [\n" + ",\n".join(items) + "\n];"


# ---------------------------------------------------------------------------
# 5) 마커 기반 치환
# ---------------------------------------------------------------------------
def replace_block(html: str, start_marker: str, end_marker: str, new_code: str) -> str:
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker), re.S
    )
    replacement = f"{start_marker}\n{new_code}\n{end_marker}"
    new_html, n = pattern.subn(replacement, html)
    if n == 0:
        print(f"  [경고] 마커를 찾지 못했습니다: {start_marker} ~ {end_marker}")
    return new_html


def build_week_label():
    """오늘(KST) 기준으로 이번 주 월~금 날짜를 계산해 WEEK_LABEL 문자열을 만든다."""
    today = dt.datetime.utcnow() + dt.timedelta(hours=9)
    monday = today - dt.timedelta(days=today.weekday())  # weekday(): Mon=0
    friday = monday + dt.timedelta(days=4)
    return f"{monday.strftime('%Y.%m.%d')}(월) ~ {friday.strftime('%m.%d')}(금)"


def main():
    print("== 시황 데이터 수집 시작 ==")
    html = INDEX_HTML.read_text(encoding="utf-8")

    week_label = build_week_label()
    html = re.sub(
        r'const WEEK_LABEL = "[^"]*";',
        f'const WEEK_LABEL = "{week_label}";',
        html,
    )

    print("- 해외지수 수집 중...")
    overseas_rows = build_overseas()

    print("- 미국채 금리(10Y/2Y) 수집 중...")
    rate_card = build_rate_card()

    print("- 금(Gold) 수집 중...")
    gold_card = build_gold_card()

    print("- 환율(원/달러, 엔/달러, 유로/달러) 수집 중...")
    fx_rows = build_fx()

    print("- 국내지수/수급 수집 중 (네이버 금융 + pykrx)...")
    domestic_rows, flow_rows = build_domestic()
    domestic_ok = any(r["value"] != "[N/A]" for r in domestic_rows)
    flow_ok = any(r["value"] != "[N/A]" for r in flow_rows)

    html = replace_block(html, "// [AUTO:OVERSEAS_START]", "// [AUTO:OVERSEAS_END]", build_overseas_js(overseas_rows))
    html = replace_block(html, "// [AUTO:RATE_START]", "// [AUTO:RATE_END]", build_rate_js(rate_card))
    html = replace_block(html, "// [AUTO:GOLD_START]", "// [AUTO:GOLD_END]", build_gold_js(gold_card))
    html = replace_block(html, "// [AUTO:FX_START]", "// [AUTO:FX_END]", build_fx_js(fx_rows))

    if domestic_ok:
        html = replace_block(html, "// [AUTO:DOMESTIC_START]", "// [AUTO:DOMESTIC_END]", build_domestic_js(domestic_rows))
    else:
        print("  [안내] 국내지수 조회 실패 - 기존 값을 유지합니다.")
    if flow_ok:
        html = replace_block(html, "// [AUTO:FLOW_START]", "// [AUTO:FLOW_END]", build_flow_js(flow_rows))
    else:
        print("  [안내] 수급 데이터 없음 - 기존 값을 유지합니다.")

    # REPORT_DATE 갱신 (기준 시각 표기)
    now_kst = dt.datetime.utcnow() + dt.timedelta(hours=9)
    date_str = now_kst.strftime("%Y.%m.%d(%a) %H:%M")
    html = re.sub(
        r'const REPORT_DATE = "[^"]*";',
        f'const REPORT_DATE = "기준 {date_str} 갱신";',
        html,
    )

    INDEX_HTML.write_text(html, encoding="utf-8")
    print("== 완료: docs/index.html 갱신됨 ==")


if __name__ == "__main__":
    main()
