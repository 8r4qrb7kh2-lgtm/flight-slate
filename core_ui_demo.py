#!/usr/bin/env python3
"""Standalone launcher for the progressive 128x64 feature lab."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import webbrowser
from pathlib import Path

from ui_lab.app import FeatureLabApp, run_feature_lab


def export_all_pages(output_dir: Path) -> dict[str, list[dict[str, object]]]:
    app = FeatureLabApp()
    report = app.export_all_pages(output_dir)
    report_path = output_dir / "final_report.json"
    markdown_path = output_dir / "final_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Core UI Lab Report", ""]
    for key, entries in report.items():
        status = "PASS" if all(not entry["analysis"]["unexpected_colors"] for entry in entries) else "CHECK"
        lines.append(f"- `{key}`: {status}, frames={len(entries)}")
    lines.append("")
    lines.append("Interactive matrix review: use Left/Right arrow keys in `core_ui_demo.py` to move between pages.")
    lines.append("Browser preview: run `core_ui_demo.py --browser-preview` and use Left/Right for pages, Up/Down for frames.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Exported {len(report)} pages")
    print(f"report: {report_path}")
    print(f"markdown: {markdown_path}")
    return report


def run_browser_preview(output_dir: Path, port: int, open_browser: bool) -> None:
    export_all_pages(output_dir)
    root = Path.cwd().resolve()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        url = f"http://127.0.0.1:{port}/web_preview/index.html"
        print(f"browser preview: {url}")
        print("controls: Left/Right page, Up/Down frame, B bounds overlay, C center overlay")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true", help="Render the current feature page to local image files and exit")
    parser.add_argument("--export-all", action="store_true", help="Render every feature page to local image files and exit")
    parser.add_argument("--output-dir", default="artifacts/feature_pages", help="Directory for exported images and reports")
    parser.add_argument("--auto-close-ms", type=int, default=None, help="Automatically close the interactive window after N milliseconds")
    parser.add_argument("--browser-preview", action="store_true", help="Export all pages and serve the browser LED preview")
    parser.add_argument("--browser-port", type=int, default=8765, help="Port for --browser-preview")
    parser.add_argument("--no-open-browser", action="store_true", help="Do not auto-open the browser for --browser-preview")
    args = parser.parse_args()

    try:
        output_dir = Path(args.output_dir)
        if args.browser_preview:
            run_browser_preview(output_dir, args.browser_port, not args.no_open_browser)
        elif args.export_all:
            export_all_pages(output_dir)
        elif args.export:
            app = FeatureLabApp()
            paths, analysis = app.export_current_page(output_dir)
            print(f"Exported feature page: {app.current_page.key}")
            for key, value in paths.items():
                print(f"{key}: {value}")
            print(f"analysis: {analysis}")
        else:
            run_feature_lab(auto_close_ms=args.auto_close_ms)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
