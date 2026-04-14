"""
bulk — модули для массовой обработки данных.

Включает:
- loader.py: массовая загрузка .txt транскриптов в БД
- name_extractor.py: извлечение имён собеседников из транскриптов
"""

from callprofiler.bulk.loader import bulk_load

__all__ = ["bulk_load"]
