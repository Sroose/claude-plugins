import sys, json, time, datetime, os, re, urllib.parse

data = json.load(sys.stdin)

model = data.get("model", {}).get("display_name", "?")
# "Opus 5.5 (1M context)" → "Opus 5.5 (1M)"
model = re.sub(r"\s+context\)", ")", model)
cwd = data.get("workspace", {}).get("current_dir", "")
pct = int(data.get("context_window", {}).get("used_percentage") or 0)
five_h = data.get("rate_limits", {}).get("five_hour", {})
seven_d = data.get("rate_limits", {}).get("seven_day", {})
cache = data.get("prompt_cache") or {}

RESET = "\033[0m"
GREY = "\033[90m"
LABEL = "\033[1;90m"  # bold grey
YELLOW = "\033[33m"
RED = "\033[31m"
GREEN = "\033[32m"
BLUE = "\033[34m"


def paint(code, s):
    return code + s + RESET if code else s


def grey(s):
    return paint(GREY, s)


def label(s):
    return paint(LABEL, s)


def pct_color(value):
    return RED if value >= 80 else YELLOW if value >= 60 else ""


def color_pct(value):
    return paint(pct_color(value), str(value) + "%")


def short_home(path):
    # The container's $HOME isn't the host's, so also fold a /Users/<x> or
    # /home/<x> prefix (e.g. in $HOST_CWD) into "~".
    home = os.path.expanduser("~")
    if home and (path == home or path.startswith(home + "/")):
        return "~" + path[len(home):]
    return re.sub(r"^/(Users|home)/[^/]+(?=/|$)", "~", path)


parts = [model]

# 5-hour rate limit, with the clock time it resets
if five_h:
    fh = round(five_h.get("used_percentage", 0))
    s = label("5H ") + color_pct(fh)
    resets_at = five_h.get("resets_at")
    if resets_at and resets_at > time.time():
        s += grey(" (" + datetime.datetime.fromtimestamp(resets_at).strftime("%H:%M") + ")")
    parts.append(s)

# 7-day rate limit, with the day it resets
if seven_d:
    wd = round(seven_d.get("used_percentage", 0))
    s = label("WEEK ") + color_pct(wd)
    resets_at = seven_d.get("resets_at")
    if resets_at:
        day = datetime.datetime.fromtimestamp(resets_at).strftime("%A").lower()
        s += grey(" (" + day + ")")
    parts.append(s)

parts.append(label("CTX ") + color_pct(pct))

# Prompt cache countdown (CC ≥ 2.1.251 passes prompt_cache). Omitted when CC
# doesn't send it or nothing has been cached yet. Warns in the last 20% of the
# TTL, red in the last 5% (1h: 12m / 3m; 5m: 60s / 15s).
if cache and cache.get("caching_observed", True):
    ttl = {"5m": 300, "1h": 3600}.get(cache.get("ttl"), 3600)
    left = int((cache.get("expires_at") or 0) - time.time())
    if not cache.get("warm") or left <= 0:
        s = paint(RED, "░░░░░ cold")
    else:
        frac = left / ttl
        col = RED if frac <= 0.05 else YELLOW if frac <= 0.20 else ""
        full = max(1, min(5, round(frac * 5)))
        bar = "█" * full + "░" * (5 - full)
        txt = str(left // 60) + "m" if left >= 60 else str(left) + "s"
        s = paint(col or GREEN, bar) + " " + paint(col, txt)
    parts.append(label("cache ") + s)

# Current working directory (rightmost).
# HOST_CWD, when set (e.g. a containerized session), is the host-side path that
# the current dir is bind-mounted from; show it in parens for orientation.
# The path is an OSC 8 hyperlink to file://<host path>, so cmd-click opens it in
# Finder (terminal permitting). In a container the in-container path doesn't
# exist on the host, so the link targets $HOST_CWD instead.
def link(target, text):
    url = "file://" + urllib.parse.quote(target)
    return "\033]8;;" + url + "\033\\" + text + "\033]8;;\033\\"


if cwd:
    host_cwd = os.environ.get("HOST_CWD")
    s = paint(BLUE, link(host_cwd or cwd, short_home(cwd)))
    if host_cwd:
        s += grey(" (" + short_home(host_cwd) + ")")
    parts.append(s)

print(grey(" │ ").join(parts))
