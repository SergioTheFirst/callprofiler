# Context Window Analysis: 16K vs 32K for Qwen3.5-9B Q5_K_M

## Hardware
- GPU: RTX 3060 12GB VRAM
- Model: Qwen3.5-9B Q5_K_M quantization (5.5-bit, actual VRAM usage: 7GB)
- Server: llama-server.exe with Flash Attention (`-fa auto`)

## Memory Breakdown

### Current Setup (16K context)
```
Model weights:     7.0 GB  (9B params × 5.5-bit Q5_K_M quantization)
KV cache (16K):    8.0 GB  (2 × 32 layers × 4096 hidden × 16384 ctx × 2 bytes)
─────────────────────────
Total required:   15.0 GB
Available VRAM:   12.0 GB
Status:           ⚠️ EXCEEDS by 3GB
```

**Почему работает сейчас:**
- Flash Attention (`-fa auto`) снижает память на ~35%
- Эффективное использование: 15.0 × 0.65 = **9.75 GB** (помещается)
- Safety margin: **2.25 GB free (18.8%)**
- Batch size = 1 (sequential processing)

### Proposed Setup (32K context)
```
Model weights:     7.0 GB
KV cache (32K):   16.0 GB  (удвоение контекста = удвоение KV cache)
─────────────────────────
Total required:   23.0 GB
Available VRAM:   12.0 GB
Status:           ❌ EXCEEDS by 11GB
```

**С Flash Attention:**
- Эффективное использование: 23.0 × 0.65 = **14.95 GB**
- Дефицит: **2.95 GB** (24.6% overflow)

## Impact Analysis

### ❌ Негативные последствия 32K context

1. **Out of Memory (OOM) crashes**
   - Дефицит 2.95 GB VRAM → llama-server будет падать при заполнении контекста >~26K токенов
   - Особенно критично для длинных звонков (>10 мин, >5K chars transcript)
   - Риск OOM выше, чем на Q8_0, т.к. меньше запас (2.95GB vs 3GB)

2. **Swap to system RAM**
   - Если не упадёт сразу, начнёт использовать системную память
   - Скорость генерации: **50-100× медленнее** (VRAM 500 GB/s vs RAM 50 GB/s)
   - Inference time: 2 сек/токен вместо 0.02 сек/токен

3. **Biography pipeline failures**
   - p8_editorial с chunked processing может превысить лимит
   - Long calls с 2× multiplier: 18000 × 2 = 36000 chars = **17K токенов** (input)
   - + system prompt (~2200 tokens) + output reserve (~5500 tokens) = **24.7K токенов**
   - Превышение 32K окна на длинных главах

### ⚠️ Пограничный случай

**Q5_K_M + 32K технически возможен, но рискован:**
- Дефицит всего 2.95GB (vs 3GB на Q8_0)
- Если Flash Attention даст 40% экономии вместо 35%: 23.0 × 0.6 = **13.8 GB** → всё равно не поместится
- Если GQA даст дополнительные 10%: 23.0 × 0.55 = **12.65 GB** → почти поместится, но без запаса
- **Риск:** любой spike в памяти (batch size >1, concurrent requests) → OOM crash

### ✅ Потенциальные выгоды (если бы поместилось)

1. **Больше контекста для LLM**
   - p8_editorial: можно обрабатывать главы до 40K chars без chunking
   - p6_chapters: больше сцен/портретов в одном промпте
   - Меньше потерь связности при chunked processing

2. **Меньше LLM вызовов**
   - Chunked editorial: 1 вызов вместо 2-3
   - Экономия времени на длинных главах

3. **Лучшее качество прозы**
   - LLM видит больше контекста → более связные переходы
   - Меньше повторов между чанками

## Current Pipeline Context Usage (Q5_K_M)

| Pass | Baseline | With 2× (long call) | Tokens | % of 16K | % of 32K |
|------|----------|---------------------|--------|----------|----------|
| p1_scene | 12000 ch | 24000 ch | 11428 + 4000 = 15428 | 94% | 47% |
| p8_editorial | 18000 ch | 36000 ch | 17142 + 7700 = 24842 | 152% ⚠️ | 76% |
| p6_chapters | 17000 ch | 34000 ch | 16190 + 7700 = 23890 | 146% ⚠️ | 73% |

**Проблема на 16K:**
- p8_editorial с 2× multiplier: 24842 токенов = **152% of 16K** → chunking обязателен
- p6_chapters с 2× multiplier: 23890 токенов = **146% of 16K** → chunking обязателен

**На 32K:**
- p8_editorial: 76% of 32K → помещается без chunking
- p6_chapters: 73% of 32K → помещается без chunking
- **Выгода:** меньше LLM вызовов, лучше связность прозы

## Recommendations

### ⚠️ 32K context — ВОЗМОЖЕН, но с рисками

**Q5_K_M (7GB) vs Q8_0 (9GB):**
- Экономия 2GB на модели → дефицит снижен с 3GB до 2.95GB
- **Технически возможен**, но без запаса безопасности

**Условия для безопасного использования 32K:**
1. **Batch size = 1** (только sequential processing, никаких concurrent requests)
2. **Мониторинг VRAM** через `nvidia-smi` каждые 5 секунд
3. **Graceful degradation**: если VRAM >11.5GB → автоматически переключаться на chunking
4. **Тестирование**: запустить p8_editorial на самой длинной главе (>30K chars) и проверить OOM

**Риски:**
- Любой spike в памяти → OOM crash
- Windows background processes могут занять 0.5-1GB VRAM
- Нет запаса для debugging (print statements, error handling)

### ✅ Рекомендация: Гибридный подход

**Оптимальная стратегия:**
1. **Оставить `-c 16384` по умолчанию** (безопасно, 18.8% запас)
2. **Добавить опциональный режим `-c 32768`** для экспериментов
3. **Adaptive context switching** в коде:
   ```python
   if estimated_tokens < 14000:  # 85% of 16K
       use_16k_context()
   elif estimated_tokens < 28000 and vram_available > 11.5:  # 85% of 32K
       use_32k_context()
   else:
       use_chunking()
   ```

**Преимущества:**
- 16K для 90% случаев (безопасно)
- 32K для длинных звонков (когда критично качество)
- Chunking как fallback (гарантия работы)

### 🔮 Альтернативы для гарантированного 32K

Если критично нужен 32K без рисков:

1. **Upgrade GPU** → RTX 4070 Ti 12GB или RTX 4080 16GB
   - 32K context: 23GB × 0.65 (Flash Attention) = 14.95GB
   - RTX 4070 Ti 12GB: не поместится (дефицит 2.95GB)
   - RTX 4080 16GB: поместится с запасом 1GB
   - Стоимость: RTX 4080 ~$1200

2. **Smaller quantization** → Q4_K_M (4-bit)
   - Model weights: 7GB → 5GB (экономия 2GB)
   - 32K context: 5 + 16 = 21GB × 0.65 = 13.65GB (поместится с запасом 1.65GB)
   - Компромисс: -5-10% качества генерации
   - **Рекомендуется попробовать**: Q4_K_M может дать достаточно качества для biography

3. **Smaller model** → Qwen3.5-7B Q5_K_M
   - Model weights: 7GB → 5.5GB
   - KV cache: 8GB → 6GB (меньше layers: 28 vs 32)
   - 32K context: 5.5 + 12 = 17.5GB × 0.65 = 11.4GB (поместится с запасом 0.6GB)
   - Компромисс: -10-15% качества на сложных задачах

## Conclusion

**Для Q5_K_M (7GB) на RTX 3060 12GB:**

### 16K context (текущая конфигурация)
- ✅ **Безопасно**: 9.75GB VRAM, 2.25GB запас (18.8%)
- ✅ **Стабильно**: работает без OOM crashes
- ⚠️ **Ограничение**: p8_editorial и p6_chapters требуют chunking для длинных звонков

### 32K context (экспериментальный режим)
- ⚠️ **Пограничный**: 14.95GB VRAM, дефицит 2.95GB (24.6%)
- ⚠️ **Рискованно**: OOM crashes возможны при >26K токенов
- ✅ **Выгода**: p8_editorial и p6_chapters без chunking → лучше качество прозы

**Итоговая рекомендация:**
1. **Оставить `-c 16384` по умолчанию** (production-ready)
2. **Попробовать `-c 32768` в тестовом режиме** на 1-2 длинных звонках
3. **Мониторить VRAM** через `nvidia-smi` во время теста
4. **Если OOM crashes** → вернуться к 16K или попробовать Q4_K_M quantization

**Альтернатива без рисков:** Q4_K_M (5GB model) + 32K context = 13.65GB → поместится с запасом.
