#!/usr/bin/env python3
"""Run engagement outcome inference for active humans."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engagement_learner import infer_outcomes
from consent_decorator import get_active_humans_with_consent

# Only process humans who consented to message_analysis
human_ids = get_active_humans_with_consent("message_analysis")
for hid in human_ids[:50]:
    infer_outcomes(hid)
