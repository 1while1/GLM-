from glm_grabber.state import GrabberState, classify_signals


def test_payment_handoff_has_highest_priority():
    state = classify_signals(
        {
            "payment": True,
            "captcha": True,
            "login": True,
            "request_in_flight": True,
        }
    )

    assert state == GrabberState.PAYMENT_HANDOFF


def test_captcha_pauses_before_login_and_ready():
    state = classify_signals({"captcha": True, "login": True, "target_ready": True})

    assert state == GrabberState.CAPTCHA_REQUIRED


def test_target_mismatch_blocks_clicking():
    state = classify_signals({"target_mismatch": True, "target_ready": True})

    assert state == GrabberState.TARGET_MISMATCH


def test_ready_requires_confirmed_target_without_inflight():
    state = classify_signals({"target_ready": True, "button_enabled": True})

    assert state == GrabberState.READY


def test_unknown_when_no_decisive_signal():
    state = classify_signals({"button_enabled": True})

    assert state == GrabberState.UNKNOWN
