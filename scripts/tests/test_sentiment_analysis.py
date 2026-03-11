#!/usr/bin/env python3
"""
Test script for enhanced sentiment analysis in conversation_logger.py

Tests various message types to verify:
- Emotion detection (excited, frustrated, curious, neutral)
- Urgency levels (high, medium, low)
- Politeness classification (formal, casual, terse)
- Intensity scoring (0.0 to 1.0)
- Polarity detection (positive, negative, neutral)
"""

import sys
from pathlib import Path

# Add parent directory to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from conversation_logger import ConversationLogger

def test_sentiment_analysis():
    """Run comprehensive tests on sentiment analysis."""

    logger = ConversationLogger()

    test_cases = [
        # Test emotions
        {
            "name": "Excited - High Intensity",
            "message": "This is absolutely amazing! I love the new feature, it's fantastic and wonderful! Great work!",
            "expected": {"emotion": "excited", "polarity": "positive", "urgency": "low"}
        },
        {
            "name": "Frustrated - High Urgency",
            "message": "This is broken! I keep getting errors and it's terrible. This is a critical problem that needs to be fixed immediately!",
            "expected": {"emotion": "frustrated", "polarity": "negative", "urgency": "high"}
        },
        {
            "name": "Curious - Low Intensity",
            "message": "I was wondering how this works? What's the best approach? I'm confused about the implementation.",
            "expected": {"emotion": "curious", "polarity": "neutral"}
        },
        {
            "name": "Neutral - No strong emotion",
            "message": "The meeting is scheduled for tomorrow at 3pm. Please bring your laptop.",
            "expected": {"emotion": "neutral", "polarity": "neutral", "urgency": "low"}
        },

        # Test urgency levels
        {
            "name": "High Urgency",
            "message": "This is an emergency! We need to fix this ASAP, it's urgent and critical!",
            "expected": {"urgency": "high"}
        },
        {
            "name": "Medium Urgency",
            "message": "Can you handle this soon? It's important and should be a priority.",
            "expected": {"urgency": "medium"}
        },
        {
            "name": "Low Urgency",
            "message": "When you have time, could you look at this? No rush.",
            "expected": {"urgency": "low"}
        },

        # Test politeness
        {
            "name": "Formal Politeness",
            "message": "I would appreciate if you could kindly review this request. Thank you for your assistance.",
            "expected": {"politeness": "formal"}
        },
        {
            "name": "Casual Politeness",
            "message": "Thanks! That's awesome and cool. Got it, no worries!",
            "expected": {"politeness": "casual"}
        },
        {
            "name": "Terse/Direct",
            "message": "Fix the error. Update the config. Deploy the changes.",
            "expected": {"politeness": "terse"}
        },

        # Test intensity scoring
        {
            "name": "High Intensity",
            "message": "This is amazing wonderful fantastic brilliant perfect excellent! I love it great awesome!",
            "expected": {"intensity_gt": 0.5}
        },
        {
            "name": "Low Intensity",
            "message": "This looks good. Thanks for the help.",
            "expected": {"intensity_lt": 0.3}
        },

        # Test polarity
        {
            "name": "Positive Polarity",
            "message": "Great work! I love the improvements. Excellent job on this feature!",
            "expected": {"polarity": "positive"}
        },
        {
            "name": "Negative Polarity",
            "message": "This is bad. It's broken and has errors. I'm frustrated with these issues.",
            "expected": {"polarity": "negative"}
        },
        {
            "name": "Neutral Polarity",
            "message": "The file is located in the config directory. You can find it there.",
            "expected": {"polarity": "neutral"}
        },

        # Mixed scenarios
        {
            "name": "Frustrated + Formal + High Urgency",
            "message": "I would appreciate if you could kindly address this critical error immediately. This is a significant issue.",
            "expected": {"emotion": "frustrated", "politeness": "formal", "urgency": "high"}
        },
        {
            "name": "Excited + Casual + Low Urgency",
            "message": "Thanks! This is awesome and great work! Really happy with the results.",
            "expected": {"emotion": "excited", "politeness": "casual", "urgency": "low"}
        },
    ]

    print("=" * 80)
    print("ENHANCED SENTIMENT ANALYSIS TEST RESULTS")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print(f"Message: {test['message'][:80]}{'...' if len(test['message']) > 80 else ''}")
        print()

        result = logger._analyze_sentiment(test['message'])

        print("Result:")
        print(f"  Polarity:  {result['polarity']}")
        print(f"  Emotion:   {result['emotion']}")
        print(f"  Urgency:   {result['urgency']}")
        print(f"  Intensity: {result['intensity']}")
        print(f"  Politeness: {result['politeness']}")

        # Validate against expectations
        test_passed = True
        expected = test.get('expected', {})

        if 'polarity' in expected and result['polarity'] != expected['polarity']:
            print(f"  ❌ Polarity mismatch: expected {expected['polarity']}")
            test_passed = False

        if 'emotion' in expected and result['emotion'] != expected['emotion']:
            print(f"  ❌ Emotion mismatch: expected {expected['emotion']}")
            test_passed = False

        if 'urgency' in expected and result['urgency'] != expected['urgency']:
            print(f"  ❌ Urgency mismatch: expected {expected['urgency']}")
            test_passed = False

        if 'politeness' in expected and result['politeness'] != expected['politeness']:
            print(f"  ❌ Politeness mismatch: expected {expected['politeness']}")
            test_passed = False

        if 'intensity_gt' in expected and result['intensity'] <= expected['intensity_gt']:
            print(f"  ❌ Intensity too low: expected > {expected['intensity_gt']}")
            test_passed = False

        if 'intensity_lt' in expected and result['intensity'] >= expected['intensity_lt']:
            print(f"  ❌ Intensity too high: expected < {expected['intensity_lt']}")
            test_passed = False

        if test_passed:
            print(f"  ✓ PASS")
            passed += 1
        else:
            print(f"  ✗ FAIL")
            failed += 1

        print()

    print("=" * 80)
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    # Additional validation: Check return type
    print("\nValidating return type structure...")
    sample = logger._analyze_sentiment("Test message")
    required_keys = {'polarity', 'emotion', 'urgency', 'intensity', 'politeness'}

    if required_keys.issubset(sample.keys()):
        print("✓ All required keys present in return dict")
        print(f"  Keys: {', '.join(required_keys)}")
    else:
        print("✗ Missing required keys!")
        print(f"  Expected: {required_keys}")
        print(f"  Got: {set(sample.keys())}")

    # Validate data types
    type_checks = [
        ('polarity', str),
        ('emotion', str),
        ('urgency', str),
        ('intensity', (int, float)),
        ('politeness', str)
    ]

    print("\nValidating data types...")
    all_types_correct = True
    for key, expected_type in type_checks:
        if not isinstance(sample[key], expected_type):
            print(f"✗ {key} has wrong type: expected {expected_type}, got {type(sample[key])}")
            all_types_correct = False
        else:
            print(f"✓ {key}: {type(sample[key]).__name__}")

    if all_types_correct:
        print("\n✓ All data types correct")

    print("\n" + "=" * 80)
    return failed == 0

if __name__ == "__main__":
    success = test_sentiment_analysis()
    sys.exit(0 if success else 1)
