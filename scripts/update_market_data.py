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
from pathlib import Path

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

RATE_TICKERS = {
    "10y": "^TNX",   # 10년물 (표시값의 10배로 나오므로 /10 처리)
    "2y":  "^UST2Y", # 2년물 - Yahoo Finance에서 불안정할 수 있음. 안 나오면 FRED(DGS2)로 교체 권장
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
    """가장 최근 종가와 전일 대비 등락률(%)을 반환."""
    try:
        df = yf.Ticker(ticker).history(period="5d", interval="1d")
        if len(df) < 2:
            return None, None
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
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
        if last is None:
            rows.append({"name": name, "value": "[N/A]", "chg": "[N/A]", "pct": 0})
            continue
        value = f"{last:,.1f}{unit}"
        rows.append({"name": name, "value": value, "chg": fmt_pct(pct), "pct": round(pct, 2)})
    return rows


def build_rate_card():
    last10, _ = fetch_last_and_chg(RATE_TICKERS["10y"])
    last2, _ = fetch_last_and_chg(RATE_TICKERS["2y"])
    y10 = (last10 / 10) if last10 else None   # ^TNX는 10배로 표기됨
    y2 = last2

    hist10 = fetch_history_3y(RATE_TICKERS["10y"])
    hist2 = fetch_history_3y(RATE_TICKERS["2y"])
    spread_hist = []
    if hist10 and hist2 and len(hist10) == len(hist2):
        spread_hist = [round((a / 10) - b, 3) for a, b in zip(hist10, hist2)]

    spread = round((y10 - y2), 3) if (y10 is not None and y2 is not None) else None

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


def build_domestic():
    """pykrx로 코스피/코스닥 지수 + 수급을 가져온다. pykrx 미설치 시 건너뜀."""
    if not HAS_PYKRX:
        print("  [안내] pykrx 미설치로 국내 데이터는 건너뜁니다. (pip install pykrx)")
        return None, None

    today = dt.datetime.now()
    # 최근 영업일 찾기 (최대 7일 역산)
    df_kospi = None
    for i in range(7):
        d = (today - dt.timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = krx.get_index_ohlcv(d, d, "1001")  # 1001 = 코스피
            if not df.empty:
                df_kospi = (d, df)
                break
        except Exception:
            continue

    domestic_index = [
        {"name": "코스피", "value": "[N/A]", "chg": "[N/A]", "pct": 0, "comment": "[등락 배경 한 줄 코멘트]"},
        {"name": "코스닥", "value": "[N/A]", "chg": "[N/A]", "pct": 0, "comment": "[등락 배경 한 줄 코멘트]"},
    ]
    flow = [
        {"name": "외국인", "value": "[N/A]", "dir": "up",   "top": "[순매수 상위 업종/종목]"},
        {"name": "기관",   "value": "[N/A]", "dir": "down", "top": "[순매도 상위 업종/종목]"},
        {"name": "개인",   "value": "[N/A]", "dir": "up",   "top": "[순매수 상위 업종/종목]"},
    ]

    if df_kospi:
        d, df = df_kospi
        try:
            close = float(df["종가"].iloc[-1])
            chg_pct = float(df["등락률"].iloc[-1])
            domestic_index[0].update({
                "value": f"{close:,.1f}pt",
                "chg": fmt_pct(chg_pct),
                "pct": round(chg_pct, 2),
            })
        except Exception as e:
            print(f"  [경고] 코스피 파싱 실패: {e}")

        try:
            df_kosdaq = krx.get_index_ohlcv(d, d, "2001")  # 2001 = 코스닥
            if not df_kosdaq.empty:
                close_q = float(df_kosdaq["종가"].iloc[-1])
                chg_q = float(df_kosdaq["등락률"].iloc[-1])
                domestic_index[1].update({
                    "value": f"{close_q:,.1f}pt",
                    "chg": fmt_pct(chg_q),
                    "pct": round(chg_q, 2),
                })
        except Exception as e:
            print(f"  [경고] 코스닥 파싱 실패: {e}")

        try:
            df_flow = krx.get_market_trading_value_by_date(d, d, "KOSPI")
            # 컬럼: 기관합계 / 기타법인 / 개인 / 외국인합계 등 (버전에 따라 상이할 수 있음)
            if not df_flow.empty:
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
    return (f'  {{ name: "{r["name"]}", value: "{r["value"]}", '
            f'chg: "{r["chg"]}", pct: {r["pct"]}, comment: "[등락 배경 한 줄 코멘트]" }}')


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


def build_summary_js(kospi_row, rate10y):
    kospi_val = kospi_row["value"] if kospi_row else "[N/A]"
    kospi_chg = kospi_row["chg"] if kospi_row else "[N/A]"
    kospi_dir = "up" if kospi_row and kospi_row["pct"] >= 0 else "down"
    return (
        "const SUMMARY_AUTO = [\n"
        f'  {{ label: "코스피", value: "{kospi_val}", chg: "{kospi_chg}", dir: "{kospi_dir}" }},\n'
        f'  {{ label: "미 10년물 금리", value: "{rate10y}", chg: "", dir: "flat" }}\n'
        "];"
    )


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


def main():
    print("== 시황 데이터 수집 시작 ==")
    html = INDEX_HTML.read_text(encoding="utf-8")

    print("- 해외지수 수집 중...")
    overseas_rows = build_overseas()

    print("- 미국채 금리(10Y/2Y) 수집 중...")
    rate_card = build_rate_card()

    print("- 금(Gold) 수집 중...")
    gold_card = build_gold_card()

    print("- 환율(원/달러, 엔/달러, 유로/달러) 수집 중...")
    fx_rows = build_fx()

    print("- 국내지수/수급 수집 중 (pykrx)...")
    domestic_rows, flow_rows = build_domestic()

    html = replace_block(html, "// [AUTO:OVERSEAS_START]", "// [AUTO:OVERSEAS_END]", build_overseas_js(overseas_rows))
    html = replace_block(html, "// [AUTO:RATE_START]", "// [AUTO:RATE_END]", build_rate_js(rate_card))
    html = replace_block(html, "// [AUTO:GOLD_START]", "// [AUTO:GOLD_END]", build_gold_js(gold_card))
    html = replace_block(html, "// [AUTO:FX_START]", "// [AUTO:FX_END]", build_fx_js(fx_rows))

    if domestic_rows:
        html = replace_block(html, "// [AUTO:DOMESTIC_START]", "// [AUTO:DOMESTIC_END]", build_domestic_js(domestic_rows))
    if flow_rows:
        html = replace_block(html, "// [AUTO:FLOW_START]", "// [AUTO:FLOW_END]", build_flow_js(flow_rows))

    kospi_row = domestic_rows[0] if domestic_rows else None
    summary_js = build_summary_js(kospi_row, rate_card["y10"])
    html = replace_block(html, "// [AUTO:SUMMARY_START]", "// [AUTO:SUMMARY_END]", summary_js)

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
