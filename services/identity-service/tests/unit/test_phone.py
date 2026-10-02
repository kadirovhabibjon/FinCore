import pytest

from app.core.phone import InvalidPhoneError, normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "+998901234567",
        "998901234567",
        "+998 90 123 45 67",
        "+998 (90) 123-45-67",
        "90 123 45 67",
        "901234567",
        "00998901234567",
        "  +998901234567  ",
    ],
)
def test_every_way_of_writing_an_uzbek_number_is_one_number(raw: str) -> None:
    assert normalize_phone(raw) == "+998901234567"


def test_other_countries_keep_their_code() -> None:
    assert normalize_phone("+7 912 345 67 89") == "+79123456789"
    assert normalize_phone("+1 (415) 555-0100") == "+14155550100"


@pytest.mark.parametrize(
    "raw", ["", "abc", "12345", "+99890123456", "+9989012345678", "1234567890123456"]
)
def test_impossible_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)
