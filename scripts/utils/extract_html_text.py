"""
Extract text from HTML files under data/html and write alongside each file.

Outputs:
- <name>.txt: plain text extracted from HTML.
- <name>_clean.txt: noise-reduced version (drops "Copied!",行番号など).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
HTML_DIR = ROOT / "data" / "html"
OUT_DIR = ROOT / "data" / "text"


def extract_plain_text(html_text: str) -> str:
    """Extract text using BeautifulSoup, skipping script/style."""
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # get_text with separator to keep line breaks between blocks
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def clean_noise(text: str) -> str:
    """Drop common noise like 'Copied!'や連番だけの行。"""

    def tidy_tag_spacing(line: str) -> str:
        """Add missing spaces between tag name/attributes for readability."""
        if "<" in line and ">" in line:
            attr_prefix = r"(?:@|class|id|type|name|style|href|src|ref|slot|data-|v-|:)"
            # Insert a space between tag name and the first attribute/@ディレクティブ
            line = re.sub(rf"<([A-Za-z0-9]+)(?={attr_prefix})", r"<\1 ", line)
            # Insert a space before attribute when it follows a closing quote with no space
            line = re.sub(r'"([@A-Za-z])', r'" \1', line)
            # Trim leading spaces inside attribute values and collapse double spaces
            line = re.sub(r'="\s+', '="', line)
            line = re.sub(r'="([^"]*)"', lambda m: '="' + m.group(1).lstrip() + '"', line)
            line = re.sub(r"\s{2,}", " ", line)
            line = re.sub(r"\s+>", ">", line)
        return line

    cleaned: list[str] = []
    prev_blank = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
            continue
        prev_blank = False
        if line.startswith("Copied!"):
            continue
        if line in {"vue", "JS"}:
            continue
        if line.isdigit():
            continue
        if re.fullmatch(r"[0-9]{3,}", line):
            continue
        if re.fullmatch(r"(?:\\d{1,2}){3,}", line):
            continue
        if line == "1":
            continue
        cleaned.append(tidy_tag_spacing(line))

    # trim leading/trailing blank lines
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned) + ("\n" if cleaned else "")


def main() -> None:
    html_files = sorted(
        path
        for path in HTML_DIR.rglob("*.html")
        if not any(part.endswith("_files") for part in path.parts)
    )
    if not html_files:
        print("No HTML files found under data/html")
        return

    # ensure output dirs
    for sub in ["raw", "clean", "notags", "nocode"]:
        (OUT_DIR / sub).mkdir(parents=True, exist_ok=True)

    for html_path in html_files:
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        plain = extract_plain_text(html_text)
        txt_path = OUT_DIR / "raw" / html_path.with_suffix(".txt").name
        txt_path.write_text(plain, encoding="utf-8")

        clean_text = clean_noise(plain)
        clean_path = OUT_DIR / "clean" / (html_path.stem + "_clean.txt")
        clean_path.write_text(clean_text, encoding="utf-8")

        # Optional variant: drop lines that still contain angle-bracket tags entirely
        no_tag_lines = [
            line for line in clean_text.splitlines() if "<" not in line and ">" not in line
        ]
        no_tag_path = OUT_DIR / "notags" / (html_path.stem + "_notags.txt")
        no_tag_path.write_text("\n".join(no_tag_lines) + ("\n" if no_tag_lines else ""), encoding="utf-8")

        # Optional variant: drop code-ish lines that still contain braces or common code tokens
        code_pattern = re.compile(r"[{}]|\$store|exportdefault|mapState|dispatch|function")
        file_ref_pattern = re.compile(r"\.(vue|js|css)\b", re.IGNORECASE)
        bracket_line = re.compile(r"^[\[\]{}]+$")
        bracket_comma_line = re.compile(r"^[\[\]{},]+\s*$")
        no_code_lines: list[str] = []
        for line in no_tag_lines:
            if code_pattern.search(line):
                continue
            if bracket_line.match(line):
                continue
            if bracket_comma_line.match(line):
                continue
            if line.startswith("▼"):
                continue
            if file_ref_pattern.search(line):
                continue
            if re.fullmatch(r"\]+|\[+", line):
                continue
            if "store/index.js" in line:
                continue
            no_code_lines.append(line)
        no_code_path = OUT_DIR / "nocode" / (html_path.stem + "_nocode.txt")
        no_code_path.write_text(
            "\n".join(no_code_lines) + ("\n" if no_code_lines else ""), encoding="utf-8"
        )

        print(f"Wrote {txt_path.name}, {clean_path.name}, {no_tag_path.name}, {no_code_path.name}")


if __name__ == "__main__":
    main()
