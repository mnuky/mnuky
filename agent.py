"""CSV Analysis Agent — reads CSVs from ./data, generates MD reports, posts to Notion."""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

import anthropic
import pandas as pd
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
notion = Client(auth=NOTION_API_KEY)


def _clean_value(val: str) -> float | str:
    """Convert '122.2 k' → 122200, '43%' → 43.0, else leave as string."""
    if not isinstance(val, str):
        return val
    val = val.strip()
    if val.endswith("%"):
        try:
            return float(val[:-1])
        except ValueError:
            return val
    if val.endswith(" k"):
        try:
            return float(val[:-2]) * 1000
        except ValueError:
            return val
    return val


def load_csv(path: Path) -> tuple[pd.DataFrame, str]:
    df = pd.read_csv(path)
    # Clean analytics-style formatting before analysis
    for col in df.columns:
        if df[col].dtype == object:
            cleaned = df[col].apply(_clean_value)
            if cleaned.dtype != object:
                df[col] = cleaned
    summary_lines = [
        f"File: {path.name}",
        f"Rows: {len(df)}, Columns: {len(df.columns)}",
        f"Columns: {', '.join(df.columns.tolist())}",
        "",
        "All data:",
        df.to_string(index=False),
        "",
        "Descriptive statistics:",
        df.describe(include="all").to_string(),
    ]
    return df, "\n".join(summary_lines)


def interpret(file_name: str, data_summary: str) -> str:
    """Ask Claude to interpret the data and produce a markdown report."""
    prompt = f"""You are a senior product analytics expert at a SaaS company. Below is a CSV export from a product analytics tool.

{data_summary}

Write a thorough Markdown report that includes:
1. `## Summary` — 2-3 sentences describing what this dataset measures and the overall story.
2. `## Key Findings` — bullet points covering the most important trends, peaks, drops, and anomalies. Include specific numbers.
3. `## Trend Analysis` — describe the direction (growth, decline, plateau) and any notable inflection points month-by-month.
4. `## Data Quality` — flag incomplete months, missing values, or values that look suspicious (e.g. May 2026 = 0.9k).
5. `## Recommendations` — 3-5 actionable next steps based on the data (investigate drops, run campaigns, etc.).

Keep the tone professional and concise. Do NOT reproduce raw data tables.
File name: {file_name}"""

    message = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def save_markdown(file_stem: str, report: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"{file_stem}_{timestamp}.md"
    header = f"# Report: {file_stem}\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
    out_path.write_text(header + report, encoding="utf-8")
    print(f"  Saved: {out_path}")
    return out_path


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    """Convert markdown text into Notion block objects (h2, bullets, paragraphs)."""
    blocks = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                },
            })
        elif line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                },
            })
        elif line.startswith("- ") or line.startswith("* "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                },
            })
        elif line.strip() == "":
            pass  # skip blank lines
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                },
            })
    return blocks


def send_to_notion(file_stem: str, report_md: str, md_path: Path) -> str:
    """Create a new page in the Notion database and return its URL."""
    title = f"{file_stem} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    blocks = markdown_to_notion_blocks(report_md)

    # Notion API allows max 100 blocks per request; chunk if needed
    chunk_size = 100
    first_chunk, rest = blocks[:chunk_size], blocks[chunk_size:]

    page = notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties={
            "Name": {"title": [{"text": {"content": title}}]},
        },
        children=first_chunk,
    )
    page_id = page["id"]

    for i in range(0, len(rest), chunk_size):
        notion.blocks.children.append(
            block_id=page_id,
            children=rest[i : i + chunk_size],
        )

    url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")
    print(f"  Notion page: {url}")
    return url


def process_csv(path: Path) -> None:
    print(f"\nProcessing: {path.name}")
    df, data_summary = load_csv(path)
    print(f"  Loaded {len(df)} rows x {len(df.columns)} columns")

    print("  Interpreting with Claude...")
    report_md = interpret(path.name, data_summary)

    md_path = save_markdown(path.stem, report_md)

    print("  Sending to Notion...")
    url = send_to_notion(path.stem, report_md, md_path)
    print(f"  Done. Report URL: {url}")


def main() -> None:
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in ./{DATA_DIR}/  — add some CSVs and re-run.")
        sys.exit(0)

    print(f"Found {len(csv_files)} CSV file(s): {[f.name for f in csv_files]}")
    for csv_path in csv_files:
        try:
            process_csv(csv_path)
        except Exception as exc:
            print(f"  ERROR processing {csv_path.name}: {exc}")

    print("\nAll done.")


if __name__ == "__main__":
    main()
