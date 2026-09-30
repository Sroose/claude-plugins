#!/usr/bin/env python3
"""Read-only access to Wispr Flow meeting notes stored on this Mac."""
import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path.home() / "Library/Application Support/Wispr Flow"
DB = ROOT / "flow.sqlite"
MEETINGS_DIR = ROOT / "meetings"
SPEAKER_TOKEN = re.compile(r"<@speaker:(\d+)>")
ASSIGNMENT_PRIORITY = ("user", "consensus", "mic", "llm", "dom")


def connect():
    if not DB.exists():
        sys.exit(f"Wispr Flow database not found at {DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = row_dict
    return con


def row_dict(cursor, row):
    """Rows as dicts with NULL read as "", so text fields never need a None check."""
    return {col[0]: "" if value is None else value for col, value in zip(cursor.description, row)}


TIMESTAMP = re.compile(r"(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(?:\.(\d+))?\s*(Z|[+-]\d\d:?\d\d)?")


def parse_ts(value):
    """SQLite timestamp as an aware datetime. No offset means UTC; any fraction length is accepted.

    Parsed by hand rather than with fromisoformat, which only got this lenient in Python 3.11.
    """
    match = TIMESTAMP.match(value or "")
    if not match:
        sys.exit(f"Unrecognised timestamp '{value}' in the Wispr Flow database (storage format changed?)")
    day, clock, fraction, offset = match.groups()
    ts = datetime.strptime(f"{day} {clock}.{(fraction or '0')[:6].ljust(6, '0')}", "%Y-%m-%d %H:%M:%S.%f")
    if offset and offset != "Z":
        sign = 1 if offset[0] == "+" else -1
        hours, minutes = int(offset[1:3]), int(offset[-2:])
        return ts.replace(tzinfo=timezone(sign * timedelta(hours=hours, minutes=minutes)))
    return ts.replace(tzinfo=timezone.utc)


def fmt_local(value):
    return parse_ts(value).astimezone().strftime("%Y-%m-%d %H:%M")


def fmt_duration(ms):
    if not ms:
        return "?"
    minutes = round(ms / 60000)
    return f"{minutes // 60}h{minutes % 60:02d}" if minutes >= 60 else f"{minutes}m"


def parse_since(value):
    match = re.fullmatch(r"(\d+)([dhw])", value)
    if match:
        n, unit = int(match[1]), match[2]
        delta = {"d": timedelta(days=n), "h": timedelta(hours=n), "w": timedelta(weeks=n)}[unit]
        return datetime.now(timezone.utc) - delta
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def speaker_names(meeting):
    """Map speaker id (as string) to a person's name using the meeting's speakerMap."""
    if not meeting["speakerMap"]:
        return {}
    data = json.loads(meeting["speakerMap"])
    people = data.get("people", {})
    names = {}
    for speaker_id, assignment in data.get("assignments", {}).items():
        for key in ASSIGNMENT_PRIORITY:
            person = people.get(assignment.get(key) or "")
            if person and person.get("name"):
                names[speaker_id] = person["name"]
                break
    return names


def participants(meeting):
    if not meeting["speakerMap"]:
        return []
    people = json.loads(meeting["speakerMap"]).get("people", {})
    return [p["name"] for p in people.values() if p.get("name")]


def resolve_speakers(text, names):
    return SPEAKER_TOKEN.sub(lambda m: names.get(m[1], f"Speaker {m[1]}"), text or "")


def live_meetings(con):
    return con.execute(
        "select * from Meetings where isDeleted = 0 and isTourDemo = 0 order by createdAt desc"
    ).fetchall()


def find_meeting(con, ref):
    """An exact id wins, then an id prefix, then a title fragment. Several matches on a level are ambiguous."""
    rows = live_meetings(con)
    for r in rows:
        if r["id"] == ref:
            return r
    matches = [r for r in rows if r["id"].startswith(ref)]
    if not matches:
        matches = [r for r in rows if ref.lower() in r["title"].lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        sys.exit(f"No meeting matches '{ref}'. Use `wispr-notes list` to see meetings.")
    options = "\n".join(f"  {r['id'][:8]}  {fmt_local(r['createdAt'])}  {r['title']}" for r in matches)
    sys.exit(f"'{ref}' matches several meetings, pass a longer id prefix:\n{options}")


def transcript_segments(meeting):
    """Refined transcript when present, else the live one. Yields (timestamp, speaker id, text)."""
    if meeting["transcriptDeletedAt"]:
        return []
    folder = MEETINGS_DIR / meeting["id"]
    for name in ("refined.ndjson", "live.ndjson"):
        path = folder / name
        if path.exists() and path.stat().st_size > 0:
            segments = []
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    # Skip blank lines and lines that don't parse (e.g. a half-written last line while
                    # recording), so one damaged file can't abort `search` across all meetings.
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row, dict) or not row.get("text"):
                        continue
                    speaker = row.get("speaker") or {}
                    speaker_id = speaker.get("id")
                    segments.append((row.get("timestamp") or "", "?" if speaker_id is None else str(speaker_id), row["text"].strip()))
            return segments
    return []


def print_meeting_header(meeting):
    people = ", ".join(participants(meeting)) or "unknown"
    print(f"# {meeting['title']}")
    print(f"id: {meeting['id']}  |  {fmt_local(meeting['createdAt'])}  |  {fmt_duration(meeting['recordedMs'])}  |  {people}")


def cmd_list(con, args):
    since = parse_since(args.since) if args.since else None
    for m in live_meetings(con):
        if since and parse_ts(m["createdAt"]) < since:
            continue
        people = ", ".join(participants(m))
        print(f"{m['id'][:8]}  {fmt_local(m['createdAt'])}  {fmt_duration(m['recordedMs']):>5}  {m['title']}  [{people}]")


def cmd_show(con, args):
    m = find_meeting(con, args.meeting)
    names = speaker_names(m)
    print_meeting_header(m)
    print("\n## Summary\n")
    print(resolve_speakers(m["summary"], names).strip() or "(no summary)")
    print("\n## My notes\n")
    print(resolve_speakers(m["notes"], names).strip() or "(no notes)")


def cmd_transcript(con, args):
    m = find_meeting(con, args.meeting)
    names = speaker_names(m)
    segments = transcript_segments(m)
    if not segments:
        sys.exit("No transcript available for this meeting (never recorded or deleted).")
    print_meeting_header(m)
    term = args.grep.lower() if args.grep else None
    context = args.context if term else 0
    hits = [i for i, s in enumerate(segments) if not term or term in s[2].lower()]
    wanted = sorted({j for i in hits for j in range(max(0, i - context), min(len(segments), i + context + 1))})
    previous = None
    for i in wanted:
        if previous is not None and i != previous + 1:
            print("...")
        ts, speaker, text = segments[i]
        print(f"[{ts}] {names.get(speaker, 'Speaker ' + speaker)}: {text}")
        previous = i
    if term and not hits:
        print(f"(no segment mentions '{args.grep}')")


def snippet(text, term, width=90):
    idx = text.lower().find(term)
    start = max(0, idx - width)
    end = min(len(text), idx + len(term) + width)
    return ("..." if start else "") + " ".join(text[start:end].split()) + ("..." if end < len(text) else "")


def cmd_search(con, args):
    term = args.term.lower()
    found = False
    for m in live_meetings(con):
        names = speaker_names(m)
        hits = []
        for label, field in (("title", m["title"]), ("summary", m["summary"]), ("notes", m["notes"])):
            text = resolve_speakers(field, names)
            if term in text.lower():
                hits.append(f"  {label}: {snippet(text, term)}")
        transcript_hits = [s for s in transcript_segments(m) if term in s[2].lower()]
        for ts, speaker, text in transcript_hits[: args.max_hits]:
            hits.append(f"  [{ts}] {names.get(speaker, 'Speaker ' + speaker)}: {snippet(text, term)}")
        if len(transcript_hits) > args.max_hits:
            hits.append(f"  (+{len(transcript_hits) - args.max_hits} more transcript hits, use `wispr-notes transcript {m['id'][:8]} --grep`)")
        if hits:
            found = True
            print(f"{m['id'][:8]}  {fmt_local(m['createdAt'])}  {m['title']}")
            print("\n".join(hits))
    for n in con.execute("select * from Notes where isDeleted = 0 order by modifiedAt desc"):
        if term in (n["title"] + " " + n["content"]).lower():
            found = True
            print(f"note {n['id'][:8]}  {fmt_local(n['modifiedAt'])}  {n['title']}")
            print(f"  {snippet(n['content'], term)}")
    if not found:
        print(f"No matches for '{args.term}'.")


def cmd_notes(con, args):
    rows = con.execute("select * from Notes where isDeleted = 0 order by modifiedAt desc").fetchall()
    if args.note:
        rows = [r for r in rows if r["id"].startswith(args.note) or args.note.lower() in r["title"].lower()]
        for r in rows:
            print(f"# {r['title']}\nid: {r['id']}  |  modified {fmt_local(r['modifiedAt'])}\n\n{r['content'].strip()}\n")
        if not rows:
            sys.exit(f"No note matches '{args.note}'.")
        return
    for r in rows:
        print(f"{r['id'][:8]}  {fmt_local(r['modifiedAt'])}  {r['title']}")


def main():
    parser = argparse.ArgumentParser(prog="wispr-notes", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="list meetings, newest first")
    p.add_argument("--since", help="e.g. 7d, 24h, 2w or an ISO date")
    p = sub.add_parser("show", help="summary and notes of one meeting")
    p.add_argument("meeting", help="id prefix or title fragment")
    p = sub.add_parser("transcript", help="transcript of one meeting")
    p.add_argument("meeting", help="id prefix or title fragment")
    p.add_argument("--grep", help="only segments containing this text")
    p.add_argument("--context", type=int, default=2, help="segments around each --grep hit (default 2)")
    p = sub.add_parser("search", help="search titles, summaries, notes and transcripts")
    p.add_argument("term")
    p.add_argument("--max-hits", type=int, default=5, help="transcript hits shown per meeting (default 5)")
    p = sub.add_parser("notes", help="standalone notes: list, or show one")
    p.add_argument("note", nargs="?", help="id prefix or title fragment")
    args = parser.parse_args()
    with connect() as con:
        {"list": cmd_list, "show": cmd_show, "transcript": cmd_transcript, "search": cmd_search, "notes": cmd_notes}[
            args.command
        ](con, args)


if __name__ == "__main__":
    main()
