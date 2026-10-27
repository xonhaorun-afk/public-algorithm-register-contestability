#!/usr/bin/env python3
"""Independent local acceptance checks; does not import the analysis code."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    RESULTS.append((name, bool(condition), detail))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    required = [
        "论文.md", "README.md", "数据字典.md", "LICENSE",
        "analysis/analyze.py", "analysis/download_data.py",
        "analysis/remedy_manual_review.csv", "analysis/render_charts.mjs",
        "analysis/svg_to_png.py", "analysis/requirements.txt",
        "data/algorithms_current_2026-10-28.csv",
        "data/algorithms_history_2026-10-28.csv",
        "data/source_manifest_2026-10-28.json",
        "data/processed/current_coded.csv",
        "outputs/summary.json", "outputs/coverage.csv",
        "outputs/paired_within_v1.csv", "outputs/sensitivity.csv",
        "verifier/v1/acceptance.md",
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    check("必需文件完整", not missing, f"缺失={missing}")

    manifest = json.loads((ROOT / "data/source_manifest_2026-10-28.json").read_text())
    for item in manifest["files"]:
        path = ROOT / item["file"]
        actual = file_hash(path)
        check(
            f"原始快照哈希：{item['kind']}",
            actual == item["sha256"],
            f"预期={item['sha256']}；实际={actual}",
        )

    current = pd.read_csv(ROOT / "data/algorithms_current_2026-10-28.csv", dtype={"algorithm_id": str})
    history = pd.read_csv(ROOT / "data/algorithms_history_2026-10-28.csv", dtype={"algorithm_id": str})
    check("当前原始规模", len(current) == 1608 and len(current.columns) == 31, f"{current.shape}")
    check("历史原始规模", len(history) == 3035 and len(history.columns) == 52, f"{history.shape}")
    check("当前算法标识唯一", current.algorithm_id.nunique() == 1608, f"唯一={current.algorithm_id.nunique()}")
    check("机构数", current.org_id.nunique() == 346, f"机构={current.org_id.nunique()}")

    summary = json.loads((ROOT / "outputs/summary.json").read_text())
    expected = {
        "notice": 1594, "explain": 1183, "challenge": 1548,
        "remedy_mention": 173, "remedy_guidance": 17, "chain_complete": 15,
    }
    coded = pd.read_csv(ROOT / "data/processed/current_coded.csv", dtype={"algorithm_id": str})
    check("编码表规模", len(coded) == 1608 and coded.algorithm_id.nunique() == 1608, f"{coded.shape}")
    for indicator, count in expected.items():
        output_count = int(coded[indicator].sum())
        check(
            f"核心计数：{indicator}",
            output_count == count == summary["coverage"][indicator]["count"],
            f"编码={output_count}；summary={summary['coverage'][indicator]['count']}；论文预期={count}",
        )

    review = pd.read_csv(ROOT / "analysis/remedy_manual_review.csv", dtype={"algorithm_id": str})
    candidates = review[review.selection.eq("all_automated_candidates")]
    random_other = review[review.selection.str.startswith("random_40", na=False)]
    check("人工复核总数与构成", len(review) == 62 and len(candidates) == 22 and len(random_other) == 40,
          f"总={len(review)}；候选={len(candidates)}；随机={len(random_other)}")
    check("人工真阳性与假阳性", int(candidates.manual_guidance.sum()) == 17 and int((~candidates.manual_guidance).sum()) == 5,
          f"真={int(candidates.manual_guidance.sum())}；假={int((~candidates.manual_guidance).sum())}")
    check("复核理由完整", review.review_note.fillna("").str.strip().ne("").all(), "62条均应有理由")
    check("自动候选已全部复核", int(coded.automated_remedy_guidance.sum()) == 22 and coded.loc[coded.automated_remedy_guidance, "manually_reviewed"].all(),
          "22个自动候选均有逐条判定")

    guided = coded[coded.remedy_guidance]
    org_counts = guided.organization.value_counts()
    check("救济导航机构集中度", guided.org_id.nunique() == 7 and int(org_counts.get("Provincie Zuid-Holland", 0)) == 8 and int(org_counts.get("Gemeente Amsterdam", 0)) == 4,
          f"机构={guided.org_id.nunique()}；{org_counts.to_dict()}")
    high = coded[coded.publication_category.eq("Hoog-risico AI-systeem") & coded.remedy_guidance]
    check("高风险导航模板边界", len(high) == 4 and high.organization.eq("Provincie Zuid-Holland").all(),
          f"高风险导航={len(high)}；机构={high.organization.unique().tolist()}")
    douane = coded[coded.organization.eq("Douane")]
    check("Douane反例", len(douane) == 48 and int(douane.remedy_mention.sum()) == 46 and int(douane.remedy_guidance.sum()) == 0,
          f"n={len(douane)}；词={int(douane.remedy_mention.sum())}；导航={int(douane.remedy_guidance.sum())}")

    paired = pd.read_csv(ROOT / "outputs/paired_within_v1.csv")
    check("同标准配对数", paired.pairs.eq(539).all() and len(paired) == 4, f"行={len(paired)}；pairs={paired.pairs.unique().tolist()}")
    p_notice = float(paired.loc[paired.indicator.eq("notice"), "mcnemar_exact_p"].iloc[0])
    p_explain = float(paired.loc[paired.indicator.eq("explain"), "mcnemar_exact_p"].iloc[0])
    check("配对精确检验", math.isclose(p_notice, 0.0078125) and math.isclose(p_explain, 0.0018310546875),
          f"notice={p_notice}；explain={p_explain}")
    models = pd.read_csv(ROOT / "outputs/clustered_models.csv")
    check("稀疏结果未建模", models.outcome.eq("explain").all(), f"模型结果={models.outcome.unique().tolist()}")

    sensitivity = pd.read_csv(ROOT / "outputs/sensitivity.csv")
    remedy_rows = sensitivity[sensitivity.indicator.eq("remedy_guidance")]
    all_rows = remedy_rows[remedy_rows["sample"].eq("all")]
    in_use_rows = remedy_rows[remedy_rows["sample"].eq("in_use")]
    check("字符门槛下导航稳定", all_rows["count"].eq(17).all() and in_use_rows["count"].eq(13).all(),
          f"全量={all_rows['count'].tolist()}；在用={in_use_rows['count'].tolist()}")
    org_eq = pd.read_csv(ROOT / "outputs/organization_equal_weight.csv")
    check("机构等权与bootstrap", org_eq.organizations.eq(346).all() and org_eq.bootstrap_low_pct.notna().all(),
          f"行={len(org_eq)}")

    paper_path = ROOT / "论文.md"
    paper = paper_path.read_text(encoding="utf-8")
    check("论文篇幅", len(paper) >= 20000, f"字符={len(paper)}")
    for heading in ["摘要", "问题提出", "文献与理论", "研究设计", "定量结果", "结构化定性比较", "综合讨论", "结论与局限", "数据、代码与复现声明"]:
        check(f"论文结构：{heading}", heading in paper, "应存在对应部分")
    check("无末尾参考文献表", not re.search(r"^#{1,3}\s*(参考文献|References)\s*$", paper, re.M), "采用内联链接")
    check("无占位标记", not re.search(r"TODO|PENDING|待补|待完成|\[插入|example\.com", paper, re.I), "论文不得含未完成占位")
    for phrase in ["不推断实际申诉", "不作因果推断", "全站FAQ", "风险分类的独立效应", "不能据此计算下降率"]:
        check(f"解释边界：{phrase}", phrase in paper, "正文须保留边界")

    markdown_links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", paper)
    empty_links = [link for link in markdown_links if not link.strip()]
    check("无空链接", not empty_links, f"链接数={len(markdown_links)}")
    external = [link for link in markdown_links if link.startswith(("https://", "http://"))]
    check("外部来源数量", len(set(external)) >= 10, f"唯一外部链接={len(set(external))}")
    local_missing = []
    for link in markdown_links:
        if link.startswith(("https://", "http://", "#")):
            continue
        target = (paper_path.parent / unquote(link.split("#")[0])).resolve()
        if not target.exists():
            local_missing.append(link)
    check("本地引文与图片路径", not local_missing, f"缺失={local_missing}")

    for number in range(1, 6):
        matches = list((ROOT / "figures").glob(f"figure_{number}_*.png"))
        ok = len(matches) == 1
        if ok:
            with Image.open(matches[0]) as image:
                ok = image.width >= 1200 and image.height >= 700
                detail = f"{matches[0].name}：{image.width}×{image.height}"
        else:
            detail = f"匹配={matches}"
        check(f"图{number}文件与尺寸", ok, detail)
    check("论文嵌入五图", len(re.findall(r"!\[[^\]]*\]\(figures/figure_[1-5]_.*?\.png\)", paper)) == 5,
          "应有五个PNG图片链接")

    passed = sum(ok for _, ok, _ in RESULTS)
    failed = len(RESULTS) - passed
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}｜{detail}")
    print(f"SUMMARY｜total={len(RESULTS)}｜passed={passed}｜failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
