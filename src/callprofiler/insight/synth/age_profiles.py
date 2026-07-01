# -*- coding: utf-8 -*-
"""Ground-truth возрастные шаблоны для синт-корпуса (Ф1 плана age.md).

Самодостаточные мини-словари для генерации реплик speaker='OTHER' с заданной
стилевой статистикой (Т1/Т2/Л1/Л2/Ч6/MATTR, vozrast.md §3.11), независимые от
production-лексиконов age_style/lexicons/ (Ф2) — не создают Ф1↔Ф2 циклическую
зависимость. Направления слов — из vozrast.md §3.1/§3.8 дословно (примеры).
"""
from dataclasses import dataclass

GROUP_RANGES = (
    ("G1", 0, 17), ("G2", 18, 25), ("G3", 26, 35),
    ("G4", 36, 45), ("G5", 46, 60), ("G6", 60, 200),
)


def group_for_age(age: int) -> str:
    for code, lo, hi in GROUP_RANGES:
        if lo <= age <= hi:
            return code
    return "G6" if age > 200 else "G1"


@dataclass(frozen=True)
class AgeStyleTemplate:
    group: str
    life_stage_words: tuple     # Т1 — «своя» лексика жизненного этапа
    realia_words: tuple         # Т2 — поколенческие реалии (может быть пустым)
    slang_words: tuple          # Л1 — молодёжный сленг
    archaism_words: tuple       # Л2 — архаизмы/советизмы
    long_words: tuple           # Ч6 — длинные/книжные (4+ слога)
    vocab_pool: tuple           # Р3/Р4 — нейтральный пул (размер = разнообразие)
    slang_density: float
    archaism_density: float
    long_word_ratio: float

    def sample_other_text(self, rng, n_words: int = 60) -> str:
        """Одна OTHER-реплика с заданной статистикой (детерминирована по rng)."""
        words = list(rng.choice(self.life_stage_words,
                                size=min(4, len(self.life_stage_words))))
        if self.realia_words:
            words += list(rng.choice(self.realia_words,
                                     size=min(2, len(self.realia_words))))
        while len(words) < n_words:
            r = rng.random()
            if r < self.slang_density and self.slang_words:
                words.append(rng.choice(self.slang_words))
            elif r < self.slang_density + self.archaism_density and self.archaism_words:
                words.append(rng.choice(self.archaism_words))
            elif rng.random() < self.long_word_ratio:
                words.append(rng.choice(self.long_words))
            else:
                words.append(rng.choice(self.vocab_pool))
        idx = rng.permutation(len(words))
        return " ".join(str(words[i]) for i in idx)


AGE_TEMPLATES: dict[str, AgeStyleTemplate] = {
    "G1": AgeStyleTemplate(
        "G1", ("школа", "ЕГЭ", "уроки", "продлёнка", "класс"),
        ("тикток", "скибиди", "реролл"),
        ("кринж", "краш", "зашквар", "чил", "рофл", "вайб", "база"), (),
        ("образование", "дополнительно"),
        ("школа", "учитель", "урок", "друзья", "игра", "телефон", "видео", "музыка"),
        slang_density=0.35, archaism_density=0.0, long_word_ratio=0.05,
    ),
    "G2": AgeStyleTemplate(
        "G2", ("универ", "сессия", "общага", "диплом", "стипендия"),
        ("тикток", "твич", "аниме"),
        ("кринж", "краш", "чил", "рофл", "вайб", "база", "изи"), (),
        ("образование", "обязательно", "действительно", "университет"),
        ("пара", "препод", "экзамен", "друзья", "работа", "подработка", "квартира", "город"),
        slang_density=0.30, archaism_density=0.0, long_word_ratio=0.10,
    ),
    "G3": AgeStyleTemplate(
        "G3", ("первая работа", "съём", "права", "ипотека"),
        (),
        ("кринж", "чил"), (),
        ("ответственность", "обязательство"),
        ("работа", "проект", "встреча", "банк", "квартира", "машина", "отпуск", "планы", "бюджет"),
        slang_density=0.08, archaism_density=0.0, long_word_ratio=0.15,
    ),
    "G4": AgeStyleTemplate(
        "G4", ("ипотека", "декрет", "садик", "карьера", "совещание"),
        ("денди", "сега", "аська"),
        (), ("сберкнижка",),
        ("ответственность", "обязательство", "совещание", "руководство", "дополнительно"),
        ("работа", "проект", "ипотека", "дети", "садик", "школа", "ремонт", "отпуск", "планирование"),
        slang_density=0.0, archaism_density=0.05, long_word_ratio=0.30,
    ),
    "G5": AgeStyleTemplate(
        "G5", ("дача", "здоровье", "диспансеризация", "внуки", "огород"),
        ("кассета", "видеомагнитофон"),
        (), ("давеча", "аккурат", "талоны"),
        ("диспансеризация", "обязательно", "действительно", "ответственность"),
        ("дача", "огород", "здоровье", "врач", "дети", "внуки", "соседи", "сад", "урожай"),
        slang_density=0.0, archaism_density=0.12, long_word_ratio=0.35,
    ),
    "G6": AgeStyleTemplate(
        "G6", ("пенсия", "внуки", "поликлиника", "огород", "сериалы"),
        ("дискотека", "кассета", "пейджер", "перестройка", "талоны"),
        (), ("давеча", "аккурат", "оное", "сберкнижка", "партком"),
        ("действительно", "обязательно", "дополнительно", "поликлиника", "ответственность"),
        ("пенсия", "внуки", "огород", "поликлиника", "сериал", "сосед", "дача", "здоровье", "память"),
        slang_density=0.0, archaism_density=0.22, long_word_ratio=0.40,
    ),
}
