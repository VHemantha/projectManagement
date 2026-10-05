"""Measure real tokens and cost on a job folder, without the PM application.

    python -m precheck_agent.measure --folder <Drive folder id or local folder name> \
        --client <client id> --items items.txt [--runs 2]

`items.txt` holds the Direction Note items, one per line. The same job is run `--runs` times:
the first run pays for everything, the later ones show what an unchanged re-run costs (it
should be zero model calls). Prints a Markdown table for the README, and how many items the
checks flagged (no source, no file named, or a figure not in the documents).
"""
import argparse
import sys
import time

from . import pm_client, runner
from .config import get_settings


class StubPM:
    def __init__(self, job: dict):
        self.job, self.events = job, []

    def get_job(self, job_id):
        return self.job

    def send_event(self, run_id, event):
        self.events.append(event)
        if event["type"] == "ai_precheck.progress" and event.get("state") == "done":
            print(f"  {event['stage']:<9} {event['label']}", file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--items", required=True, help="text file: one Direction Note item per line")
    parser.add_argument("--job", default="measure-1")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args(argv)

    with open(args.items, encoding="utf-8") as fh:
        items = [{"id": f"D{n}", "text": line.strip()} for n, line in enumerate((l for l in fh if l.strip()), start=1)]
    s = get_settings()
    pm = StubPM({"job_id": args.job, "key": args.job, "title": args.job, "client_id": args.client, "client_name": args.client,
                 "drive_folder_id": args.folder, "direction_items": items, "knowledge_ids": []})
    pm_client.set_pm(pm)

    print(f"llm_mode={s.llm_mode} drive_mode={s.drive_mode} precheck={s.precheck_model}", file=sys.stderr)
    rows, ok = [], True
    for n in range(1, args.runs + 1):
        print(f"run {n}:", file=sys.stderr)
        started = time.time()
        r = runner.execute(runner.new_run_id(), args.job)
        if r["status"] == "failed":
            print(f"FAILED: {r['reason']}", file=sys.stderr)
            return 1
        u, t = r["usage"], r["usage"]["totals"]
        p = r["precheck"]
        rows.append(
            f"| {n} | {r['trail']['read']['documents']} | {p['decision']['label']} | {len(p['requests'])} / {len(p['provided'])} / {len(p['not_needed'])} | "
            f"{u['model_calls']} | {t['input']:,} | {t['cache_read']:,} | {t['output']:,} | ${u['cost_usd']:.4f} | {time.time() - started:.0f} s |"
        )
        if n == 1:
            flagged = [i for i in p["requests"] + p["provided"] if i.get("flags")]
            print(f"  {len(flagged)} items flagged (no source, no file named, or a figure not in the documents)", file=sys.stderr)
            for sk in r["skipped"]:
                print(f"  skipped: {sk['what']} ({sk['reason']})", file=sys.stderr)
    print("| Run | Documents | Decision | Requests / provided / not needed | Model calls | Input (uncached) | Cache read | Output | Cost | Time |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
