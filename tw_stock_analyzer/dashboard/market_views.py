"""儀表板：消息面、基本面、籌碼顯示。"""

from __future__ import annotations

import streamlit as st

from tw_stock_analyzer.analyzer.engine import AnalysisReport
from tw_stock_analyzer.data.market_context import ensure_report_market_context


def _fmt_num(val: float | None, suffix: str = "") -> str:
    if val is None:
        return "—"
    if abs(val) >= 1e8:
        return f"{val / 1e8:.2f} 億{suffix}"
    return f"{val:,.2f}{suffix}"


def render_market_context(report: AnalysisReport) -> None:
    ctx = ensure_report_market_context(report)
    f = ctx.fundamentals

    st.subheader("基本面")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("本益比 PER", _fmt_num(f.pe_ratio))
    c2.metric("股價淨值比 PBR", _fmt_num(f.pb_ratio))
    c3.metric("EPS", _fmt_num(f.eps))
    c4.metric(
        "月營收 YoY",
        f"{f.revenue_yoy_pct:+.1f}%" if f.revenue_yoy_pct is not None else "—",
    )
    c5.metric(
        "殖利率",
        f"{f.dividend_yield_pct:.2f}%"
        if f.dividend_yield_pct is not None
        else "—",
    )
    if f.sources:
        st.caption("資料來源：" + "、".join(f.sources))

    st.subheader("籌碼（三大法人）")
    if ctx.institutional:
        i = ctx.institutional
        st.caption(f"近 {i.period_days} 個交易日淨買超（張）· 截至 {i.latest_date}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("外資", f"{i.foreign_net:,.0f}")
        c2.metric("投信", f"{i.trust_net:,.0f}")
        c3.metric("自營商", f"{i.dealer_net:,.0f}")
        c4.metric("合計", f"{i.total_net:,.0f}")
    else:
        st.info("未取得法人籌碼，請設定 FINMIND_API_TOKEN 後重新分析。")

    st.subheader("題材偵測")
    if ctx.themes:
        cols = st.columns(min(len(ctx.themes), 4))
        for col, hit in zip(cols, ctx.themes):
            col.success(f"**{hit.theme}**（{hit.score} 則）")
    else:
        st.caption("近期新聞標題未命中預設題材關鍵字（AI、法說、訂單等）")

    tab_news, tab_ann, tab_social = st.tabs(["新聞", "公告", "社群"])

    with tab_news:
        _news_list(ctx.news, empty="暫無新聞")

    with tab_ann:
        _news_list(ctx.announcements, empty="暫無公告相關消息")

    with tab_social:
        _news_list(ctx.social, empty="暫無社群 / Google News 結果")

    if ctx.notes:
        with st.expander("資料說明與限制"):
            for note in ctx.notes:
                st.markdown(f"- {note}")


def _news_list(items, empty: str) -> None:
    if not items:
        st.caption(empty)
        return
    for item in items:
        link = item.link or "#"
        st.markdown(
            f"**[{item.title}]({link})**  \n"
            f"{item.source} · {item.published_at} · {item.category}"
        )
        if item.summary:
            st.caption(item.summary[:120])
