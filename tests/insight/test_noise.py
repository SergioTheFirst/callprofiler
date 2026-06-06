from callprofiler.insight.synth.noise import inject_asr_noise


def test_zero_rate_is_identity():
    s = "привет как дела наверное завтра позвоню"
    assert inject_asr_noise(s, rate=0.0, seed=1) == s


def test_noise_changes_text_but_keeps_length_ballpark():
    s = "привет как дела наверное завтра позвоню договорились хорошо"
    out = inject_asr_noise(s, rate=0.5, seed=1)
    assert out != s
    # длина слов сохраняется в пределах разумного (дроп частиц)
    assert abs(len(out.split()) - len(s.split())) <= len(s.split())


def test_deterministic_with_seed():
    s = "одна две три четыре пять шесть семь"
    assert inject_asr_noise(s, 0.3, seed=7) == inject_asr_noise(s, 0.3, seed=7)
