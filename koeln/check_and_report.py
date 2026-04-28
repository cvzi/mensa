#!/usr/bin/env python3
"""Fetch dishes from API and run parser for all canteens to verify
that each dish occurrence is used exactly once. Prints a summary and writes
a JSON report. If issues are found, creates or comments on a GitHub issue with details.

Run with:
  python koeln/check_and_report.py [--out PATH] [--verbose] [--no-issue]

"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from typing import Dict, List, Tuple

import requests

# Try importing koeln helpers
try:
    from koeln import Parser, _get_week_menu_data, monday_for, now_local, weekSpanDays, _dish_matches_canteen
except Exception:
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if here not in sys.path:
        sys.path.insert(0, here)
    from koeln import Parser, _get_week_menu_data, monday_for, now_local, weekSpanDays, _dish_matches_canteen  # type: ignore


ISSUE_TITLE = "Köln parser: unused or duplicated dishes found"
GITHUB_API_BASE = "https://api.github.com"


def build_occurrence_index(menuData) -> Dict[str, Tuple[str, int, dict]]:
    index = {}
    for day in menuData:
        dayDate = str(day.get("date") or "").strip()
        for idx, dish in enumerate(day.get("dishes", [])):
            occ_id = f"{dayDate}::{idx}::{dish.get('id') or ''}"
            index[occ_id] = (dayDate, idx, dish)
    return index


def build_usage(menuData, parser: Parser) -> Dict[str, List[str]]:
    occurrences = []
    for day in menuData:
        dayDate = str(day.get("date") or "").strip()
        for idx, dish in enumerate(day.get("dishes", [])):
            occ_id = f"{dayDate}::{idx}::{dish.get('id') or ''}"
            occurrences.append((occ_id, dayDate, dish))

    usage: Dict[str, List[str]] = {}
    for occ_id, dayDate, dish in occurrences:
        usage.setdefault(occ_id, [])
        for canteen_key, canteen in parser.canteens.items():
            try:
                if _dish_matches_canteen(dish, canteen):
                    usage[occ_id].append(canteen_key)
            except Exception:
                logging.exception("Error matching occurrence %s", occ_id)
    return usage


def write_report(path: str, summary: dict, usage: dict) -> None:
    with open(path, "w", encoding="utf8") as f:
        json.dump({"summary": summary, "usage": usage}, f, ensure_ascii=False, indent=2)
    logging.info("Wrote report to %s", path)


def github_find_issue(repo: str, token: str, title: str) -> dict | None:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    params = {"state": "open", "per_page": 100}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logging.exception("Failed to list GitHub issues: %s", exc)
        return None

    for issue in resp.json() or []:
        if issue.get("title") == title:
            return issue
    return None


def github_create_issue(repo: str, token: str, title: str, body: str) -> dict | None:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    payload = {"title": title, "body": body}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logging.exception("Failed to create GitHub issue")
        return None


def github_post_comment(repo: str, token: str, issue_number: int, body: str) -> dict | None:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{issue_number}/comments"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    payload = {"body": body}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logging.exception("Failed to post GitHub comment")
        return None


def make_markdown_body(start: dt.date, end: dt.date, summary: dict, occ_index: Dict[str, Tuple[str, int, dict]], sample_limit: int, full_report: dict | None = None) -> str:
    lines: List[str] = []
    lines.append(f"Automated Köln menu verification for {start.isoformat()} to {end.isoformat()}.")
    lines.append("")
    lines.append("Summary:")
    lines.append("")
    lines.append(f"- Checked dishes: {summary.get('checked_dishes', 0)}")
    lines.append(f"- Unused dishes: {summary.get('unused_count', 0)}")
    lines.append(f"- Doubly used dishes: {summary.get('duplicates_count', 0)}")
    lines.append("")
    dup = summary.get("duplicates", {}) or {}
    unused = summary.get("unused", []) or []

    if dup:
        lines.append(f"Example duplicates (first {sample_limit}):")
        lines.append("")
        count = 0
        for occ_id, canteens in dup.items():
            if count >= sample_limit:
                break
            entry = occ_index.get(occ_id)
            name = ""
            if entry:
                dish = entry[2]
                name = dish.get("name_de") or dish.get("name") or ""
            lines.append(f"- **{occ_id}** -> {canteens}  {('  ' + name) if name else ''}")
            count += 1
        lines.append("")

    if unused:
        lines.append(f"Example unused occurrences (first {sample_limit}):")
        lines.append("")
        count = 0
        for occ_id in unused:
            if count >= sample_limit:
                break
            entry = occ_index.get(occ_id)
            name = ""
            if entry:
                dish = entry[2]
                name = dish.get("name_de") or dish.get("name") or ""
            lines.append(f"- **{occ_id}**  {('  ' + name) if name else ''}")
            count += 1
        lines.append("")

    # Optionally embed the full JSON report inside a collapsible spoiler
    if full_report is not None:
        try:
            report_text = json.dumps(full_report, ensure_ascii=False, indent=2)
            lines.append("")
            lines.append("<details>")
            lines.append("<summary>Full JSON report</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(report_text)
            lines.append("```")
            lines.append("</details>")
        except Exception:
            # If serialization fails, skip embedding the report but continue
            logging.exception("Failed to embed full report in issue body")
    return "\n".join(lines)


def run(argv=None) -> int:
    p = argparse.ArgumentParser(description="Koeln live menu verifier and GitHub reporter")
    p.add_argument("--out", help="Path to write JSON report", default=None)
    p.add_argument("--verbose", help="Enable debug logging", action="store_true")
    p.add_argument("--no-issue", help="Do not create or comment on GitHub issue", action="store_true")
    p.add_argument("--sample-limit", help="Limit examples included in issue body", type=int, default=5)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    parser = Parser("http://localhost/")

    today = now_local().date()
    start = monday_for(today)
    end = start + dt.timedelta(days=weekSpanDays - 1)

    logging.info("Fetching menu for %s to %s", start.isoformat(), end.isoformat())
    try:
        menuData = _get_week_menu_data(start, end)
    except Exception:
        logging.exception("Failed to fetch week menu data")
        return 0

    logging.info("Running verifier across %d days", len(menuData))

    occ_index = build_occurrence_index(menuData)
    usage = build_usage(menuData, parser)

    total_dishes = len(usage)
    unused = [did for did, used in usage.items() if not used]
    duplicates = {did: used for did, used in usage.items() if len(used) > 1}

    summary = {
        "checked_dishes": total_dishes,
        "unused_count": len(unused),
        "duplicates_count": len(duplicates),
        "unused": unused,
        "duplicates": duplicates,
    }

    print("Koeln live verification summary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.out:
        out_path = args.out
    else:
        out_path = os.path.join(os.getcwd(), f"koeln_verify_report_{dt.date.today().isoformat()}.json")

    try:
        write_report(out_path, summary, usage)
    except Exception:
        logging.exception("Failed to write report to %s", out_path)

    issues_present = bool(summary["unused_count"] or summary["duplicates_count"])
    if not issues_present:
        print("All dishes used exactly once")
        return 0

    print("Issues found: unused or duplicated dishes present")

    if args.no_issue:
        print("Issue creation disabled by --no-issue")
        return 0

    gh_token = os.environ.get("GITHUB_TOKEN")
    gh_repo = os.environ.get("GITHUB_REPOSITORY")
    if not gh_token or not gh_repo:
        print("GITHUB_TOKEN or GITHUB_REPOSITORY not set; skipping GitHub issue creation")
        return 0

    # Provide full report for embedding into the issue body
    full_report = {"summary": summary, "usage": usage}
    body = make_markdown_body(start, end, summary, occ_index, args.sample_limit, full_report=full_report)

    existing = github_find_issue(gh_repo, gh_token, ISSUE_TITLE)
    if existing:
        issue_number = existing.get("number")
        if issue_number is None:
            logging.error("Found issue without number, skipping comment")
            print("Found existing issue but could not determine its number; skipping comment")
            return 0
        comment = github_post_comment(gh_repo, gh_token, issue_number, body)
        if comment:
            print(f"Posted comment to existing issue #{issue_number}")
        else:
            print("Failed to post comment to existing issue")
        return 0

    created = github_create_issue(gh_repo, gh_token, ISSUE_TITLE, body)
    if created:
        print(f"Created new issue #{created.get('number')}")
    else:
        print("Failed to create new GitHub issue")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
