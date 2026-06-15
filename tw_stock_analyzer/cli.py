"""命令列介面。"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tw_stock_analyzer.analyzer.engine import StockAnalyzer
from tw_stock_analyzer.backtest.engine import BacktestEngine
from tw_stock_analyzer.notifications.resonance_alert import (
    format_resonance_telegram_message,
    scan_resonance_with_summary,
)
from tw_stock_analyzer.notifications.telegram import TelegramConfigError, send_telegram_message
from tw_stock_analyzer.screener.engine import ScreenerEngine
from tw_stock_analyzer.screener.filters import ScreenerFilters
from tw_stock_analyzer.screener.universe import get_universe


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

    ps = report.potential_score
    score_table = Table(title="潛力評分", show_header=True)
    score_table.add_column("維度", style="cyan")
    score_table.add_column("分數", justify="right")
    score_table.add_row("技術 + ML", f"{ps.technical}/25")
    score_table.add_row("基本面", f"{ps.fundamental}/25")
    score_table.add_row("籌碼", f"{ps.institutional}/25")
    score_table.add_row("題材", f"{ps.theme}/10")
    score_table.add_row("動能", f"{ps.momentum}/15")
    score_table.add_row("綜合", f"[bold]{ps.total}/100 ({ps.grade})[/bold]")
    score_table.add_row("持有類型", f"{ps.holding_type}（{ps.holding_period}）")
    console.print(score_table)
    if ps.reasons:
        console.print("[cyan]評分理由：[/cyan]" + " · ".join(ps.reasons[:5]))

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


@main.command("screen")
@click.option(
    "--universe",
    "-u",
    type=click.Choice(["watchlist", "all"], case_sensitive=False),
    default="watchlist",
    show_default=True,
    help="股票池：watchlist=常用股, all=全市場",
)
@click.option(
    "--symbols",
    "-s",
    default="",
    help="自訂代號（逗號分隔，如 2330,2454），指定時忽略 --universe",
)
@click.option("--top", default=10, show_default=True, type=int, help="輸出 Top N")
@click.option(
    "--min-score",
    default=0,
    show_default=True,
    type=int,
    help="最低綜合分",
)
@click.option(
    "--bullish-only",
    is_flag=True,
    default=False,
    help="僅保留綜合方向「看多」",
)
@click.option(
    "--period",
    "-p",
    default="1y",
    show_default=True,
    help="快速掃描用的歷史資料期間",
)
def screen_cmd(
    universe: str,
    symbols: str,
    top: int,
    min_score: int,
    bullish_only: bool,
    period: str,
) -> None:
    """掃描潛力股並依綜合分排名，例如：tw-stock screen --universe watchlist --top 10"""
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    flt = ScreenerFilters(
        min_score=min_score,
        top_n=top,
        bullish_only=bullish_only,
    )
    engine = ScreenerEngine(period=period)

    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            fast_task = progress.add_task("快速掃描…", total=1)
            deep_task = progress.add_task("深度評分…", total=1)

            def on_progress(phase: str, current: int, total: int) -> None:
                if phase == "fast":
                    progress.update(fast_task, total=max(total, 1), completed=current)
                else:
                    progress.update(deep_task, total=max(total, 1), completed=current)

            result = engine.scan(
                universe=universe.lower(),
                symbols=sym_list,
                filters=flt,
                progress=on_progress,
            )
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise SystemExit(1) from e

    console.print()
    console.print(
        Panel(
            f"股票池：{result.universe_label}\n"
            f"成功 {result.scanned_count}/{result.universe_total or result.scanned_count} 檔"
            f"（略過 {result.skipped_count or max(0, (result.universe_total or result.scanned_count) - result.scanned_count)} 檔無資料） · "
            f"深度評分 {result.deep_scanned_count} 檔 · "
            f"符合條件 {len(result.ranked)} 檔",
            title="潛力股掃描",
            border_style="blue",
        )
    )

    for note in result.notes:
        console.print(f"[dim]{note}[/dim]")

    if not result.ranked:
        console.print("[yellow]無符合條件的標的，可調低 --min-score 或更換股票池。[/yellow]")
        return

    table = Table(title=f"Top {len(result.ranked)} 潛力股", show_header=True)
    table.add_column("#", style="dim")
    table.add_column("代號", style="cyan")
    table.add_column("名稱")
    table.add_column("總分", justify="right")
    table.add_column("等級", justify="center")
    table.add_column("方向")
    table.add_column("持有類型")
    table.add_column("技術", justify="right")
    table.add_column("基本面", justify="right")
    table.add_column("籌碼", justify="right")
    table.add_column("動能", justify="right")

    for i, row in enumerate(result.ranked, start=1):
        s = row.score
        table.add_row(
            str(i),
            row.symbol,
            row.name[:8],
            str(s.total),
            s.grade,
            row.direction,
            s.holding_type,
            str(s.technical),
            str(s.fundamental),
            str(s.institutional),
            str(s.momentum),
        )

    console.print(table)
    console.print()
    console.print(
        "[dim]免責聲明：本工具輸出僅供學習與研究，不構成任何投資建議。[/dim]"
    )


@main.command("notify-resonance")
@click.option(
    "--universe",
    "-u",
    type=click.Choice(["watchlist", "all"], case_sensitive=False),
    default="watchlist",
    show_default=True,
    help="股票池",
)
@click.option(
    "--symbols",
    "-s",
    default="",
    help="自訂代號（逗號分隔），指定時忽略 --universe",
)
@click.option(
    "--min-resonance",
    default=5,
    show_default=True,
    type=click.IntRange(1, 6),
    help="至少符合幾項多頭共振（1～6）",
)
@click.option(
    "--period",
    "-p",
    default="1y",
    show_default=True,
    help="掃描用的歷史資料期間",
)
@click.option(
    "--batch-size",
    default=50,
    show_default=True,
    type=click.IntRange(10, 200),
    help="全市場掃描每批檔數（分批掃描後合併結果）",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="只掃描並印出訊息，不發送 Telegram",
)
@click.option(
    "--notify-empty",
    is_flag=True,
    default=False,
    help="無符合標的時也發送 Telegram（預設僅在有符合時發送）",
)
def notify_resonance_cmd(
    universe: str,
    symbols: str,
    min_resonance: int,
    period: str,
    batch_size: int,
    dry_run: bool,
    notify_empty: bool,
) -> None:
    """掃描多頭共振並發送 Telegram，例如：tw-stock notify-resonance --min-resonance 5"""
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    _, universe_label = get_universe(universe.lower(), sym_list)
    u = universe.lower()

    def on_progress(scanned: int, total: int, batch_index: int) -> None:
        console.print(
            f"[dim]批次 {batch_index} 完成 · 已掃 {scanned}/{total} 檔[/dim]"
        )

    try:
        if u == "all" and not sym_list:
            console.print(
                f"[cyan]全市場分批掃描（每批 {batch_size} 檔），完成後合併結果…[/cyan]"
            )
            summary = scan_resonance_with_summary(
                universe=u,
                symbols=sym_list,
                min_passed=min_resonance,
                period=period,
                batch_size=batch_size,
                on_progress=on_progress,
            )
        else:
            with console.status("[bold green]掃描多頭共振…"):
                summary = scan_resonance_with_summary(
                    universe=u,
                    symbols=sym_list,
                    min_passed=min_resonance,
                    period=period,
                    batch_size=batch_size,
                )
        hits = list(summary.hits)
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise SystemExit(1) from e

    console.print(
        f"[green]掃描完成：{summary.scanned_count}/{summary.total_count} 檔"
        f" · {summary.batch_count} 批 · 符合 {len(hits)} 檔[/green]"
    )

    message = format_resonance_telegram_message(
        hits,
        min_passed=min_resonance,
        universe_label=universe_label,
        scanned_count=summary.scanned_count,
        total_count=summary.total_count,
    )
    console.print(message)

    if dry_run:
        console.print("[yellow]dry-run 模式，未發送 Telegram。[/yellow]")
        return

    if not hits and not notify_empty:
        console.print("[dim]無符合標的，略過 Telegram 通知。[/dim]")
        return

    try:
        send_telegram_message(message)
    except TelegramConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e
    except Exception as e:
        console.print(f"[red]Telegram 發送失敗：{e}[/red]")
        raise SystemExit(1) from e

    console.print(f"[green]已發送 Telegram（{len(hits)} 檔符合 ≥ {min_resonance}/6）。[/green]")


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
