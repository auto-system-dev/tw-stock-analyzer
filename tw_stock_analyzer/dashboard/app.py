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
from tw_stock_analyzer.dashboard.screener_service import run_screen
from tw_stock_analyzer.dashboard.service import run_analysis
from tw_stock_analyzer.indicators.chart_timeframe import (
    CHART_TIMEFRAME_OPTIONS,
    DISPLAY_RANGE_OPTIONS,
    TIMEFRAME_SPECS,
    fib_lookback_bars,
    prepare_chart_data,
    slice_chart_display_range,
)
from tw_stock_analyzer.indicators.fibonacci import compute_fibonacci_retracement

# 分析報告結構版本；變更時清除舊 session 快取
REPORT_CACHE_VERSION = 7

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


def render_sidebar() -> tuple[str, str, str, int, bool, bool, dict, bool, int]:
    if "symbol" not in st.session_state:
        st.session_state.symbol = "2330"

    screen_opts: dict = {}

    with st.sidebar:
        st.title("📈 台股分析")
        st.caption("技術分析 · 潛力評分 · 批次掃描")
        page = st.radio(
            "功能",
            ["單檔分析", "潛力股掃描"],
            horizontal=True,
            label_visibility="collapsed",
            key="page_mode",
        )
        st.divider()

        if page == "潛力股掃描":
            screen_opts["universe"] = st.selectbox(
                "股票池",
                ["watchlist", "all"],
                format_func=lambda x: "常用股" if x == "watchlist" else "全市場",
            )
            screen_opts["symbols_csv"] = st.text_input(
                "自訂代號（選填，逗號分隔）",
                placeholder="2330,2454,2303",
            )
            screen_opts["top_n"] = st.slider("Top N", 5, 30, 10)
            screen_opts["min_score"] = st.slider("最低綜合分", 0, 80, 0, step=5)
            screen_opts["bullish_only"] = st.checkbox("僅看多")
            screen_opts["period"] = st.selectbox(
                "掃描資料期間",
                list(PERIOD_OPTIONS.keys()),
                index=2,
            )
            run_screen_btn = st.button("開始掃描", type="primary", use_container_width=True)
            screen_opts["run"] = run_screen_btn
            st.divider()
            st.caption("股價：Yahoo · 籌碼/營收：FinMind · 僅供研究參考")
            return "", "", page, 5, False, False, screen_opts, False, 60

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
        show_fibonacci = st.checkbox("顯示斐波那契回撤", value=False)
        fib_lookback = 60
        if show_fibonacci:
            fib_lookback = st.selectbox(
                "斐波那契波段天數",
                [60, 120],
                format_func=lambda x: f"{x} 日",
            )
        analyze = st.button("開始分析", type="primary", use_container_width=True)
        run_bt = st.button("執行回測", use_container_width=True)

        st.divider()
        st.caption("股價：Yahoo · 籌碼/營收：FinMind · 僅供研究參考")

    period = PERIOD_OPTIONS[period_label]
    return symbol.strip(), period, page, horizon_days, analyze, run_bt, screen_opts, show_fibonacci, fib_lookback


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
    ps = report.potential_score
    delta_mode, arrow = DIRECTION_STYLE.get(pred.direction, ("off", "→"))

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("目前收盤", f"{pred.current_price:,.2f} 元")
    c2.metric(
        f"預估 {pred.horizon_days} 日後",
        f"{pred.predicted_price:,.2f} 元",
        f"{pred.predicted_change_pct:+.2f}%",
    )
    c3.metric("綜合方向", f"{arrow} {pred.direction}", delta_color=delta_mode)
    c4.metric("潛力評分", f"{ps.total}/100", f"{ps.grade} 級")
    c5.metric("持有類型", ps.holding_type, ps.holding_period)
    c6.metric("模型信心 (R²)", f"{pred.confidence:.1%}")


def render_potential_score(report: AnalysisReport) -> None:
    ps = report.potential_score
    st.subheader("潛力評分")
    st.caption(f"持有類型：**{ps.holding_type}** · 參考持有 {ps.holding_period}（依評分維度推估，非投資建議）")
    cols = st.columns(5)
    for col, (label, val, mx) in zip(
        cols,
        [
            ("技術+ML", ps.technical, 25),
            ("基本面", ps.fundamental, 25),
            ("籌碼", ps.institutional, 25),
            ("題材", ps.theme, 10),
            ("動能", ps.momentum, 15),
        ],
    ):
        col.metric(label, f"{val}/{mx}")
    if ps.reasons:
        with st.expander("評分理由"):
            for reason in ps.reasons:
                st.write(f"- {reason}")


def render_signals(report: AnalysisReport) -> None:
    pred = report.prediction
    latest = report.ohlcv.iloc[-1]

    st.subheader("技術訊號")
    cols = st.columns(len(pred.signals) + 2)
    for col, (name, status) in zip(cols, pred.signals.items()):
        col.info(f"**{name}**\n\n{status}")
    cols[-2].info(f"**RSI (14)**\n\n{latest['rsi_14']:.1f}")
    cols[-1].info(f"**MACD 柱**\n\n{latest['macd_hist']:.4f}")


def _navigate_to_analyze(symbol: str) -> None:
    """從掃描結果跳轉至單檔分析。"""
    st.session_state.symbol = symbol
    st.session_state.page_mode = "單檔分析"
    st.session_state.auto_analyze = True


def render_screener_page(screen_opts: dict) -> None:
    st.header("潛力股掃描")
    st.caption("兩階段掃描：快速技術篩選 → 深度基本面/籌碼評分（批次略過 ML 以加速）")

    if screen_opts.get("run"):
        universe = screen_opts["universe"]
        symbols_csv = screen_opts.get("symbols_csv", "")
        top_n = screen_opts["top_n"]
        min_score = screen_opts["min_score"]
        bullish_only = screen_opts["bullish_only"]
        period = PERIOD_OPTIONS[screen_opts["period"]]

        try:
            with st.spinner("正在掃描…（常用股約 1–2 分鐘，全市場較久）"):
                result = run_screen(
                    universe,
                    symbols_csv,
                    top_n,
                    min_score,
                    bullish_only,
                    period,
                )
            st.session_state["screener_result"] = result
        except Exception as e:
            st.error(f"掃描失敗：{e}")
            return

    result = st.session_state.get("screener_result")
    if result is None:
        st.info("在左側設定股票池與篩選條件，按 **開始掃描**。")
        return

    st.success(
        f"{result.universe_label} · 掃描 {result.scanned_count} 檔 · "
        f"深度 {result.deep_scanned_count} 檔 · 符合 {len(result.ranked)} 檔"
    )
    for note in result.notes:
        st.caption(note)

    if not result.ranked:
        st.warning("無符合條件的標的，請調低最低分或更換股票池。")
        return

    rows = []
    for i, row in enumerate(result.ranked, start=1):
        s = row.score
        rows.append(
            {
                "排名": i,
                "代號": row.symbol,
                "名稱": row.name,
                "總分": s.total,
                "等級": s.grade,
                "持有類型": s.holding_type,
                "參考持有": s.holding_period,
                "方向": row.direction,
                "技術": s.technical,
                "基本面": s.fundamental,
                "籌碼": s.institutional,
                "題材": s.theme,
                "動能": s.momentum,
                "重點": " · ".join(s.reasons[:2]),
            }
        )
    st.dataframe(rows, use_container_width=True)

    st.markdown("**點選代號進行單檔分析**")
    pick_cols = st.columns(min(len(result.ranked), 5))
    for col, row in zip(pick_cols, result.ranked[:5]):
        col.button(
            f"{row.symbol} {row.name[:4]}",
            key=f"pick_{row.symbol}",
            use_container_width=True,
            on_click=_navigate_to_analyze,
            args=(row.symbol,),
        )


def main() -> None:
    if st.session_state.get("report_cache_version") != REPORT_CACHE_VERSION:
        for key in ("last_report", "cache_key"):
            st.session_state.pop(key, None)
        st.session_state["report_cache_version"] = REPORT_CACHE_VERSION

    # 掃描結果點選後，先切換頁面再渲染側欄
    pending_analyze = st.session_state.pop("auto_analyze", False)
    if pending_analyze:
        st.session_state.page_mode = "單檔分析"

    symbol, period, page, horizon_days, analyze, run_bt, screen_opts, show_fibonacci, fib_lookback = render_sidebar()

    if page == "潛力股掃描":
        render_screener_page(screen_opts)
        st.caption("免責聲明：本工具輸出僅供學習與研究，不構成任何投資建議。")
        return

    if pending_analyze:
        analyze = True

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
    render_potential_score(report)
    st.divider()

    tab_chart, tab_signal, tab_market, tab_summary, tab_backtest = st.tabs(
        ["圖表", "訊號", "消息面", "摘要", "回測"]
    )

    with tab_chart:
        ctrl1, ctrl2 = st.columns(2)
        with ctrl1:
            chart_timeframe = st.radio(
                "K 線週期",
                CHART_TIMEFRAME_OPTIONS,
                horizontal=True,
                key="chart_timeframe",
            )
        with ctrl2:
            chart_range = st.radio(
                "顯示範圍",
                DISPLAY_RANGE_OPTIONS,
                horizontal=True,
                key="chart_display_range",
            )
        chart_spec = TIMEFRAME_SPECS[chart_timeframe]
        st.caption(
            "圖表週期與顯示範圍僅影響 K 線；均線等指標依側欄「歷史資料期間」完整資料計算。"
            " 訊號、評分與預測仍依日線。"
        )

        try:
            chart_df = prepare_chart_data(report.ohlcv, chart_timeframe)
        except ValueError as e:
            st.warning(str(e))
            chart_df = report.ohlcv
            chart_timeframe = "日線"
            chart_spec = TIMEFRAME_SPECS["日線"]

        display_df = slice_chart_display_range(chart_df, chart_range)

        fib_bars = fib_lookback_bars(chart_timeframe, fib_lookback)
        fib = (
            compute_fibonacci_retracement(display_df, lookback=fib_bars)
            if show_fibonacci
            else None
        )
        if show_fibonacci and fib is None:
            st.caption("資料不足，無法計算斐波那契回撤。")
        elif show_fibonacci:
            st.caption(
                f"斐波那契回撤：{fib.trend}波段 · 近 {fib_bars} {chart_spec.fib_unit} · "
                f"高 {fib.swing_high:,.2f}（{fib.swing_high_date:%Y-%m-%d}）· "
                f"低 {fib.swing_low:,.2f}（{fib.swing_low_date:%Y-%m-%d}）"
            )
        chart_key_suffix = f"{chart_timeframe}_{chart_range}"
        st.plotly_chart(
            build_price_chart(
                display_df,
                f"{report.name}（{report.symbol}）股價與均線",
                fib=fib,
                spec=chart_spec,
                fib_unit=chart_spec.fib_unit,
            ),
            use_container_width=True,
            key=f"chart_price_{chart_key_suffix}",
        )
        st.plotly_chart(
            build_indicator_chart(display_df),
            use_container_width=True,
            key=f"chart_indicator_{chart_key_suffix}",
        )
        st.plotly_chart(
            build_volume_chart(display_df),
            use_container_width=True,
            key=f"chart_volume_{chart_key_suffix}",
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
            "sma_50",
            "sma_200",
            "macd_hist",
        ]
        st.dataframe(
            report.ohlcv[display_cols].tail(10).sort_index(ascending=False),
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
