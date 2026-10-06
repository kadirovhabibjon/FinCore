import pytest

from app.services.devices import describe_device, device_signature


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36",
            "Chrome on Linux",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0 "
            "Safari/537.36 Edg/147.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 19_1 like Mac OS X) AppleWebKit/605.1.15 "
            "Version/19.1 Mobile/15E148 Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36 Chrome/147.0 "
            "Mobile Safari/537.36",
            "Chrome on Android",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 15.6; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Firefox on Mac",
        ),
        ("python-httpx/0.28.1", "an unrecognised device or app"),
        (None, "an unrecognised device or app"),
    ],
)
def test_a_user_agent_is_described_the_way_a_person_would(agent: str | None, expected: str) -> None:
    assert describe_device(agent) == expected


def test_a_browser_update_is_the_same_device_but_another_browser_is_not() -> None:
    chrome = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36"
    updated = chrome.replace("147.0.0.0", "148.0.7.1")
    firefox = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"

    assert device_signature(chrome) == device_signature(updated)
    assert device_signature(chrome) != device_signature(firefox)
    assert device_signature(None) == device_signature("") == ""
