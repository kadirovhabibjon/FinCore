from app.domain.fraud_check import FraudDecision
from app.services.rules import decide


def test_zero_score_is_allow() -> None:
    assert decide(0) == FraudDecision.ALLOW


def test_score_just_under_review_threshold_is_allow() -> None:
    assert decide(39) == FraudDecision.ALLOW


def test_score_at_review_threshold_is_review() -> None:
    assert decide(40) == FraudDecision.REVIEW


def test_score_just_under_block_threshold_is_review() -> None:
    assert decide(69) == FraudDecision.REVIEW


def test_score_at_block_threshold_is_block() -> None:
    assert decide(70) == FraudDecision.BLOCK


def test_a_very_high_score_is_still_block() -> None:
    assert decide(1000) == FraudDecision.BLOCK
