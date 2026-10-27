#!/usr/bin/env python3
"""Independently verify the public GitHub delivery and fixed source snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://raw.githubusercontent.com/xonhaorun-afk/public-algorithm-register-contestability/main/"
EXPECTED = {
    "论文.md": "07a8a064c84ad5faef62f3ef85e6887bfe50ae0767ebe2cc47ba49d4fbf2910f",
    "README.md": "29a50d61ce8a378ed1aff268ceffbc8976dc8af8096a6fb51895e0c9f088b2fb",
    "数据字典.md": "83a9b7d7422c8b03e891088e9e26e7e2f3141dd98202d4c7655229be5f4db467",
    "data/source_manifest_2026-10-28.json": "54f6fd6b1e5731031e633b91670eda385e705522a8462c7262b003b4ea212386",
    "data/来源与许可说明.md": "bad590e922c2f317aa2f68969512a09081d4f53dc6814d902df247d03f8f0578",
    "analysis/analyze.py": "fe8c9f02c5c7de6b732579523363a11d615ce0a397655c603c4d8e8f7589470d",
    "analysis/download_data.py": "bbe6097fa089c00eaadd7860bb653861e2c45d2ccf5e2c852a1a5595822d4891",
    "analysis/restore_archive.py": "4f76b90e5ff9c1a50a6861bac9aacf57f0fa475ec6f7d62a6e63b12368190da9",
    "analysis/render_charts.mjs": "3f6ad18357f9c25d1e44c109f0d0d59b69f02740af68ea5319fb794d7c3c7f6e",
    "analysis/svg_to_png.py": "72d32f0c76639ca89c6190ae332d774a89f8903ea2566ad8062bbf298595552f",
    "analysis/remedy_manual_review.csv": "108ed4a2b03ce4ee3397d1e1646413a60667bb2c2301e89feed59bf1e95a43be",
    "analysis/requirements.txt": "03d0d291c3099239932c593a670100f52dfef3cf8388aa80e519657b0551d4f1",
    "analysis/package.json": "044a2d5ebccf450b492e46ea47f473e6159b21bdab8dd1cd682bc12e658c92d0",
    "analysis/package-lock.json": "c8f2b1874eec7a60fa515d2f3bb484bb144175686a8e5340211d6c2662e22275",
    "outputs/summary.json": "3c542beeef1e58614bb2aefe34f12cd330377b9c74b292f6b59934cec8c56520",
    "outputs/coverage.csv": "5848a18e863665bc693021d95b108bb7f785676c3dc5a687f17234587b16c056",
    "outputs/field_coverage.csv": "c6edadc4cb77f3d6eb66bd80b40a4094c067e903d392714f1ff6da92e418bb8b",
    "outputs/paired_within_v1.csv": "2ba57985fb5325e19edaf200e4440c9061459d9f075b4af1d92491a3023a2af6",
    "outputs/sensitivity.csv": "4edc140442234fa0147855e15a96dbc7b2d511688b742ff9f110282e3624ec01",
    "outputs/cross_standard_descriptive.csv": "86ba5db0a57212f084d11ebb5b862894223b4d13b9cd74fa5f37fcf8ce1d1337",
    "outputs/organization_equal_weight.csv": "0352f72ebaa06087227d823f8ea17adda3db8f8db9c78595ff54f557d3677894",
    "outputs/organization_summary.csv": "a7e1a650dc01d0f1fa5d5f115303f066d0301e70c987b6e1064991a6918e4884",
    "outputs/clustered_models.csv": "54c090619f0bc32b5245a1c183760bb1e5297e98a28c4b5f79ce20253ab00080",
    "outputs/standard_transition_counts.csv": "7419574c31a155761fa7b591d4eee27e3978503230bdbd82ceb79ddc44cfefaf",
    "outputs/category_tests.csv": "19d9c3f9329dee085e0ff6227354acbbbb35257401b889d1b90dbe64ff4a4085",
    "outputs/status_tests.csv": "ce7e86ce7b9bdfc5576ee389f245b89a230cc9ea5b601dc68d3dad665d6dd729",
    "verifier/run_acceptance.sh": "9ad931c58f897d1b8c2961fc9c4ebceb3b452df4b65f2fdbb33d3c8d77f3c501",
    "verifier/v2/acceptance.md": "bcbf13029d9f009d17eaf821c8e5b11838ce47fb050adaee75b55e93dac2215f",
    "verifier/v2/verify.py": "34eced45d0550e2a673f0b1bba5c79c35560d0c9bcb37174540d30fe968a113a",
}
FIGURES = [
    "figures/figure_1_disclosure_chain.svg",
    "figures/figure_2_coverage.svg",
    "figures/figure_3_category_heatmap.svg",
    "figures/figure_4_organization_heatmap.svg",
    "figures/figure_5_paired_change.svg",
]
LOGS = [
    "verifier/runs/acceptance_20261027T180313Z.log",
    "verifier/runs/acceptance_20261027T180344Z.log",
    "verifier/runs/acceptance_20261027T184528Z.log",
    "verifier/runs/acceptance_20261027T184601Z.log",
    "verifier/runs/acceptance_20261027T184628Z.log",
    "verifier/runs/acceptance_20261027T185647Z.log",
]
SOURCES = [
    ("current", "https://algoritmes.overheid.nl/api/downloads/NLD?filetype=csv", "062550033289976baa6ee2b75a923c991c984e4ccf9d676297b434a374aad01f"),
    ("history", "https://algoritmes.overheid.nl/api/downloads/history/NLD?filetype=csv", "83d3cbafb93146c5c39fead5cb8de2ba75c859e24d0e5120c56d4f5115daf54f"),
]

results: list[dict[str, object]] = []
cache: dict[str, bytes] = {}

def record(name: str, ok: bool, detail: str) -> None:
    results.append({"name": name, "passed": bool(ok), "detail": detail})


def fetch(path: str) -> bytes:
    if path not in cache:
        response = requests.get(BASE + quote(path, safe="/"), timeout=90)
        response.raise_for_status()
        cache[path] = response.content
    return cache[path]


for path, expected in EXPECTED.items():
    try:
        content = fetch(path)
        actual = hashlib.sha256(content).hexdigest()
        record(f"远端哈希：{path}", actual == expected, f"expected={expected}; actual={actual}")
    except Exception as exc:
        record(f"远端哈希：{path}", False, f"{type(exc).__name__}: {exc}")

for path in FIGURES:
    try:
        content = fetch(path)
        root = ET.fromstring(content)
        ok = root.tag.endswith("svg") and len(content) > 500
        record(f"远端SVG：{path}", ok, f"bytes={len(content)}; root={root.tag}")
    except Exception as exc:
        record(f"远端SVG：{path}", False, f"{type(exc).__name__}: {exc}")

for path in LOGS:
    try:
        text = fetch(path).decode("utf-8")
        record(f"历史日志：{path}", ("SUMMARY｜" in text or "Traceback" in text) and "command=" in text, f"chars={len(text)}")
    except Exception as exc:
        record(f"历史日志：{path}", False, f"{type(exc).__name__}: {exc}")

try:
    paper = fetch("论文.md").decode("utf-8")
    links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", paper)
    local_links = sorted({unquote(link.split("#")[0]) for link in links if not link.startswith(("https://", "http://", "#"))})
    record("论文五张SVG链接", len(re.findall(r"!\[[^\]]*\]\(figures/figure_[1-5]_.*?\.svg\)", paper)) == 5, "应为5")
    record("论文不含远端PNG图片链接", ".png)" not in paper, "网页版应使用SVG")
    record("论文不含本地CSV链接", "](data/algorithms_" not in paper, "原始记录示例应指向官方接口")
    for link in local_links:
        try:
            fetch(link)
            record(f"论文本地链接：{link}", True, "HTTP 200")
        except Exception as exc:
            record(f"论文本地链接：{link}", False, f"{type(exc).__name__}: {exc}")
except Exception as exc:
    record("论文链接解析", False, f"{type(exc).__name__}: {exc}")

for label, url, expected in SOURCES:
    try:
        response = requests.get(url, timeout=240)
        response.raise_for_status()
        actual = hashlib.sha256(response.content).hexdigest()
        record(f"官方快照恢复：{label}", actual == expected, f"expected={expected}; actual={actual}; bytes={len(response.content)}")
    except Exception as exc:
        record(f"官方快照恢复：{label}", False, f"{type(exc).__name__}: {exc}")

passed = sum(bool(item["passed"]) for item in results)
report = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "repository": "https://github.com/xonhaorun-afk/public-algorithm-register-contestability",
    "branch": "main",
    "total": len(results),
    "passed": passed,
    "failed": len(results) - passed,
    "results": results,
    "boundary": "Remote verification covers public files and snapshot recovery; it does not claim that raw CSV or PNG binaries are stored in GitHub.",
}
out = ROOT / "verifier/v2/remote_acceptance.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for item in results:
    print(f"[{'PASS' if item['passed'] else 'FAIL'}] {item['name']}｜{item['detail']}")
print(f"SUMMARY｜total={len(results)}｜passed={passed}｜failed={len(results)-passed}")
raise SystemExit(0 if passed == len(results) else 1)
