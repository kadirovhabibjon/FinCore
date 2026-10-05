from fincore_common import generate_card_number, is_valid_card_number, normalize_card_number
from fincore_common.card_number import _luhn_check_digit


def test_luhn_check_digit_matches_the_textbook_example() -> None:
    # 7992739871 -> check digit 3 is the standard worked example.
    assert _luhn_check_digit("7992739871") == "3"


def test_generated_numbers_are_valid_and_differ() -> None:
    numbers = {generate_card_number() for _ in range(200)}
    assert len(numbers) == 200
    assert all(len(n) == 16 and n.startswith("9955") and is_valid_card_number(n) for n in numbers)


def test_a_mistyped_or_swapped_digit_is_caught() -> None:
    number = generate_card_number()
    wrong_digit = number[:10] + str((int(number[10]) + 1) % 10) + number[11:]
    assert not is_valid_card_number(wrong_digit)
    a, b = number[8], number[9]
    if a != b and {a, b} != {"0", "9"}:  # the one swap Luhn cannot see
        assert not is_valid_card_number(number[:8] + b + a + number[10:])


def test_rejects_anything_that_is_not_a_fincore_number() -> None:
    assert not is_valid_card_number("")
    assert not is_valid_card_number("4111111111111111")  # valid Luhn, someone else's range
    assert not is_valid_card_number(generate_card_number()[:-1])
    assert not is_valid_card_number("9955abcd12345678")
    assert not is_valid_card_number("９９５５" + "0" * 12)  # non-ASCII digits


def test_normalize_drops_spaces_and_dashes() -> None:
    assert normalize_card_number("9955 1234-5678 9012") == "9955123456789012"
