from app.pipeline.text_ur import assess_transcript, clean_roman, has_repetition, normalize_urdu, replace_words


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


def test_replace_words_matches_whole_words_only():
    assert replace_words("یہ کام کامیاب ہے۔", "کام", "کاج") == ("یہ کاج کامیاب ہے۔", 1)
    assert replace_words("bohotsa", "bohot", "bohat") == ("bohotsa", 0)
    assert replace_words("bohotsa", "bohot", "bohat", whole_word=False) == ("bohatsa", 1)


def test_replace_words_ignore_case_keeps_a_leading_capital():
    assert replace_words("Bohot bohot achha.", "bohot", "bohat", ignore_case=True) == ("Bohat bohat achha.", 2)
    assert replace_words("Bohot achha.", "bohot", "bohat") == ("Bohot achha.", 0)


def test_replace_words_punctuation_and_deletion():
    assert replace_words("وہ گیا۔ وہ آیا۔", "۔", "؟") == ("وہ گیا؟ وہ آیا؟", 2)
    assert replace_words("Haan ji theek hai", "ji", "") == ("Haan  theek hai", 1)  # the API tidies the spaces
    assert replace_words("anything", "", "x") == ("anything", 0)
