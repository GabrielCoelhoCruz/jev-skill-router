"""Replay the published-main Jev observations without credentials or network."""

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

from router import INPUT_USD_PER_MILLION, InputError, catalogue_from, route

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "benchmark"
DATASET_SHA = "a1fd9b23e3ee2af166b25a15ea41f8163c8717c9bfa638b5ab2acb531e11f2ad"
METADATA_SHA = "f11a293ba5801a4365f8ad8e81faf611f89643226bd1a0c87c60e7e36a2c1302"
ORDINARY_SHA = "ba59acfeb36855413cd02d050a56e18fa1636810f7875a29d70a0bc8a0bc834e"
LIVE_SHA = "26cac21dc7a98b3dba9d2d62dd3c3c0c6e805e8fa54c1efb4cb7c7738b4e0d34"
ORDINARY_RESULTS_SHA = "9c89fb052f9bad2a84efa488a6b50f7ff4376ee67358ee95bd229cb303e2a261"
CATALOGUE_SHA = "84ea9cfdd29789ae79434f330b5cbc96c8d9c8c4df4022a2924b3cf40e5bf4ac"
ROUTER_SHA = "cff71463063cfc572f935feaf67fb03e5cc30d9469f25c59cbcf08d0cdc5eee2"
CONFIG_SHA = "cc8a66f9cc67043e400b1edd62fb7a23efd8dca209c4bd26c76e72412a4882df"
ERRORS = {"api_unavailable", "api_invalid_response", "api_model_mismatch"}


def read_pinned(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise InputError(f"pinned input changed: {path.name}")
    return data


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify(observations, cases, labels, repeats):
    expected = {(case["id"], repeat) for repeat in range(1, repeats + 1) for case in cases}
    keys = [(item.get("id"), item.get("repeat")) for item in observations]
    if (len(observations) != len(expected) or any(type(item.get("repeat")) is not int for item in observations)
            or len(set(keys)) != len(keys) or set(keys) != expected):
        raise InputError("observations must match every planned id and repeat exactly once")
    if len({case["id"] for case in cases}) != len(cases):
        raise InputError("duplicate case id")
    known = set(labels) | {"__no_skill__", "__review__"}
    for row in observations:
        if set(row) != {"id", "repeat", "decision", "latency_ms"}:
            raise InputError("unexpected observation fields")
        decision = row.get("decision")
        if not isinstance(decision, dict) or type(row.get("latency_ms")) not in (float, int) or not math.isfinite(row["latency_ms"]) or row["latency_ms"] < 0:
            raise InputError("invalid recorded decision or latency")
        if set(decision) != {"outcome", "skill_id", "probabilities", "confidence", "source", "reason", "usage"}:
            raise InputError("unexpected decision fields")
        usage = decision.get("usage")
        if not isinstance(usage, dict) or set(usage) != {"requests", "input_tokens", "output_tokens", "estimated_input_usd"} or usage.get("requests") != 1 or type(usage["requests"]) is not int:
            raise InputError("each observation must record exactly one API attempt")
        for field in ("input_tokens", "output_tokens"):
            value = usage.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise InputError("invalid token usage")
        expected_cost = (round(usage["input_tokens"] * INPUT_USD_PER_MILLION / 1_000_000, 12)
                         if usage["input_tokens"] is not None else None)
        if (usage["estimated_input_usd"] is not None and
                (type(usage["estimated_input_usd"]) not in (int, float) or not math.isfinite(usage["estimated_input_usd"]))) or usage["estimated_input_usd"] != expected_cost:
            raise InputError("recorded input estimate contradicts usage")
        source, reason = decision.get("source"), decision.get("reason")
        action = decision.get("skill_id") if decision.get("outcome") == "route" else decision.get("outcome")
        if source == "api":
            if reason not in ERRORS and not (isinstance(reason, str) and reason.startswith("api_http_") and reason[9:].isdigit()):
                raise InputError("unknown API failure reason")
            if action != "review" or decision.get("skill_id") is not None or decision.get("confidence") is not None or decision.get("probabilities") != {}:
                raise InputError("API errors must remain unscored review decisions")
            if usage["input_tokens"] is not None or usage["output_tokens"] is not None:
                raise InputError("failed API response cannot report successful token usage")
        elif source == "jev":
            if reason not in ("model_choice", "uncertain") or action not in labels | {"no_skill", "review"}:
                raise InputError("invalid Jev decision")
            if reason == "uncertain" and action != "review":
                raise InputError("uncertainty must require review")
            p = decision.get("probabilities")
            confidence = decision.get("confidence")
            if not isinstance(p, dict) or set(p) != known or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p.values()) or not math.isclose(sum(p.values()), 1, abs_tol=1e-8) or type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise InputError("invalid recorded probability distribution")
            if (decision.get("outcome") == "route") != (decision.get("skill_id") in labels) or (decision.get("outcome") == "no_skill" and decision.get("skill_id") is not None) or (decision.get("outcome") == "review" and decision.get("skill_id") is not None):
                raise InputError("invalid route skill")
            maximum = max(p.values())
            if reason == "model_choice":
                choice = decision["skill_id"] if action not in ("no_skill", "review") else "__" + action + "__"
                if p[choice] < maximum - 1e-9 or (action not in ("no_skill", "review") and
                                                  (confidence < 0.55 or p[choice] < 0.55)):
                    raise InputError("recorded choice contradicts frozen router policy")
            elif action != "review" or not any(p[skill] >= maximum - 1e-9 and
                                                (confidence < 0.55 or p[skill] < 0.55) for skill in labels):
                raise InputError("uncertain review contradicts frozen router policy")
        else:
            raise InputError("record must declare a Jev or API error decision")


def score(observations, cases):
    expected = {case["id"]: case["expected"] for case in cases}
    counters = Counter()
    times = []
    for row in observations:
        d = row["decision"]
        target = expected[row["id"]]
        predicted = d["skill_id"] if d["outcome"] == "route" else d["outcome"]
        valid = d["source"] == "jev"
        counters["exact"] += int(valid and target == predicted)
        counters["skill_correct"] += int(valid and target == predicted and target not in ("review", "no_skill"))
        counters["wrong_routes"] += int(d["outcome"] == "route" and predicted != target)
        counters["unnecessary_reviews"] += int(valid and predicted == "review" and target != "review")
        counters["valid_reviews"] += int(valid and predicted == "review")
        counters["automatic_routes"] += int(predicted not in ("review", "no_skill"))
        counters["no_skill_answers"] += int(valid and predicted == "no_skill")
        counters["api_errors"] += int(not valid)
        counters["invalid_responses"] += int(d["reason"] in ("api_invalid_response", "api_model_mismatch"))
        times.append(row["latency_ms"])
    ordered = sorted(times)
    def percentile(p):
        pos = (len(ordered) - 1) * p
        low = int(pos)
        return round(ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (pos - low), 3)
    return {"observations": len(observations), "api_attempts": sum(r["decision"]["usage"]["requests"] for r in observations),
            "api_error_rate": counters["api_errors"] / len(observations),
            "expected_skill": sum(c["expected"] not in ("review", "no_skill") for c in cases) * (len(observations) // len(cases)),
            "expected_review": sum(c["expected"] == "review" for c in cases) * (len(observations) // len(cases)),
            "expected_no_skill": sum(c["expected"] == "no_skill" for c in cases) * (len(observations) // len(cases)),
            **dict(sorted(counters.items())), "latency_ms_p50": percentile(0.5), "latency_ms_p95": percentile(0.95)}


def replay(live_path, ordinary_path):
    cases = [json.loads(line) for line in read_pinned(DATA / "known-120.jsonl", DATASET_SHA).splitlines() if line.strip()]
    metadata = json.loads(read_pinned(DATA / "metadata.json", METADATA_SHA))
    ordinary = [json.loads(line) for line in read_pinned(DATA / "ordinary-6.jsonl", ORDINARY_SHA).splitlines() if line.strip()]
    catalogue = catalogue_from(json.loads(read_pinned(ROOT / "data/catalogue.json", CATALOGUE_SHA)))
    read_pinned(ROOT / "router.py", ROUTER_SHA)
    settings = {"model": "jev-1.13.0", "router_sha256": ROUTER_SHA, "catalogue_sha256": CATALOGUE_SHA}
    if hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest() != CONFIG_SHA:
        raise InputError("frozen runtime configuration changed")
    labels = {skill["id"] for skill in catalogue}
    family_counts = Counter(v["family"] for v in metadata.values())
    languages = Counter(language for item in metadata.values() for language in item["strata"] if language in ("en", "pt"))
    if (len(cases) != 120 or len(ordinary) != 6 or set(metadata) != {c["id"] for c in cases}
            or len(family_counts) != 60 or set(family_counts.values()) != {2}
            or languages != {"en": 60, "pt": 60}
            or Counter(c["expected"] == "review" for c in cases) != {False: 96, True: 24}
            or any(c["expected"] not in labels | {"review"} for c in cases)
            or any(c["expected"] != "no_skill" for c in ordinary)):
        raise InputError("pinned dataset or family inventory is invalid")
    if live_path.resolve() == (DATA / "live-360.jsonl").resolve():
        read_pinned(live_path, LIVE_SHA)
    if ordinary_path.resolve() == (DATA / "ordinary-6-results.jsonl").resolve():
        read_pinned(ordinary_path, ORDINARY_RESULTS_SHA)
    live, sanity = rows(live_path), rows(ordinary_path)
    verify(live, cases, labels, 3)
    verify(sanity, ordinary, labels, 1)
    total = score(live, cases)
    per_repeat = [score([r for r in live if r["repeat"] == i], cases) for i in range(1, 4)]
    families = sorted({item["family"] for item in metadata.values()})
    expected = {case["id"]: case["expected"] for case in cases}
    exact_by_family = [sum(r["decision"]["source"] == "jev" and
                           (r["decision"]["skill_id"] if r["decision"]["outcome"] == "route" else r["decision"]["outcome"]) == expected[r["id"]]
                           for r in live if metadata[r["id"]]["family"] == family) for family in families]
    changing = sum(any(len({r["decision"]["skill_id"] if r["decision"]["outcome"] == "route" else
                            r["decision"]["reason"] if r["decision"]["source"] == "api" else r["decision"]["outcome"]
                            for r in live if r["id"] == case["id"]}) > 1
                       for case in cases if metadata[case["id"]]["family"] == family) for family in families)
    rng = random.Random(20261003)
    sampled = sorted(sum(exact_by_family[rng.randrange(len(families))] for _ in families) / len(live) for _ in range(10000))
    lexical = [route(case["request"], catalogue, dry_run=True) for case in cases]
    lexical_exact = sum((d["skill_id"] if d["outcome"] == "route" else d["outcome"]) == c["expected"] for c, d in zip(cases, lexical))
    usages = [r["decision"]["usage"] for r in live]
    known_input = sum(u["input_tokens"] for u in usages if u["input_tokens"] is not None)
    known_output = sum(u["output_tokens"] for u in usages if u["output_tokens"] is not None)
    complete = all(u["input_tokens"] is not None and u["output_tokens"] is not None for u in usages)
    return {"runtime_commit": "37a05e2ad3edb145f47ccaffdbc151c5b37856d0", "model": "jev-1.13.0",
            "corpus_sha256": DATASET_SHA, "metadata_sha256": METADATA_SHA,
            "router_sha256": ROUTER_SHA, "catalogue_sha256": CATALOGUE_SHA, "config_sha256": CONFIG_SHA,
            "live": total, "repeats": per_repeat, "ordinary_controls": score(sanity, ordinary),
            "lexical_same_120": {"exact": lexical_exact, "observations": 120, "description": "weak token-overlap comparator, not a best-free baseline"},
            "family_variability": {"families": len(families), "families_with_changing_case": changing,
                                   "bootstrap_seed": 20261003, "bootstrap_draws": 10000,
                                   "exact_rate_95_percentile_interval": [sampled[250], sampled[9749]]},
            "usage": {"known_input_tokens": known_input, "known_output_tokens": known_output,
                      "unknown_usage_observations": sum(u["input_tokens"] is None or u["output_tokens"] is None for u in usages),
                      "complete": complete, "published_input_rate_usd_per_million": INPUT_USD_PER_MILLION,
                      "input_only_usd": round(known_input * INPUT_USD_PER_MILLION / 1_000_000, 12) if complete else None,
                      "known_input_usd_lower_bound": round(known_input * INPUT_USD_PER_MILLION / 1_000_000, 12),
                      "total_provider_cost_usd": None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, default=DATA / "live-360.jsonl")
    parser.add_argument("--ordinary", type=Path, default=DATA / "ordinary-6-results.jsonl")
    args = parser.parse_args()
    try:
        print(json.dumps(replay(args.live, args.ordinary), indent=2))
    except (InputError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Replay rejected: {error}\n")


if __name__ == "__main__":
    main()
