"""Terminal output: panels, verdict tables and refusal cards.

One place decides how the desk looks. Agents describe what happened, never
how to draw it, so every agent prints in the same shape.

Colour and box drawing come from `rich`. When output is piped the console
degrades to plain text on its own, which keeps `--table` output clean.
"""

from __future__ import annotations

from rich.box import HEAVY_HEAD, ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Desk palette. Amber is the warden, red is a refusal, teal is the one pass.
AMBER = "#F2B04A"
DENY = "#FF5C52"
PASS = "#2dd4bf"
SLATE = "#6b7c93"
LINE = "#2b3543"

WIDTH = 112

console = Console(width=WIDTH)


def head(
    agent: str,
    subtitle: str,
    *,
    asks: str | None = None,
    bench: str | None = None,
    footer: str | None = None,
) -> None:
    """Agent banner: who is speaking, what it does, what it is about to ask."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=f"bold {AMBER}", width=7)
    grid.add_column(overflow="fold")
    grid.add_row(agent, f"[bold]{subtitle}[/]")
    if asks:
        grid.add_row("asks", f"[{SLATE}]{asks}[/]")
    if bench:
        grid.add_row("bench", bench)
    console.print(
        Panel(
            grid,
            box=ROUNDED,
            border_style=LINE,
            padding=(0, 1),
            subtitle=f"[{SLATE}]{footer}[/]" if footer else None,
            subtitle_align="right",
        )
    )
    console.print()


class VerdictTable:
    """Rows of verdicts, one line each - the desk's main view.

    Numbers live in their own columns so a long reason can never push the
    table out of shape; the full sentence belongs in a card instead.
    """

    def __init__(self, *columns: tuple[str, int, str]) -> None:
        self._table = Table(
            box=HEAVY_HEAD,
            header_style=f"bold {SLATE}",
            border_style=LINE,
            width=WIDTH,
            pad_edge=False,
            collapse_padding=True,
        )
        self._table.add_column("", width=1)
        for title, width, justify in columns:
            self._table.add_column(title, width=width, justify=justify)
        self.rows = 0

    def add(self, passed: bool, *cells: object) -> None:
        mark = Text("✓" if passed else "✗", style=PASS if passed else DENY)
        self._table.add_row(mark, *[c if isinstance(c, Text) else str(c) for c in cells])
        self.rows += 1

    def render(self) -> None:
        if self.rows:
            console.print(self._table)
            console.print()


def verdict(passed: bool, text: str) -> Text:
    """The CLEARED / DENIED cell, coloured."""
    return Text(text, style=f"bold {PASS}" if passed else f"bold {DENY}")


def value(text: object, *, good: bool | None = None) -> Text:
    """A number in a table cell, tinted when it is the one that decided."""
    style = "" if good is None else (PASS if good else DENY)
    return Text(str(text), style=style)


def rule_card(
    rule_id: str,
    agent: str,
    title: str,
    *,
    asks: str,
    denies: str,
    params: dict,
    accent: bool = False,
) -> None:
    """One rule from rules.json, laid out so the thresholds are readable."""
    tone = DENY if accent else AMBER
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=SLATE, width=7)
    grid.add_column(overflow="fold")
    grid.add_row("asks", Text(asks, style="italic"))
    grid.add_row("denies", Text(denies))
    if params:
        knobs = Table.grid(padding=(0, 2))
        knobs.add_column(style=SLATE)
        knobs.add_column(style=f"bold {tone}")
        for key, value in params.items():
            knobs.add_row(key, str(value))
        grid.add_row("params", knobs)

    console.print(
        Panel(
            grid,
            box=ROUNDED,
            border_style=LINE,
            padding=(0, 1),
            title=f"[bold {tone}]{rule_id}[/]  [bold]{agent}[/]  [{SLATE}]{title}[/]",
            title_align="left",
        )
    )


def ledger(title: str, rows: list[tuple[str, str, bool]], *, footer: str = "") -> None:
    """A short money breakdown: label, amount, and whether it is the total."""
    grid = Table.grid(padding=(0, 3))
    grid.add_column(style=SLATE, width=22)
    grid.add_column(justify="right")
    for label, amount, total in rows:
        style = f"bold {AMBER}" if total else ""
        grid.add_row(Text(label, style="bold" if total else SLATE), Text(amount, style=style))
    body = Group(grid, "", Text(footer, style=SLATE)) if footer else grid
    console.print(
        Panel(
            body,
            box=ROUNDED,
            border_style=LINE,
            padding=(0, 1),
            title=f"[{SLATE}]{title}[/]",
            title_align="left",
        )
    )
    console.print()


def card(title: str, lines: list[str], *, passed: bool = False) -> None:
    """A single finding in full - used where the sentence matters."""
    tone = PASS if passed else DENY
    grid = Table.grid(padding=(0, 1))
    grid.add_column(overflow="fold")
    grid.add_row(Text(title, style=f"bold {tone}"))
    for line in lines:
        grid.add_row(Text(line, style=SLATE))
    console.print(Panel(grid, box=ROUNDED, border_style=LINE, padding=(0, 1)))
    console.print()


def denied(title: str, rule: str, reason: str, detail: str = "") -> None:
    lines = [f"rule: {rule}", reason] if rule else [reason]
    if detail:
        lines.append(detail)
    card(f"DENIED   {title}", lines)


def cleared(title: str, detail: str = "", extra: str = "") -> None:
    card(f"CLEARED  {title}", [x for x in (detail, extra) if x], passed=True)


def note(text: str) -> None:
    console.print(f"[{SLATE}]  {text}[/]")


def warn(text: str) -> None:
    """Loud line for a run that produced nothing at all - silence is not proof."""
    console.print(f"[bold {AMBER}]  ! {text}[/]")


def tally(
    cleared_n: int,
    denied_n: int,
    reasons: dict[str, int],
    *,
    wrote: str = "",
    unit: str = "candidates",
    kept: str = "cleared",
    dropped: str = "denied",
) -> None:
    """Closing panel: how many went through, how many did not, and why.

    The labels are arguments because a filter over names ("42 waves out of
    4,883 names") is not judging orders, and saying "denied" there would be
    a small lie in the one place the desk reports on itself.
    """
    total = cleared_n + denied_n
    line = Text.assemble(
        (f"{total}", "bold white"), (f"  {unit}    ", SLATE),
        (f"{cleared_n}", f"bold {PASS}"), (f"  {kept}    ", SLATE),
        (f"{denied_n}", f"bold {DENY}"), (f"  {dropped}    ", SLATE),
        (f"{denied_n / total:.0%}" if total else "-", f"bold {AMBER}"),
        ("  refusal rate", SLATE),
    )

    bars = Table.grid(padding=(0, 1))
    bars.add_column(justify="right", style=f"bold {DENY}", width=4)
    bars.add_column(width=24)
    bars.add_column(style=SLATE, overflow="fold")
    top = max(reasons.values()) if reasons else 1
    for rule, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        bars.add_row(str(count), f"[{DENY}]{'█' * max(1, round(count / top * 24))}[/]", rule)

    body = Group(line, "", bars) if reasons else Group(line)
    console.print(
        Panel(
            body,
            box=ROUNDED,
            border_style=LINE,
            padding=(0, 1),
            title=f"[{SLATE}]session[/]",
            title_align="left",
            subtitle=f"[{LINE}]{wrote}[/]" if wrote else None,
            subtitle_align="right",
        )
    )


def money(amount: float | None) -> str:
    return "n/a" if amount is None else f"${amount:,.0f}"


def short(mint: str, width: int = 12) -> str:
    """Contract address cut to fit a column - never silently, always with the mark."""
    return mint if len(mint) <= width else mint[:width] + "…"
