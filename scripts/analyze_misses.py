"""Analyze misclassified test cases to guide classifier tuning."""
import sys
sys.path.insert(0, ".")

from collections import Counter
from tools.kurultai.team_size_classifier import TeamSizeClassifier
from tools.kurultai.complexity_config import DEFAULT_CONFIG
from tools.kurultai.complexity_validation_framework import TestCaseLibrary

classifier = TeamSizeClassifier()
lib = TestCaseLibrary()
cases = lib.get_all_test_cases()

misses = []
correct = 0
by_class = {"individual": [0, 0], "small_team": [0, 0], "full_team": [0, 0]}

for case in cases:
    result = classifier.classify(case.capability_request)
    predicted = result["team_size"]
    expected = case.expected_team_size.value if hasattr(case.expected_team_size, "value") else str(case.expected_team_size)

    if expected in by_class:
        by_class[expected][1] += 1

    if predicted != expected:
        misses.append({
            "id": case.id,
            "text": case.capability_request[:120],
            "expected": expected,
            "predicted": predicted,
            "score": round(result["complexity"], 3),
            "factors": {k: round(v, 3) for k, v in result["factors"].items() if v > 0.01}
        })
    else:
        correct += 1
        if expected in by_class:
            by_class[expected][0] += 1

total = len(cases)
print(f"Total cases: {total}")
print(f"Correct: {correct} ({100*correct/total:.1f}%)")
print(f"Misclassified: {len(misses)}")
print()

for cls, (c, t) in by_class.items():
    print(f"  {cls}: {c}/{t} correct ({100*c/t:.1f}%)" if t > 0 else f"  {cls}: no cases")
print()

by_expected = Counter()
for m in misses:
    by_expected[m["expected"]] += 1
print("Misses by expected class:", dict(by_expected))
print()

print("=" * 100)
print("MISCLASSIFIED CASES (sorted by expected class, then score):")
print("=" * 100)

for m in sorted(misses, key=lambda x: (x["expected"], x["score"])):
    print(f'\n[{m["expected"]} -> {m["predicted"]}] score={m["score"]}')
    print(f'  Text: {m["text"]}')
    print(f'  Factors: {m["factors"]}')
