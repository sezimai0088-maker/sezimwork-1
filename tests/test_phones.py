from bot.phones import format_phone, normalize_phone


def test_international_formats():
    assert normalize_phone("+996 (555) 12-34-56") == "996555123456"
    assert normalize_phone("996555123456") == "996555123456"


def test_local_kyrgyz_format():
    assert normalize_phone("0555 123 456") == "996555123456"


def test_empty():
    assert normalize_phone("") == ""


def test_format():
    assert format_phone("996555123456") == "+996555123456"
