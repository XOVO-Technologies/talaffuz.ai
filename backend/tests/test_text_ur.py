from app.pipeline.text_ur import assess_transcript, clean_roman, has_repetition, normalize_urdu


def test_spec_examples_are_unchanged():
    for s in ("کیا حال ہے؟ میں ابھی دفتر پہنچا ہوں۔", "آپ کہاں جا رہے ہیں؟", "مجھے یہ کام آج مکمل کرنا ہے۔"):
        assert normalize_urdu(s) == s


def test_arabic_letter_forms_and_punctuation():
    assert normalize_urdu("كيا حال هے?") == "کیا حال ہے؟"
    assert normalize_urdu("آپ کہاں ہیں,  ٹھیک ہیں") == "آپ کہاں ہیں، ٹھیک ہیں۔"


def test_diacritics_zero_width_and_pipe_removed():
    assert normalize_urdu("مَیں​ ٹھیک | ہوں") == "میں ٹھیک ہوں۔"


def test_latin_full_stop_becomes_urdu_stop_but_decimals_survive():
    assert normalize_urdu("وہ گیا.") == "وہ گیا۔"
    assert "3.5" in normalize_urdu("قیمت 3.5 ہے")


def test_terminal_mark_optional():
    assert normalize_urdu("وہ گیا", ensure_terminal=False) == "وہ گیا"


def test_clean_roman_has_no_pipe_or_newline():
    assert clean_roman("Kya  haal\nhai |?") == "Kya haal hai ?"


def test_repetition_detected():
    assert has_repetition("شکریہ شکریہ شکریہ شکریہ")
    assert not has_repetition("آپ کہاں جا رہے ہیں؟")


def test_assess_flags():
    flags, reject = assess_transcript("", 3.0, None, None)
    assert flags == ["empty"] and reject
    flags, reject = assess_transcript("hello there how are you", 3.0, -0.2, 0.1)
    assert "not_urdu_script" in flags and not reject
    flags, reject = assess_transcript("آپ کہاں جا رہے ہیں؟", 2.0, -1.5, 0.9)
    assert "maybe_not_speech" in flags and reject
