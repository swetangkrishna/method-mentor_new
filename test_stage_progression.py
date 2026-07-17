#!/usr/bin/env python3
"""Deterministic regression tests for Stage 1-3 progression; no LLM/GPU needed."""
from stage_tracker import StageTracker


def reply(tracker, text):
    before = tracker.current_stage
    tracker.scan_student_parameters(before, text)
    tracker.advance_after_student_reply()
    return before, tracker.current_stage


def test_stage1_uncertain_method_advances():
    t = StageTracker()
    before, after = reply(t, "I want to understand why students use AI for essays, but I do not know which method to use.")
    assert before == 1 and after == 2, (before, after, t.summary())


def test_stage1_named_method_advances():
    t = StageTracker()
    before, after = reply(t, 'My research question is why students use AI, and I am considering a survey.')
    assert before == 1 and after == 2, (before, after, t.summary())


def test_stage2_requires_all_three_answers():
    t = StageTracker(); reply(t, 'I study student AI use and I am not sure which method to use.')
    assert t.current_stage == 2
    reply(t, "I am a full-time master's student in my first year.")
    assert t.current_stage == 2
    reply(t, 'I prefer qualitative methods.')
    assert t.current_stage == 2
    reply(t, 'Because I have used interviews before and I am familiar with qualitative analysis.')
    assert t.current_stage == 3, t.summary()


if __name__ == '__main__':
    test_stage1_uncertain_method_advances()
    test_stage1_named_method_advances()
    test_stage2_requires_all_three_answers()
    print('All stage-progression tests passed.')
