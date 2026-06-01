"""命令列介面。"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tw_stock_analyzer.analyzer.engine import StockAnalyzer
from tw_stock_analyzer.backtest.engine import BacktestEngine


def _make_console() -> Console:
    """建立相容 Windows 主控台編碼的 Rich Console。"""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    return Console(legacy_windows=False)


console = _make_console()


def _fmt(val: float | None) -> str:
    return f"{val:,.2f}" if val is not None else "—"


@click.group()
@click.version_option(package_name="tw-stock-analyzer")
def main() -> None:
    """台灣股票技術分析與價格預測工具。"""


@main.command("analyze")
@click.argument("symbol")
@click.option(
    "--period",
    "-p",
    default="2y",
    show_default=True,
    help="歷史資料期間（yfinance period）",
)
@click.option(
    "--horizon",
    "-h",
    "horizon_days",
    default=5,
    show_default=True,
    type=int,
    help="預測天數",
)
def analyze_cmd(symbol: str, period: str, horizon_days: int) -> None:
    """分析指定台股代號，例如：tw-stock analyze 2330"""
    try:
        with console.status(f"[bold green]正在分析 {symbol}…"):
            report = StockAnalyzer(horizon_days=horizon_days).analyze(
                symbol, period=period
            )
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise SystemExit(1) from e

    pred = report.prediction
    latest = report.ohlcv.iloc[-1]

    console.print()
    console.print(
        Panel(
            f"[bold]{report.name}[/bold] ({report.symbol})\n"
            f"資料截至：{report.latest_date:%Y-%m-%d}  |  期間：{report.period}",
            title="台股分析報告",
            border_style="blue",
        )
    )

    price_table = Table(title="價格與預測", show_header=True)
    price_table.add_column("項目", style="cyan")
    price_table.add_column("數值", justify="right")
    price_table.add_row("目前收盤", f"{pred.current_price:,.2f}")
    price_table.add_row(
        f"預估 {pred.horizon_days} 日後",
        f"{pred.predicted_price:,.2f} ({pred.predicted_change_pct:+.2f}%)",
    )
    price_table.add_row("綜合方向", f"[bold]{pred.direction}[/bold]")
    price_table.add_row("模型信心 (R²)", f"{pred.confidence:.2%}")
    console.print(price_table)

    signal_table = Table(title="技術訊號", show_header=True)
    signal_table.add_column("指標", style="cyan")
    signal_table.add_column("狀態")
    for name, status in pred.signals.items():
        signal_table.add_row(name, status)
    signal_table.add_row("RSI(14)", f"{latest['rsi_14']:.1f}")
    signal_table.add_row("MACD 柱", f"{latest['macd_hist']:.4f}")
    console.print(signal_table)

    ctx = report.market_context
    f = ctx.fundamentals
    fund_table = Table(title="基本面", show_header=True)
    fund_table.add_column("項目", style="cyan")
    fund_table.add_column("數值", justify="right")
    fund_table.add_row("本益比 PER", _fmt(f.pe_ratio))
    fund_table.add_row("PBR", _fmt(f.pb_ratio))
    fund_table.add_row("EPS", _fmt(f.eps))
    fund_table.add_row(
        "月營收 YoY",
        f"{f.revenue_yoy_pct:+.1f}%" if f.revenue_yoy_pct is not None else "—",
    )
    console.print(fund_table)

    if ctx.institutional:
        i = ctx.institutional
        chip_table = Table(
            title=f"籌碼（近 {i.period_days} 日淨買超，張）", show_header=True
        )
        chip_table.add_column("法人", style="cyan")
        chip_table.add_column("淨買超", justify="right")
        chip_table.add_row("外資", f"{i.foreign_net:,.0f}")
        chip_table.add_row("投信", f"{i.trust_net:,.0f}")
        chip_table.add_row("自營商", f"{i.dealer_net:,.0f}")
        chip_table.add_row("合計", f"{i.total_net:,.0f}")
        console.print(chip_table)

    if ctx.themes:
        console.print(f"[cyan]題材：[/cyan]{ctx.themes_summary()}")

    if ctx.news:
        news_table = Table(title="近期新聞（前 5 則）", show_header=True)
        news_table.add_column("標題")
        news_table.add_column("來源")
        for n in ctx.news[:5]:
            news_table.add_row(n.title[:50], n.source)
        console.print(news_table)

    if ctx.notes:
        console.print("[dim]" + " | ".join(ctx.notes[:2]) + "[/dim]")

    console.print()
    console.print(Panel(report.summary, title="摘要", border_style="green"))
    console.print(
        "[dim]免責聲明：本工具輸出僅供學習與研究，不構成任何投資建議。[/dim]"
    )


@main.command("backtest")
@click.argument("symbol")
@click.option(
    "--period",
    "-p",
    default="2y",
    show_default=True,
    help="歷史資料期間（yfinance period）",
)
@click.option(
    "--hold",
    "hold_days",
    default=5,
    show_default=True,
    type=int,
    help="持有天數（出場）",
)
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(["composite", "rsi", "both"], case_sensitive=False),
    default="both",
    show_default=True,
    help="回測策略：composite=綜合方向, rsi=RSI超賣, both=兩者比較",
)
def backtest_cmd(symbol: str, period: str, hold_days: int, strategy: str) -> None:
    """回測策略並比較績效，例如：tw-stock backtest 2330 --strategy both"""
    try:
        with console.status(f"[bold green]正在回測 {symbol}…"):
            report = BacktestEngine(hold_days=hold_days).run(
                symbol, period=period, strategy=strategy.lower()
            )
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise SystemExit(1) from e

    console.print()
    console.print(
        Panel(
            f"[bold]{report.name}[/bold] ({report.symbol})\n"
            f"期間：{report.period}  |  持有 {report.hold_days} 日  |  "
            f"Buy & Hold：{report.buy_hold_return_pct:+.2f}%",
            title="回測報告",
            border_style="blue",
        )
    )

    table = Table(title="策略績效比較", show_header=True)
    table.add_column("策略", style="cyan")
    table.add_column("總報酬", justify="right")
    table.add_column("年化", justify="right")
    table.add_column("勝率", justify="right")
    table.add_column("均筆", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("交易次數", justify="right")
    table.add_column("vs B&H", justify="right")

    for s in report.strategies:
        m = s.metrics
        vs_style = "green" if m.vs_buy_hold_pct > 0 else "red" if m.vs_buy_hold_pct < 0 else "white"
        table.add_row(
            m.strategy_name,
            f"{m.total_return_pct:+.2f}%",
            f"{m.annualized_return_pct:+.2f}%",
            f"{m.win_rate_pct:.1f}%",
            f"{m.avg_trade_return_pct:+.2f}%",
            f"{m.max_drawdown_pct:.2f}%",
            str(m.num_trades),
            f"[{vs_style}]{m.vs_buy_hold_pct:+.2f}%[/{vs_style}]",
        )

    console.print(table)

    best = max(report.strategies, key=lambda s: s.metrics.total_return_pct)
    console.print()
    console.print(
        Panel(
            f"本期間總報酬最高：[bold]{best.metrics.strategy_name}[/bold] "
            f"（{best.metrics.total_return_pct:+.2f}%）。\n"
            f"回測僅供研究參考，過去績效不代表未來表現。",
            title="結論",
            border_style="green",
        )
    )
    console.print(
        "[dim]免責聲明：本工具輸出僅供學習與研究，不構成任何投資建議。[/dim]"
    )


if __name__ == "__main__":
    main()
