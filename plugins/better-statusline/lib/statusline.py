import sys, json, subprocess, time, datetime, os

data = json.load(sys.stdin)

model = data.get("model", {}).get("display_name", "?")
cwd = data.get("workspace", {}).get("current_dir", "")
pct = int(data.get("context_window", {}).get("used_percentage") or 0)
five_h = data.get("rate_limits", {}).get("five_hour", {})
seven_d = data.get("rate_limits", {}).get("seven_day", {})

RED = "\033[31m"
RESET = "\033[0m"

def color_pct(value):
    s = str(value) + "%"
    return RED + s + RESET if value >= 75 else s

parts = ["[" + model + "]"]

# 5-hour rate limit
if five_h:
    fh = round(five_h.get("used_percentage", 0))
    fh_str = "5h usage: " + color_pct(fh)
    resets_at = five_h.get("resets_at")
    if resets_at:
        diff = int(resets_at - time.time())
        if diff > 0:
            hours = diff // 3600
            mins = (diff % 3600) // 60
            if hours > 0:
                fh_str += "  (reset in " + str(hours) + " hr " + str(mins) + " min)"
            else:
                fh_str += "  (reset in " + str(mins) + " min)"
    parts.append(fh_str)

# 7-day rate limit
if seven_d:
    wd = round(seven_d.get("used_percentage", 0))
    wd_str = "week usage: " + color_pct(wd)
    resets_at = seven_d.get("resets_at")
    if resets_at:
        reset_dt = datetime.datetime.fromtimestamp(resets_at)
        day_name = reset_dt.strftime("%A").lower()
        wd_str += "  (reset " + day_name + ")"
    parts.append(wd_str)

# Context (last)
parts.append("context " + color_pct(pct))

# Current working directory (rightmost).
# HOST_CWD, when set (e.g. a containerized session), is the host-side path that
# the current dir is bind-mounted from; show it in parens for orientation.
if cwd:
    host_cwd = os.environ.get("HOST_CWD")
    cwd_str = "cwd: " + cwd
    if host_cwd:
        cwd_str += " (" + host_cwd + ")"
    parts.append(cwd_str)

sep = "     |     "
print(parts[0] + sep + sep.join(parts[1:]))
