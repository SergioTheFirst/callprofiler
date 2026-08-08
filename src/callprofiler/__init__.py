# -*- coding: utf-8 -*-
"""callprofiler package.

Намеренно НЕ импортирует torch на уровне пакета — иначе любой
``import callprofiler.*`` (включая ``--help``/``doctor``) тянет ML-стек.
torch 2.6 weights_only-патч живёт в ``callprofiler.torch_patch`` и
применяется точечно в runner'ах при загрузке чекпоинтов (T-01).
"""
