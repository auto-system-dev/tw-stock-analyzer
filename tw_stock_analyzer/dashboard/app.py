"""Streamlit 網頁儀表板主程式。"""

from __future__ import annotations

import streamlit as st

from tw_stock_analyzer.analyzer.engine import AnalysisReport
from tw_stock_analyzer.backtest.engine import ComparisonReport
from tw_stock_analyzer.dashboard.backtest_service import run_backtest
from tw_stock_analyzer.dashboard.charts import (
    build_indicator_chart,
    build_price_chart,
    build_volume_chart,
)
from tw_stock_analyzer.dashboard.equity_chart import build_equity_chart
from tw_stock_analyzer.data.market_context import ensure_report_market_context
from tw_stock_analyzer.dashboard.market_views import render_market_context
from tw_stock_analyzer.dashboard.service import run_analysis

# 分析報告結構版本；變更時清除舊 session 快取
REPORT_CACHE_VERSION = 3

PERIOD_OPTIONS = {
    "3 個月": "3mo",
    "6 個月": "6mo",
    "1 年": "1y",
    "2 年": "2y",
    "5 年": "5y",
}

DIRECTION_STYLE = {
    "看多": ("normal", "↑"),
    "看空": ("inverse", "↓"),
    "中性": ("off", "→"),
}


st.set_page_config(
    page_title="台股分析儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"],
    .main .block-container,
    .block-container {
        padding-top: 2.5rem;
    }
    [data-testid="stHeader"] {
        background: transparent;
    }
    h1, h2, h3, [data-testid="stHeading"] {
        overflow: visible !important;
        line-height: 1.35 !important;
        padding-top: 0.15rem;
    }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 0.6rem;
        padding: 0.75rem 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_sidebar() -> tuple[str, str, int, bool, bool]:
    if "symbol" not in st.session_state:
        st.session_state.symbol = "2330"

    with st.sidebar:
        st.title("📈 台股分析")
        st.caption("技術分析與價格趨勢預測")
        st.divider()

        st.markdown("**常用標的**")
        cols = st.columns(3)
        for i, code in enumerate(["2330", "2317", "2454", "2303", "2881"]):
            if cols[i % 3].button(code, use_container_width=True, key=f"preset_{code}"):
                st.session_state.symbol = code
                st.rerun()

        symbol = st.text_input(
            "股票代號",
            key="symbol",
            help="輸入 4 碼代號，如 2330、2317",
        )
        period_label = st.selectbox("歷史資料期間", list(PERIOD_OPTIONS.keys()), index=3)
        horizon_days = st.slider("預測天數", min_value=1, max_value=20, value=5)
        analyze = st.button("開始分析", type="primary", use_container_width=True)
        run_bt = st.button("執行回測", use_container_width=True)

        st.divider()
        st.caption("股價：Yahoo · 籌碼/營收：FinMind · 僅供研究參考")

    period = PERIOD_OPTIONS[period_label]
    return symbol.strip(), period, horizon_days, analyze, run_bt


def render_backtest(symbol: str, period: str, horizon_days: int) -> bool:
    """執行回測並寫入 session，回傳是否成功。"""
    cache_key = f"bt_{symbol}_{period}_{horizon_days}"
    try:
        with st.spinner(f"正在回測 {symbol}…"):
            comparison = run_backtest(symbol, period, horizon_days, "both")
        st.session_state["backtest_report"] = comparison
        st.session_state["backtest_cache_key"] = cache_key
        return True
    except Exception as e:
        st.error(f"回測失敗：{e}")
        return False


def _display_backtest(comparison: ComparisonReport, *, chart_key: str = "bt_equity") -> None:
    st.subheader("回測比較")
    st.caption(
        f"Buy & Hold：**{comparison.buy_hold_return_pct:+.2f}%** · "
        f"持有 {comparison.hold_days} 日 · 已扣手續費 · 綜合方向（僅規則）vs RSI≤30"
    )

    cols = st.columns(len(comparison.strategies))
    for col, s in zip(cols, comparison.strategies):
        m = s.metrics
        col.metric(
            m.strategy_name,
            f"{m.total_return_pct:+.2f}%",
            f"vs B&H {m.vs_buy_hold_pct:+.2f}%",
        )

    curves = {s.metrics.strategy_name: s.equity_curve for s in comparison.strategies}
    st.plotly_chart(
        build_equity_chart(curves, comparison.buy_hold_return_pct),
        use_container_width=True,
        key=chart_key,
    )

    rows = []
    for s in comparison.strategies:
        m = s.metrics
        rows.append(
            {
                "策略": m.strategy_name,
                "總報酬%": m.total_return_pct,
                "年化%": m.annualized_return_pct,
                "勝率%": m.win_rate_pct,
                "均筆報酬%": m.avg_trade_return_pct,
                "最大回撤%": m.max_drawdown_pct,
                "交易次數": m.num_trades,
                "vs B&H%": m.vs_buy_hold_pct,
            }
        )
    st.dataframe(rows, use_container_width=True)

    best = max(comparison.strategies, key=lambda s: s.metrics.total_return_pct)
    st.success(
        f"本期間總報酬較高：**{best.metrics.strategy_name}** "
        f"（{best.metrics.total_return_pct:+.2f}%）。過去績效不代表未來表現。"
    )


def render_metrics(report: AnalysisReport) -> None:
    pred = report.prediction
    delta_mode, arrow = DIRECTION_STYLE.get(pred.direction, ("off", "→"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("目前收盤", f"{pred.current_price:,.2f} 元")
    c2.metric(
        f"預估 {pred.horizon_days} 日後",
        f"{pred.predicted_price:,.2f} 元",
        f"{pred.predicted_change_pct:+.2f}%",
    )
    c3.metric("綜合方向", f"{arrow} {pred.direction}", delta_color=delta_mode)
    c4.metric("模型信心 (R²)", f"{pred.confidence:.1%}")


def render_signals(report: AnalysisReport) -> None:
    pred = report.prediction
    latest = report.ohlcv.iloc[-1]

    st.subheader("技術訊號")
    cols = st.columns(len(pred.signals) + 2)
    for col, (name, status) in zip(cols, pred.signals.items()):
        col.info(f"**{name}**\n\n{status}")
    cols[-2].info(f"**RSI (14)**\n\n{latest['rsi_14']:.1f}")
    cols[-1].info(f"**MACD 柱**\n\n{latest['macd_hist']:.4f}")


def main() -> None:
    if st.session_state.get("report_cache_version") != REPORT_CACHE_VERSION:
        for key in ("last_report", "cache_key"):
            st.session_state.pop(key, None)
        st.session_state["report_cache_version"] = REPORT_CACHE_VERSION

    symbol, period, horizon_days, analyze, run_bt = render_sidebar()

    st.header("台股分析儀表板")
    st.caption("輸入代號後按「開始分析」或「執行回測」，或從側欄選擇常用標的")

    bt_key = f"bt_{symbol}_{period}_{horizon_days}"

    if run_bt:
        if render_backtest(symbol, period, horizon_days):
            st.success("回測完成，結果見下方或「回測」分頁。")

    if not analyze and "last_report" not in st.session_state:
        if not run_bt:
            st.info("請在左側輸入股票代號，然後按 **開始分析** 或 **執行回測**。")
            return
        if st.session_state.get("backtest_cache_key") == bt_key:
            _display_backtest(
                st.session_state["backtest_report"],
                chart_key="bt_equity_standalone",
            )
        return

    if analyze:
        cache_key = f"{symbol}_{period}_{horizon_days}"
        try:
            with st.spinner(f"正在分析 {symbol}…"):
                report = run_analysis(symbol, period, horizon_days)
            st.session_state["last_report"] = report
            st.session_state["cache_key"] = cache_key
        except Exception as e:
            st.error(f"分析失敗：{e}")
            return
    elif st.session_state.get("cache_key") != f"{symbol}_{period}_{horizon_days}":
        st.warning("參數已變更，請重新按 **開始分析**。")
        return

    report: AnalysisReport = st.session_state["last_report"]
    ensure_report_market_context(report)

    st.markdown(
        f"### {report.name} (`{report.symbol}`)  \n"
        f"資料截至 **{report.latest_date:%Y-%m-%d}** · 期間 **{report.period}** · "
        f"分析時間 {report.analyzed_at:%Y-%m-%d %H:%M}"
    )

    render_metrics(report)
    st.divider()

    tab_chart, tab_signal, tab_market, tab_summary, tab_backtest = st.tabs(
        ["圖表", "訊號", "消息面", "摘要", "回測"]
    )

    with tab_chart:
        st.plotly_chart(
            build_price_chart(
                report.ohlcv, f"{report.name}（{report.symbol}）股價與均線"
            ),
            use_container_width=True,
            key="chart_price",
        )
        st.plotly_chart(
            build_indicator_chart(report.ohlcv),
            use_container_width=True,
            key="chart_indicator",
        )
        st.plotly_chart(
            build_volume_chart(report.ohlcv),
            use_container_width=True,
            key="chart_volume",
        )

    with tab_signal:
        render_signals(report)

    with tab_market:
        render_market_context(report)

    with tab_summary:
        st.success(report.summary)
        st.caption("免責聲明：本工具輸出僅供學習與研究，不構成任何投資建議。")

    with tab_backtest:
        if st.button("在此分頁執行回測", key="bt_tab_run"):
            if render_backtest(symbol, period, horizon_days):
                st.rerun()
        if st.session_state.get("backtest_cache_key") == bt_key:
            _display_backtest(
                st.session_state["backtest_report"],
                chart_key="bt_equity_tab",
            )
        else:
            st.info("按 **執行回測**（側欄或此分頁）以比較「綜合方向」與「RSI 超賣」策略。")

    with st.expander("檢視最近 10 日資料"):
        display_cols = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "rsi_14",
            "sma_20",
            "macd_hist",
        ]
        st.dataframe(
            report.ohlcv[display_cols].tail(10).sort_index(ascending=False),
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
