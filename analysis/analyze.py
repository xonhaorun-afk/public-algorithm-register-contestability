#!/usr/bin/env python3
"""Reproducible analysis for the Dutch Algorithm Register contestability study.

Input snapshots are public CSV files downloaded from algoritmes.overheid.nl.
The script deliberately measures disclosure conditions, not actual remedy outcomes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.proportion import proportion_confint

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
PROCESSED = DATA / "processed"
OUT.mkdir(exist_ok=True)
PROCESSED.mkdir(exist_ok=True)

CURRENT_FILE = DATA / "algorithms_current_2026-10-28.csv"
HISTORY_FILE = DATA / "algorithms_history_2026-10-28.csv"
TEXT_FIELDS = [
    "description_short", "goal", "proportionality", "lawful_basis",
    "source_data", "methods_and_models", "human_intervention", "risks",
    "impacttoetsen", "contact_email",
]
FIELD_LABELS = {
    "notice": "知情：简介与目标均非占位",
    "explain": "理解：数据、技术与风险均非占位",
    "challenge": "质疑：人工介入非占位且含可机读联系方式",
    "remedy_mention": "救济词汇：任一文本字段出现",
    "remedy_guidance": "救济导航：同字段含程序或去向线索",
    "chain_complete": "完整披露链：上述四项同时满足",
}
PLACEHOLDERS = {
    "", "-", "--", "/", "nvt", "n.v.t", "n.v.t.", "n.v.t..", "n/a", "na",
    "niet van toepassing", "niet van toepassing.", "niet beschikbaar",
    "niet bekend", "niet bekend.", "onbekend", "geen", "geen.", "nee",
    "veld niet ingevuld", "wordt vervolgd", "nog niet beschikbaar",
    "zie hierboven", "zie boven", "n.t.b", "n.t.b.", "tb", "tbd",
}
REMEDY_RE = re.compile(
    r"\b(?:bezwaar|bezwaren|beroep|klacht|klachten|objection|appeal|complaint)\b",
    re.IGNORECASE,
)
# A conservative lexical proxy: a remedy word and, in the SAME field, a concrete
# destination, document, deadline, URL or e-mail. A bare statement that appeals
# are possible does not qualify. Every automated positive is manually audited.
GUIDE_RE = re.compile(
    r"https?://|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"binnen\s+(?:\d+|zes|acht|twaalf|\w+)\s+weken|"
    r"(?:nationale\s+)?ombudsman|bezwaarcommissie|klachtenformulier|"
    r"bezwaarschrift|rechtbank|juridische\s+afdeling|griffie|"
    r"klachtenloket|digitale\s+balie|bezwaar\s+indienen\s+bij|"
    r"bezwaar\s+maken\s+bij\s+de\s+gemeente|beroep\s+instellen\s+bij",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:0\d{2,3}[-\s]?\d{5,7}|1[01]\d{3})(?!\d)")


def norm(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def informative(value: object, minimum: int = 20) -> bool:
    text = norm(value)
    key = text.lower().strip(" \t\r\n")
    if key in PLACEHOLDERS or not text:
        return False
    # Length is only a floor for removing terse placeholders/model labels;
    # it is never used as a quality score.
    return len(text) >= minimum


def valid_contact(value: object) -> bool:
    text = norm(value)
    return bool(EMAIL_RE.search(text) or URL_RE.search(text) or PHONE_RE.search(text))


def encode(df: pd.DataFrame, minimum: int = 20) -> pd.DataFrame:
    df = df.copy()
    for col in TEXT_FIELDS + ["contact_email", "organization", "algorithm_id", "org_id"]:
        if col not in df:
            df[col] = ""
        df[col] = df[col].map(norm)

    df["notice"] = (
        df["description_short"].map(lambda x: informative(x, minimum))
        & df["goal"].map(lambda x: informative(x, minimum))
    )
    for col in ["source_data", "methods_and_models", "risks", "human_intervention", "goal", "proportionality", "lawful_basis"]:
        df[f"info_{col}"] = df[col].map(lambda x: informative(x, minimum))
    df["explain"] = df[["info_source_data", "info_methods_and_models", "info_risks"]].all(axis=1)
    df["valid_contact"] = df["contact_email"].map(valid_contact)
    df["challenge"] = df["info_human_intervention"] & df["valid_contact"]

    remedy_by_field = df[TEXT_FIELDS].apply(lambda col: col.map(lambda x: bool(REMEDY_RE.search(x))))
    guide_by_field = df[TEXT_FIELDS].apply(
        lambda col: col.map(lambda x: bool(REMEDY_RE.search(x) and GUIDE_RE.search(x)))
    )
    df["remedy_mention"] = remedy_by_field.any(axis=1)
    df["remedy_guidance"] = guide_by_field.any(axis=1)
    df["remedy_fields"] = remedy_by_field.apply(
        lambda row: ";".join([c for c in TEXT_FIELDS if row[c]]), axis=1
    )
    df["guide_fields"] = guide_by_field.apply(
        lambda row: ";".join([c for c in TEXT_FIELDS if row[c]]), axis=1
    )
    df["automated_remedy_guidance"] = df["remedy_guidance"]
    df["chain_complete"] = df[["notice", "explain", "challenge", "remedy_guidance"]].all(axis=1)
    df["disclosure_components"] = df[["notice", "explain", "challenge", "remedy_guidance"]].sum(axis=1)
    return df


def apply_manual_review(df: pd.DataFrame) -> pd.DataFrame:
    """Apply record-level manual decisions; retain automated candidates for audit."""
    df = df.copy()
    review = pd.read_csv(ROOT / "analysis" / "remedy_manual_review.csv", dtype={"algorithm_id": str})
    decisions = review.set_index("algorithm_id")["manual_guidance"].astype(bool)
    matched = df["algorithm_id"].isin(decisions.index)
    df.loc[matched, "remedy_guidance"] = df.loc[matched, "algorithm_id"].map(decisions)
    df["manually_reviewed"] = matched
    df["chain_complete"] = df[["notice", "explain", "challenge", "remedy_guidance"]].all(axis=1)
    df["disclosure_components"] = df[["notice", "explain", "challenge", "remedy_guidance"]].sum(axis=1)
    return df


def coverage_table(df: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
    rows = []
    n = len(df)
    for indicator in indicators:
        count = int(df[indicator].sum())
        lo, hi = proportion_confint(count, n, alpha=0.05, method="wilson")
        rows.append({
            "indicator": indicator, "label": FIELD_LABELS.get(indicator, indicator),
            "count": count, "n": n, "percent": 100 * count / n,
            "wilson_low_pct": 100 * lo, "wilson_high_pct": 100 * hi,
        })
    return pd.DataFrame(rows)


def grouped_tests(df: pd.DataFrame, group: str, indicators: list[str]) -> pd.DataFrame:
    rows = []
    for indicator in indicators:
        table = pd.crosstab(df[group], df[indicator])
        if table.shape[0] < 2 or table.shape[1] < 2:
            continue
        chi2, p, dof, expected = st.chi2_contingency(table)
        n = table.to_numpy().sum()
        cramer_v = np.sqrt(chi2 / (n * min(table.shape[0] - 1, table.shape[1] - 1)))
        for level, sub in df.groupby(group):
            count = int(sub[indicator].sum())
            lo, hi = proportion_confint(count, len(sub), method="wilson")
            rows.append({
                "group_variable": group, "group": level, "indicator": indicator,
                "count": count, "n": len(sub), "percent": 100 * count / len(sub),
                "wilson_low_pct": 100 * lo, "wilson_high_pct": 100 * hi,
                "chi2": chi2, "p_value": p, "dof": dof, "cramers_v": cramer_v,
                "min_expected": expected.min(),
            })
    return pd.DataFrame(rows)


def organization_equal_weight(df: pd.DataFrame, indicators: list[str], seed: int = 20261028) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    org_rates = df.groupby("org_id")[indicators].mean()
    rows = []
    for indicator in indicators:
        values = org_rates[indicator].to_numpy()
        boot = rng.choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
        rows.append({
            "indicator": indicator, "organizations": len(values),
            "entry_weighted_percent": 100 * df[indicator].mean(),
            "organization_equal_weighted_percent": 100 * values.mean(),
            "bootstrap_low_pct": 100 * np.quantile(boot, 0.025),
            "bootstrap_high_pct": 100 * np.quantile(boot, 0.975),
        })
    return pd.DataFrame(rows)


def mcnemar_exact(b: int, c: int) -> float:
    discordant = b + c
    if discordant == 0:
        return 1.0
    return float(st.binomtest(min(b, c), discordant, 0.5).pvalue)


def paired_analysis(history: pd.DataFrame, standard: str = "1.0") -> tuple[pd.DataFrame, pd.DataFrame]:
    h = history[history["standard_version"].eq(standard)].copy()
    h["dt"] = pd.to_datetime(h["publication_dt"], errors="coerce", utc=True)
    h = h.dropna(subset=["dt"]).sort_values(["algorithm_id", "dt"], kind="stable")
    counts = h.groupby("algorithm_id").size()
    ids = counts[counts >= 2].index
    h = h[h["algorithm_id"].isin(ids)]
    first = h.groupby("algorithm_id", as_index=False).first()
    last = h.groupby("algorithm_id", as_index=False).last()
    a, b = encode(first), encode(last)
    keys = ["algorithm_id", "name", "organization", "org_id"]
    pair = a[keys].merge(
        a[["algorithm_id", "notice", "explain", "challenge", "remedy_mention", "remedy_guidance", "chain_complete"]],
        on="algorithm_id",
    ).merge(
        b[["algorithm_id", "notice", "explain", "challenge", "remedy_mention", "remedy_guidance", "chain_complete", "publication_dt"]],
        on="algorithm_id", suffixes=("_first", "_last"),
    )
    rows = []
    # Cross-version inferential comparisons are limited to common, non-sparse
    # measures; remedy candidates require version-specific manual review.
    for indicator in ["notice", "explain", "challenge", "remedy_mention"]:
        x, y = pair[f"{indicator}_first"], pair[f"{indicator}_last"]
        improve = int((~x & y).sum())
        decline = int((x & ~y).sum())
        rows.append({
            "standard": standard, "indicator": indicator, "pairs": len(pair),
            "first_count": int(x.sum()), "last_count": int(y.sum()),
            "first_percent": 100 * x.mean(), "last_percent": 100 * y.mean(),
            "change_pp": 100 * (y.mean() - x.mean()),
            "improved_0_to_1": improve, "declined_1_to_0": decline,
            "unchanged": int((x == y).sum()), "mcnemar_exact_p": mcnemar_exact(improve, decline),
        })
    return pd.DataFrame(rows), pair


def cross_standard_descriptive(history: pd.DataFrame, current_coded: pd.DataFrame) -> pd.DataFrame:
    """Describe pre-1.0 fields without treating them as equivalent to 1.0 measures."""
    old_standards = ["0.1", "0.2.3", "0.3.1"]
    old = history[history["standard_version"].isin(old_standards)].copy()
    old["dt"] = pd.to_datetime(old["publication_dt"], errors="coerce", utc=True)
    old = old.sort_values(["algorithm_id", "dt"], na_position="first", kind="stable")
    old_last = old.groupby("algorithm_id").last()
    new_last = history[history["standard_version"].eq("1.0")].groupby("algorithm_id").last()
    ids = old_last.index.intersection(new_last.index)
    current_indexed = current_coded.set_index("algorithm_id")
    columns = {}
    for field in ["objection_procedure", "decision_making_process", "monitoring", "performance_standard"]:
        columns[f"pre_1_0_{field}"] = old_last.loc[ids, field].map(lambda x: informative(x, 1))
    for indicator in ["remedy_mention", "remedy_guidance", "notice", "explain", "challenge"]:
        columns[f"current_{indicator}"] = current_indexed.reindex(ids)[indicator].astype(bool).to_numpy()
    frame = pd.DataFrame(columns, index=ids)
    result = pd.DataFrame({
        "indicator": frame.columns,
        "count": [int(frame[c].sum()) for c in frame.columns],
        "transition_algorithms": len(frame),
    })
    result["percent"] = 100 * result["count"] / len(frame)
    return result


def fit_clustered_models(df: pd.DataFrame) -> pd.DataFrame:
    model_df = df.copy()
    model_df["org_entries"] = model_df.groupby("org_id")["algorithm_id"].transform("size")
    model_df["log_org_entries"] = np.log1p(model_df["org_entries"])
    model_df["risk_category"] = model_df["publication_category"].fillna("Onbekend")
    model_df["status_clean"] = model_df["status"].fillna("Onbekend")
    rows = []
    # Only the explanation outcome has enough events for a multivariable model.
    # The validated remedy outcome is too sparse and is reported descriptively.
    for outcome in ["explain"]:
        formula = f"{outcome} ~ C(risk_category) + C(status_clean) + log_org_entries"
        model = smf.glm(formula, data=model_df, family=sm.families.Binomial()).fit(
            cov_type="cluster", cov_kwds={"groups": model_df["org_id"]}
        )
        conf = model.conf_int()
        for term in model.params.index:
            if term == "Intercept":
                continue
            rows.append({
                "outcome": outcome, "term": term, "coefficient": model.params[term],
                "odds_ratio": np.exp(model.params[term]), "std_error_clustered": model.bse[term],
                "or_low_95": np.exp(conf.loc[term, 0]), "or_high_95": np.exp(conf.loc[term, 1]),
                "p_value": model.pvalues[term], "n": int(model.nobs),
                "organizations": model_df["org_id"].nunique(),
            })
    return pd.DataFrame(rows)


def main() -> None:
    current = pd.read_csv(CURRENT_FILE, dtype=str, keep_default_na=False)
    history = pd.read_csv(HISTORY_FILE, dtype=str, keep_default_na=False)
    assert current["algorithm_id"].is_unique, "Current algorithm_id must be unique"
    coded = apply_manual_review(encode(current))
    indicators = ["notice", "explain", "challenge", "remedy_mention", "remedy_guidance", "chain_complete"]

    coverage_table(coded, indicators).to_csv(OUT / "coverage.csv", index=False)
    field_indicators = [
        "info_goal", "info_proportionality", "info_lawful_basis", "info_source_data",
        "info_methods_and_models", "info_human_intervention", "info_risks", "valid_contact",
    ]
    coverage_table(coded, field_indicators).to_csv(OUT / "field_coverage.csv", index=False)
    grouped_tests(coded, "publication_category", indicators).to_csv(OUT / "category_tests.csv", index=False)
    grouped_tests(coded, "status", indicators).to_csv(OUT / "status_tests.csv", index=False)
    organization_equal_weight(coded, indicators).to_csv(OUT / "organization_equal_weight.csv", index=False)

    org = coded.groupby(["org_id", "organization"]).agg(
        entries=("algorithm_id", "size"),
        notice_pct=("notice", "mean"), explain_pct=("explain", "mean"),
        challenge_pct=("challenge", "mean"), remedy_mention_pct=("remedy_mention", "mean"),
        remedy_guidance_pct=("remedy_guidance", "mean"), chain_complete_pct=("chain_complete", "mean"),
    ).reset_index()
    for col in [c for c in org.columns if c.endswith("_pct")]:
        org[col] *= 100
    org.sort_values("entries", ascending=False).to_csv(OUT / "organization_summary.csv", index=False)

    fit_clustered_models(coded).to_csv(OUT / "clustered_models.csv", index=False)
    paired, pair_records = paired_analysis(history, "1.0")
    paired.to_csv(OUT / "paired_within_v1.csv", index=False)
    pair_records.to_csv(PROCESSED / "paired_record_indicators.csv", index=False)

    sensitivity_rows = []
    for minimum in [1, 20, 40]:
        variant = apply_manual_review(encode(current, minimum=minimum))
        for sample, sub in [("all", variant), ("in_use", variant[variant["status"].eq("In gebruik")])]:
            for indicator in indicators:
                sensitivity_rows.append({
                    "minimum_characters": minimum, "sample": sample, "indicator": indicator,
                    "n": len(sub), "count": int(sub[indicator].sum()),
                    "percent": 100 * sub[indicator].mean(),
                })
    pd.DataFrame(sensitivity_rows).to_csv(OUT / "sensitivity.csv", index=False)

    keep = [
        "algorithm_id", "name", "organization", "org_id", "publication_category", "status",
        "notice", "explain", "challenge", "remedy_mention", "remedy_guidance", "chain_complete",
        "disclosure_components", "remedy_fields", "guide_fields", "valid_contact",
        "automated_remedy_guidance", "manually_reviewed",
    ] + field_indicators
    coded[keep].to_csv(PROCESSED / "current_coded.csv", index=False)

    # An audit universe rather than a cherry-picked qualitative sample.
    audit = coded[coded["remedy_mention"]].copy()
    audit_cols = ["algorithm_id", "name", "organization", "publication_category", "status", "remedy_fields", "guide_fields", "remedy_guidance"] + TEXT_FIELDS
    audit[audit_cols].to_csv(OUT / "remedy_audit_universe.csv", index=False)

    dated_history = history.copy()
    dated_history["dt"] = pd.to_datetime(dated_history["publication_dt"], errors="coerce", utc=True)
    dated_history = dated_history.sort_values(["algorithm_id", "dt"], na_position="first", kind="stable")
    transitions = dated_history.groupby("algorithm_id").agg(
        versions=("algorithm_id", "size"),
        first_standard=("standard_version", "first"),
        last_standard=("standard_version", "last"),
    ).reset_index()
    transitions = transitions[transitions["versions"] >= 2]
    pd.crosstab(transitions["first_standard"], transitions["last_standard"]).to_csv(OUT / "standard_transition_counts.csv")
    cross_standard_descriptive(history, coded).to_csv(OUT / "cross_standard_descriptive.csv", index=False)

    summary = {
        "snapshot": "2026-10-28",
        "current_rows": len(current), "current_unique_algorithms": current["algorithm_id"].nunique(),
        "current_organizations": current["org_id"].nunique(),
        "history_rows": len(history), "history_unique_algorithms": history["algorithm_id"].nunique(),
        "multi_version_algorithms": int((history.groupby("algorithm_id").size() >= 2).sum()),
        "paired_within_v1_algorithms": int(paired["pairs"].iloc[0]),
        "automated_remedy_candidates": int(coded["automated_remedy_guidance"].sum()),
        "manually_validated_remedy_guidance": int(coded["remedy_guidance"].sum()),
        "manual_review_records": int(coded["manually_reviewed"].sum()),
        "category_counts": current["publication_category"].value_counts().to_dict(),
        "status_counts": current["status"].value_counts().to_dict(),
        "coverage": {r["indicator"]: {"count": r["count"], "percent": r["percent"]} for _, r in coverage_table(coded, indicators).iterrows()},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    chart_data = {
        "coverage": json.loads(coverage_table(coded, indicators).to_json(orient="records")),
        "category": json.loads(grouped_tests(coded, "publication_category", indicators).to_json(orient="records")),
        "organizations": json.loads(org.sort_values("entries", ascending=False).head(12).to_json(orient="records")),
        "paired": json.loads(paired.to_json(orient="records")),
        "equal_weight": json.loads(organization_equal_weight(coded, indicators).to_json(orient="records")),
    }
    (OUT / "chart_data.json").write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
