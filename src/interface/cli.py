import click
import schedule
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from loguru import logger
from datetime import datetime

console = Console()


@click.command()
@click.option("--date", "-d", default=None, help="指定日期(YYYYMMDD)，不传则默认今天")
@click.option("--backfill", "-b", nargs=2, type=str, default=None, help="全量补跑: -b 起始日期 结束日期")
@click.option("--phase1", "-p1", nargs=2, type=str, default=None, help="第一阶段: 仅采集日线+复权数据(快)")
@click.option("--phase2", "-p2", nargs=2, type=str, default=None, help="第二阶段: 因子计算+选股+风控+进化")
@click.option("--moneyflow", "-mf", nargs=2, type=str, default=None, help="补跑资金流向: -mf 起始日期 结束日期")
@click.option("--dailybasic", "-db", nargs=2, type=str, default=None, help="补跑每日指标(PE/PB/市值): -db 起始日期 结束日期")
@click.option("--check", "-c", nargs=2, type=str, default=None, help="检查缺失: -c 起始日期 结束日期")
@click.option("--force", "-f", is_flag=True, default=False, help="强制重跑(不跳过已有数据)")
@click.option("--time", "-t", default=None, help="定时模式，指定每日运行时间如 15:30")
@click.option("--reset-calendar", nargs=2, type=str, default=None, help="重置交易日历: --reset-calendar 起始年份 结束年份")
def main(date, backfill, phase1, phase2, moneyflow, dailybasic, check, force, time, reset_calendar):
    """认知型智能选股 Agent - 运行即输出选股结果"""
    from src.scheduler import Scheduler
    from src.config import start_hot_reload, get_config

    start_hot_reload()

    if phase1:
        scheduler = Scheduler()
        console.print(f"[bold cyan]第一阶段: 采集日线 ({phase1[0]} ~ {phase1[1]})[/bold cyan]")
        scheduler.run_backfill_phase1(phase1[0], phase1[1])
        console.print("[bold green]第一阶段完成[/bold green]")
        return

    if phase2:
        scheduler = Scheduler()
        label = " (强制重跑)" if force else ""
        console.print(f"[bold magenta]第二阶段: 因子+选股 ({phase2[0]} ~ {phase2[1]}){label}[/bold magenta]")
        scheduler.run_backfill_phase2(phase2[0], phase2[1], force=force)
        console.print("[bold green]第二阶段完成[/bold green]")
        return

    if moneyflow:
        scheduler = Scheduler()
        console.print(f"[bold yellow]补跑资金流向: {moneyflow[0]} ~ {moneyflow[1]}[/bold yellow]")
        scheduler.run_backfill_moneyflow(moneyflow[0], moneyflow[1])
        console.print("[bold green]资金流向补跑完成[/bold green]")
        return

    if dailybasic:
        scheduler = Scheduler()
        console.print(f"[bold yellow]补跑每日指标(PE/PB/市值): {dailybasic[0]} ~ {dailybasic[1]}[/bold yellow]")
        scheduler.run_backfill_daily_basic(dailybasic[0], dailybasic[1])
        console.print("[bold green]每日指标补跑完成[/bold green]")
        return

    if reset_calendar:
        scheduler = Scheduler()
        console.print(f"[bold cyan]重置交易日历: {reset_calendar[0]}~{reset_calendar[1]}年[/bold cyan]")
        scheduler.collector.reset_trade_calendar(reset_calendar[0], reset_calendar[1])
        console.print("[bold green]交易日历重置完成[/bold green]")
        return

    if check:
        scheduler = Scheduler()
        result = scheduler.get_missing_dates(check[0], check[1])
        console.print(f"\n[bold]交易日: {result['total_trade_days']} 天[/bold]")
        console.print(f"[red]缺失行情: {len(result['missing_data'])} 天[/red]  {result['missing_data'][:20]}{'...' if len(result['missing_data'])>20 else ''}")
        console.print(f"[yellow]缺失因子: {len(result['missing_factor'])} 天[/yellow]  {result['missing_factor'][:20]}{'...' if len(result['missing_factor'])>20 else ''}")
        console.print(f"[cyan]缺失决策: {len(result['missing_decision'])} 天[/cyan]  {result['missing_decision'][:20]}{'...' if len(result['missing_decision'])>20 else ''}")
        return

    if backfill:
        scheduler = Scheduler()
        console.print(f"[bold blue]全量补跑: {backfill[0]} ~ {backfill[1]}[/bold blue]")
        scheduler.run_backfill(backfill[0], backfill[1])
        console.print("[bold green]补跑完成[/bold green]")
        return

    if time:
        scheduler = Scheduler()
        cfg = get_config()

        def job():
            today = datetime.now().strftime("%Y%m%d")
            console.print(Panel(f"[bold green]自动选股: {today}[/bold green]"))
            holdings = scheduler.run_daily(today)
            _print_result(holdings, today)

        schedule.every().day.at(time).do(job)
        console.print(f"[bold blue]每日 {time} 自动选股[/bold blue] (Ctrl+C 退出)")
        while True:
            schedule.run_pending()
            time.sleep(30)
        return

    trade_date = date or datetime.now().strftime("%Y%m%d")
    scheduler = Scheduler()

    console.print(Panel(
        f"[bold green]认知型智能选股 Agent[/bold green]\n"
        f"交易日期: {trade_date}"
    ))

    holdings = scheduler.run_daily(trade_date)

    _print_result(holdings, trade_date)


def _print_result(holdings, trade_date):
    if not holdings:
        console.print("[bold red]无选股结果[/bold red]")
        return

    table = Table(title=f"选股结果 ({trade_date})")
    table.add_column("#", style="white", width=3)
    table.add_column("股票代码", style="cyan")
    table.add_column("权重", style="magenta")
    table.add_column("理由", style="white")

    for i, h in enumerate(sorted(holdings, key=lambda x: x.get("weight", 0), reverse=True), 1):
        table.add_row(
            str(i),
            h.get("ts_code", ""),
            f"{h.get('weight', 0):.2%}",
            h.get("reason", ""),
        )
    console.print(table)

    codes = [h.get("ts_code", "") for h in sorted(holdings, key=lambda x: x.get("weight", 0), reverse=True)]
    console.print(f"\n[bold green]持仓代码: {', '.join(codes)}[/bold green]")
