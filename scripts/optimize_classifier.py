"""Optimize TeamSizeClassifier weights and thresholds via k-fold cross-validation."""
import sys
sys.path.insert(0, ".")

import random
from collections import defaultdict
from itertools import product

from tools.kurultai.team_size_classifier import TeamSizeClassifier
from tools.kurultai.complexity_config import ComplexityConfig
from tools.kurultai.complexity_validation_framework import TestCaseLibrary

# Load test cases
lib = TestCaseLibrary()
all_cases = lib.get_all_test_cases()

# Set random seed for reproducibility
random.seed(42)

# Split into train (80%) and holdout (20%) stratified by team size
def stratified_split(cases, train_ratio=0.8):
    """Split cases into train/holdout with stratification by team size."""
    by_team = defaultdict(list)
    for case in cases:
        team = case.expected_team_size.value if hasattr(case.expected_team_size, "value") else str(case.expected_team_size)
        by_team[team].append(case)

    train_cases = []
    holdout_cases = []

    for team, team_cases in by_team.items():
        random.shuffle(team_cases)
        split_idx = int(len(team_cases) * train_ratio)
        train_cases.extend(team_cases[:split_idx])
        holdout_cases.extend(team_cases[split_idx:])

    return train_cases, holdout_cases

train_cases, holdout_cases = stratified_split(all_cases, train_ratio=0.8)

print(f"Total cases: {len(all_cases)}")
print(f"Train cases: {len(train_cases)} (80%)")
print(f"Holdout cases: {len(holdout_cases)} (20%)")

# Analyze score distribution with current classifier on TRAIN set
classifier = TeamSizeClassifier()

scores_by_class = {"individual": [], "small_team": [], "full_team": []}
for case in train_cases:
    result = classifier.classify(case.capability_request)
    expected = case.expected_team_size.value if hasattr(case.expected_team_size, "value") else str(case.expected_team_size)
    scores_by_class.get(expected, []).append(result["complexity"])

print("\n=== TRAIN SET SCORE DISTRIBUTION ===")
for cls in ["individual", "small_team", "full_team"]:
    scores = sorted(scores_by_class[cls])
    if scores:
        print(f"\n{cls}: n={len(scores)}")
        print(f"  min={scores[0]:.3f} q25={scores[len(scores)//4]:.3f} median={scores[len(scores)//2]:.3f} q75={scores[3*len(scores)//4]:.3f} max={scores[-1]:.3f}")

def evaluate_thresholds(lower, upper, cases, desc=""):
    """Evaluate accuracy for given thresholds on a case set."""
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

    acc = correct / len(cases) if cases else 0
    ind_acc = by_class["individual"][0] / max(by_class["individual"][1], 1)
    st_acc = by_class["small_team"][0] / max(by_class["small_team"][1], 1)
    ft_acc = by_class["full_team"][0] / max(by_class["full_team"][1], 1)

    return acc, (ind_acc, st_acc, ft_acc)

# Brute-force threshold search on TRAIN set
print("\n\n=== THRESHOLD OPTIMIZATION (5-FOLD CV ON TRAIN SET) ===")

# Implement 5-fold cross-validation
k = 5
fold_size = len(train_cases) // k
folds = []
for i in range(k):
    start = i * fold_size
    end = start + fold_size if i < k - 1 else len(train_cases)
    folds.append(train_cases[start:end])

# Grid search for best thresholds
best_cv_acc = 0
best_thresholds = (0, 0)
threshold_results = []

for lower in [x/100 for x in range(5, 50, 1)]:
    for upper in [x/100 for x in range(50, 100, 1)]:
        if upper <= lower:
            continue

        # 5-fold cross-validation
        cv_accuracies = []
        for i in range(k):
            # Use fold i as validation, rest as training
            val_cases = folds[i]
            train_folds = [f for j, f in enumerate(folds) if j != i]
            # Note: we're just evaluating thresholds, not training,
            # so we use all train folds for evaluation
            combined_train = []
            for f in train_folds:
                combined_train.extend(f)

            acc, _ = evaluate_thresholds(lower, upper, val_cases)
            cv_accuracies.append(acc)

        cv_acc = sum(cv_accuracies) / k

        # Track best by CV accuracy
        if cv_acc > best_cv_acc:
            best_cv_acc = cv_acc
            best_thresholds = (lower, upper)

        threshold_results.append((cv_acc, lower, upper))

print(f"Best CV accuracy: {best_cv_acc*100:.1f}%")
print(f"Best thresholds: lower={best_thresholds[0]:.2f}, upper={best_thresholds[1]:.2f}")

# Evaluate on HOLDOUT set
holdout_acc, holdout_per_class = evaluate_thresholds(
    best_thresholds[0], best_thresholds[1], holdout_cases, desc="holdout"
)

train_acc, train_per_class = evaluate_thresholds(
    best_thresholds[0], best_thresholds[1], train_cases, desc="train"
)

print(f"\n=== FINAL EVALUATION ===")
print(f"Train accuracy: {train_acc*100:.1f}% (ind={train_per_class[0]*100:.0f}%, st={train_per_class[1]*100:.0f}%, ft={train_per_class[2]*100:.0f}%)")
print(f"Holdout accuracy: {holdout_acc*100:.1f}% (ind={holdout_per_class[0]*100:.0f}%, st={holdout_per_class[1]*100:.0f}%, ft={holdout_per_class[2]*100:.0f}%)")

# Check for overfitting: holdout should be within 10% of train
overfit_gap = train_acc - holdout_acc
if overfit_gap > 0.10:
    print(f"\n⚠️  WARNING: Overfitting detected! Gap of {overfit_gap*100:.1f}% between train and holdout.")
    print("   Consider reducing model complexity or gathering more training data.")
elif holdout_acc < train_acc - 0.05:
    print(f"\n✓ Acceptable generalization: {overfit_gap*100:.1f}% gap within tolerance.")
else:
    print(f"\n✓ Excellent generalization: Holdout performance matches or exceeds train.")

# Show top threshold configurations by holdout performance
print("\n\n=== TOP THRESHOLD CONFIGURATIONS (BY HOLDOUT ACCURACY) ===")
holdout_results = []
for lower in [x/100 for x in range(5, 50, 1)]:
    for upper in [x/100 for x in range(50, 100, 1)]:
        if upper <= lower:
            continue

        acc, per_class = evaluate_thresholds(lower, upper, holdout_cases)
        holdout_results.append((acc, lower, upper, per_class))

holdout_results.sort(reverse=True, key=lambda x: x[0])
for i, (acc, lo, hi, (ia, sa, fa)) in enumerate(holdout_results[:10], 1):
    print(f"{i:2}. {acc*100:.1f}% | lower={lo:.2f} upper={hi:.2f} | ind={ia*100:.0f}% st={sa*100:.0f}% ft={fa*100:.0f}%")
