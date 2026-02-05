"""Optimize TeamSizeClassifier weights and thresholds via brute-force search."""
import sys
sys.path.insert(0, ".")

from itertools import product
from tools.kurultai.team_size_classifier import TeamSizeClassifier
from tools.kurultai.complexity_config import ComplexityConfig
from tools.kurultai.complexity_validation_framework import TestCaseLibrary

lib = TestCaseLibrary()
cases = lib.get_all_test_cases()

print(f"Loaded {len(cases)} test cases")

# First: analyze score distribution with current classifier
classifier = TeamSizeClassifier()
scores_by_class = {"individual": [], "small_team": [], "full_team": []}
for case in cases:
    result = classifier.classify(case.capability_request)
    expected = case.expected_team_size.value if hasattr(case.expected_team_size, "value") else str(case.expected_team_size)
    scores_by_class.get(expected, []).append(result["complexity"])

for cls in ["individual", "small_team", "full_team"]:
    scores = sorted(scores_by_class[cls])
    print(f"\n{cls}: n={len(scores)}")
    print(f"  min={scores[0]:.3f} q25={scores[len(scores)//4]:.3f} median={scores[len(scores)//2]:.3f} q75={scores[3*len(scores)//4]:.3f} max={scores[-1]:.3f}")

# Brute-force threshold search
print("\n\n=== THRESHOLD OPTIMIZATION ===")
best_acc = 0
best_thresholds = (0, 0)

for lower in [x/100 for x in range(5, 50, 1)]:
    for upper in [x/100 for x in range(50, 100, 1)]:
        if upper <= lower:
            continue
        config = ComplexityConfig(individual_threshold=lower, small_team_threshold=upper)

        correct = 0
        by_class = {"individual": [0, 0], "small_team": [0, 0], "full_team": [0, 0]}

        for case in cases:
            result = classifier.classify(case.capability_request)
            score = result["complexity"]
            expected = case.expected_team_size.value if hasattr(case.expected_team_size, "value") else str(case.expected_team_size)

            if score < lower:
                predicted = "individual"
            elif score < upper:
                predicted = "small_team"
            else:
                predicted = "full_team"

            by_class.get(expected, ["?", 0])[1] += 1
            if predicted == expected:
                correct += 1
                by_class.get(expected, [0, "?"])[0] += 1

        acc = correct / len(cases)

        # Check per-class constraints
        ind_acc = by_class["individual"][0] / max(by_class["individual"][1], 1)
        st_acc = by_class["small_team"][0] / max(by_class["small_team"][1], 1)
        ft_acc = by_class["full_team"][0] / max(by_class["full_team"][1], 1)

        if acc > best_acc:
            best_acc = acc
            best_thresholds = (lower, upper)
            best_per_class = (ind_acc, st_acc, ft_acc)

print(f"Best accuracy: {best_acc*100:.1f}%")
print(f"Best thresholds: lower={best_thresholds[0]:.2f}, upper={best_thresholds[1]:.2f}")
print(f"Per-class: individual={best_per_class[0]*100:.1f}%, small_team={best_per_class[1]*100:.1f}%, full_team={best_per_class[2]*100:.1f}%")

# Show top 10 threshold configs
print("\n\n=== TOP THRESHOLD CONFIGURATIONS ===")
results = []
for lower in [x/100 for x in range(5, 50, 1)]:
    for upper in [x/100 for x in range(50, 100, 1)]:
        if upper <= lower:
            continue
        config = ComplexityConfig(individual_threshold=lower, small_team_threshold=upper)

        correct = 0
        by_class = {"individual": [0, 0], "small_team": [0, 0], "full_team": [0, 0]}

        for case in cases:
            result = classifier.classify(case.capability_request)
            score = result["complexity"]
            expected = case.expected_team_size.value if hasattr(case.expected_team_size, "value") else str(case.expected_team_size)

            if score < lower:
                predicted = "individual"
            elif score < upper:
                predicted = "small_team"
            else:
                predicted = "full_team"

            by_class.get(expected, ["?", 0])[1] += 1
            if predicted == expected:
                correct += 1
                by_class.get(expected, [0, "?"])[0] += 1

        acc = correct / len(cases)
        ind_acc = by_class["individual"][0] / max(by_class["individual"][1], 1)
        st_acc = by_class["small_team"][0] / max(by_class["small_team"][1], 1)
        ft_acc = by_class["full_team"][0] / max(by_class["full_team"][1], 1)

        results.append((acc, lower, upper, ind_acc, st_acc, ft_acc))

results.sort(reverse=True)
for acc, lo, hi, ia, sa, fa in results[:15]:
    print(f"  {acc*100:.1f}% | lower={lo:.2f} upper={hi:.2f} | ind={ia*100:.0f}% st={sa*100:.0f}% ft={fa*100:.0f}%")
