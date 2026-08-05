"""Small console display helpers for long-running TCF pipeline messages.

The project currently prints a lot of useful debugging details directly to the
terminal.  These helpers keep those details available while making the main
stage handoff messages easier to scan by humans.
"""

import os
import shlex
import textwrap


_WIDTH = 88


def _supports_color():
    """Return True when ANSI colors are likely to render correctly."""
    if os.environ.get("NO_COLOR"):
        return False
    return os.environ.get("TERM", "").lower() not in ("", "dumb")


_USE_COLOR = _supports_color()


_COLORS = {
    "blue": "\033[94m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


_STAGE_ICONS = {
    "DataConverter": "🧱",
    "RunClassfier": "🤖",
    "CombineTestResult": "🧩",
    "Test_result_Vis": "📊",
    "BackupAndClean": "🧹",
}


def colorize(text, color):
    if not _USE_COLOR:
        return text
    return f"{_COLORS.get(color, '')}{text}{_COLORS['reset']}"


def rule(title=None, char="─", width=_WIDTH):
    if not title:
        return char * width
    label = f" {title} "
    side = max(width - len(label), 0)
    left = side // 2
    right = side - left
    return f"{char * left}{label}{char * right}"


def stage_banner(stage_name, status="START", detail=None):
    icon = _STAGE_ICONS.get(stage_name, "▶")
    heading = f"{icon} {stage_name} · {status}"
    lines = ["", colorize(rule(heading, "═"), "blue")]
    if detail:
        lines.append(colorize(detail, "dim"))
    print("\n".join(lines))


def stage_done(stage_name, elapsed=None):
    detail = f"完成，耗時 {elapsed:.2f} 秒" if elapsed is not None else "完成"
    print(colorize(f"✅ {stage_name} · {detail}", "green"))
    print(colorize(rule(char="═"), "blue"))


def stage_failed(stage_name, returncode, cmd):
    print(colorize(f"❌ {stage_name} · 失敗，exit code {returncode}", "red"))
    print_command(cmd, label="Failed command")


def print_args_summary(args):
    """Print a compact argparse Namespace summary with noisy empty values removed."""
    values = vars(args) if hasattr(args, "__dict__") else {}
    important = [
        "task", "train", "test", "TRVPort", "TRVWebHost", "ModelType",
        "ExecutionTime", "WorkPoolROOT", "BertDatasetSubDir", "modelDir",
        "TopicTreeDir", "TopicTreeFiles", "nProcess", "nProcessSPC",
    ]
    shown = []
    for key in important:
        value = values.get(key)
        if value not in (None, ""):
            shown.append(f"{key}={value}")
    if not shown:
        return
    print(colorize("設定摘要", "bold"))
    for chunk in textwrap.wrap(" | ".join(shown), width=_WIDTH):
        print(f"  {chunk}")


def print_command(cmd, label="Command"):
    """Pretty-print a shell command without hiding the exact executable text."""
    print(colorize(label, "bold"))
    try:
        parts = shlex.split(cmd)
        formatted = " \\\n  ".join(shlex.quote(part) for part in parts)
    except ValueError:
        formatted = cmd
    print(textwrap.indent(formatted, "  "))


def info(message, icon="ℹ️"):
    for idx, line in enumerate(textwrap.wrap(str(message), width=_WIDTH) or [""]):
        prefix = f"{icon} " if idx == 0 else "  "
        print(prefix + line)


def warning(message):
    info(message, icon="⚠️")


def section(title, detail=None, icon="▶"):
    heading = f"{icon} {title}"
    lines = [colorize(rule(heading), "blue")]
    if detail:
        lines.append(colorize(str(detail), "dim"))
    print("\n".join(lines))


def key_values(title, items, icon="•"):
    shown = [(key, value) for key, value in items if value not in (None, "")]
    if not shown:
        return
    print(colorize(title, "bold"))
    key_width = min(max(len(str(key)) for key, _ in shown), 24)
    for key, value in shown:
        wrapped = textwrap.wrap(str(value), width=max(_WIDTH - key_width - 8, 20)) or [""]
        print(f"  {icon} {str(key):<{key_width}} : {wrapped[0]}")
        for line in wrapped[1:]:
            print(f"    {'':<{key_width}}   {line}")


def summarize_sequence(values, limit=5):
    values = list(values or [])
    if len(values) <= limit:
        return str(values)
    head = values[:limit]
    return f"{head} ... (+{len(values) - limit} more)"


def dataframe_summary(df, label="DataFrame", max_rows=6):
    shape = getattr(df, "shape", None)
    columns = list(getattr(df, "columns", []))
    key_values(label, [
        ("shape", shape),
        ("columns", summarize_sequence(columns, limit=8)),
    ], icon="·")
    if hasattr(df, "head"):
        preview = df.head(max_rows)
        print(textwrap.indent(str(preview), "  "))
