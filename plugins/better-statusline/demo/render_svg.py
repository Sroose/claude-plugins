"""Render statusline.svg for the README from the real lib/statusline.py.

    python3 plugins/better-statusline/demo/render_svg.py

Feeds the script a made-up input (5H warning, cache running low), turns its ANSI
output into colored SVG text and writes ../statusline.svg. GitHub doesn't
render ANSI in Markdown, but it does render an SVG image.
"""
import datetime, html, json, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "lib" / "statusline.py"
OUT = HERE.parent / "statusline.svg"

HOME = "/home/user"  # fake home, so the path renders as ~/code/projectx
now = time.time()
clock = datetime.datetime.now().replace(hour=22, minute=59, second=0, microsecond=0)
if clock.timestamp() <= now:
    clock += datetime.timedelta(days=1)
sunday = datetime.datetime.now() + datetime.timedelta(days=(6 - datetime.datetime.now().weekday()) % 7 or 7)


def payload(five, week, ctx, cache_left):
    cache = ({"warm": False, "ttl": "1h", "expires_at": None} if cache_left is None
             else {"warm": True, "ttl": "1h", "expires_at": now + cache_left + 30})
    return {
        "model": {"display_name": "Opus 5.5 (1M context)"},
        "workspace": {"current_dir": HOME + "/code/projectx"},
        "context_window": {"used_percentage": ctx},
        "rate_limits": {"five_hour": {"used_percentage": five, "resets_at": clock.timestamp()},
                        "seven_day": {"used_percentage": week, "resets_at": sunday.timestamp()}},
        "prompt_cache": cache,
    }


# One line: 5H warning, WEEK and CTX calm, cache running low (yellow).
STATES = [payload(64, 13, 12, 6 * 60)]

# Dark-terminal palette for the SGR codes statusline.py uses.
FG = "#d4d4d4"
COLORS = {"31": "#f14c4c", "32": "#23d18b", "33": "#e5c07b", "34": "#5c9cf5", "90": "#8a8a8a"}
SGR = re.compile(r"\033\[([0-9;]*)m")
OSC8 = re.compile(r"\033\]8;;[^\033]*\033\\")


def spans(line):
    """ANSI line → list of (text, color, bold)."""
    line = OSC8.sub("", line)
    out, color, bold, pos = [], FG, False, 0
    for m in SGR.finditer(line):
        if m.start() > pos:
            out.append((line[pos:m.start()], color, bold))
        for code in (m.group(1) or "0").split(";"):
            if code == "0":
                color, bold = FG, False
            elif code == "1":
                bold = True
            elif code in COLORS:
                color = COLORS[code]
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], color, bold))
    return out


env = dict(os.environ, HOME=HOME)
env.pop("HOST_CWD", None)
lines = [subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(p), env=env,
                        capture_output=True, text=True, check=True).stdout.rstrip("\n")
         for p in STATES]

CH, LH, PAD, FS = 8.6, 22, 14, 14  # char width, line height, padding, font size (px)
cols = max(sum(len(t) for t, _, _ in spans(l)) for l in lines)
w, h = int(cols * CH + 2 * PAD), int(len(lines) * LH + 2 * PAD - 6)
rows = []
for i, l in enumerate(lines):
    y = PAD + FS + i * LH
    ts = "".join(
        f'<tspan fill="{c}"{" font-weight=\"bold\"" if b else ""}>{html.escape(t)}</tspan>'
        for t, c, b in spans(l))
    # textLength pins the line width whatever monospace font the viewer has
    # (they differ by ~10%); lengthAdjust="spacing" only touches letter spacing.
    n = sum(len(t) for t, _, _ in spans(l))
    rows.append(f'  <text x="{PAD}" y="{y}" textLength="{n * CH:.0f}" lengthAdjust="spacing"'
                f' xml:space="preserve">{ts}</text>')

OUT.write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
    f'  <rect width="100%" height="100%" rx="6" fill="#1e1e1e"/>\n'
    f'  <g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" font-size="{FS}">\n'
    + "\n".join(rows) + "\n  </g>\n</svg>\n")
print("wrote", OUT)
