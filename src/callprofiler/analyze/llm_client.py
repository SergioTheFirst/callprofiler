# -*- coding: utf-8 -*-
"""
llm_client.py — клиент для локального LLM (llama.cpp) с OpenAI-совместимым API.

Используется для отправки промптов на локально запущенный llama-server
и получения ответов в формате OpenAI API.

API endpoint: http://127.0.0.1:8080/v1/chat/completions
Формат совместим с OpenAI API, но без необходимости указывать модель.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResult:
    """Результат вызова LLM с метаданными завершения.

    ``finish_reason`` от llama-server: ``"stop"`` — модель закончила сама,
    ``"length"`` — упёрлась в ``max_tokens`` (вывод ОБРЕЗАН). Обрезку надо
    ловить: иначе теряются promises/facts (см. pipeline.md → output_truncated).
    """

    text: str | None
    finish_reason: str | None = None

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


class LLMClient:
    """Клиент для взаимодействия с локальным llama-server (llama.cpp).

    llama-server должен быть запущен с флагом -api для OpenAI-совместимого API.

    Использование:
        client = LLMClient(base_url="http://127.0.0.1:8080/v1/chat/completions")
        response = client.generate(
            messages=[
                {"role": "system", "content": "Ты анализируешь стенограммы"},
                {"role": "user", "content": "Проанализируй..."}
            ]
        )
        logger.debug(response)  # JSON строка или текст ответа
    """

    def __init__(self, base_url: str, timeout: int = 300) -> None:
        """Инициализировать LLM клиент.

        Параметры:
            base_url  — URL endpoint (обычно http://127.0.0.1:8080/v1/chat/completions)
            timeout   — timeout для запроса в секундах (по умолчанию 300 для длинных звонков)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._verify_connection()

    def _verify_connection(self) -> None:
        """Проверить что llama-server доступен при инициализации.

        Raises:
            ConnectionError  — если сервер недоступен
        """
        try:
            # Попытаться минимальный запрос
            response = requests.post(
                self.base_url,
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "temperature": 0.1,
                    "max_tokens": 10,
                },
                timeout=5,
            )
            response.raise_for_status()
            logger.info("✓ LLM сервер доступен на %s", self.base_url)
        except requests.ConnectionError as exc:
            raise ConnectionError(
                f"Не удаётся подключиться к llama-server на {self.base_url}. "
                f"Запустите: llama-server -api"
            ) from exc
        except requests.RequestException as exc:
            logger.warning("Предупреждение при проверке LLM сервера: %s", exc)

    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> LLMResult:
        """Отправить сообщения в LLM и вернуть текст + finish_reason.

        Параметры:
            messages     — список сообщений в формате OpenAI API
                          [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            temperature  — параметр температуры (0.0-2.0), по умолчанию 0.3 для консистентного JSON
            max_tokens   — максимальное число токенов в ответе (потолок, не цель)

        Возвращает:
            LLMResult(text, finish_reason). ``text=None`` при ошибке подключения
            или невалидном ответе. ``finish_reason="length"`` → вывод обрезан.
        """
        logger.debug(
            "Отправка промпта в LLM сервер (сообщений: %d, max_tokens: %d)",
            len(messages), max_tokens,
        )

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    self.base_url,
                    json={
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()

                try:
                    result = response.json()
                    # OpenAI API format: choices[0].message.content + finish_reason
                    choice = result["choices"][0]
                    content = choice["message"]["content"]
                    finish_reason = choice.get("finish_reason")
                    return LLMResult(text=content, finish_reason=finish_reason)
                except (json.JSONDecodeError, KeyError, IndexError):
                    logger.error("Невалидный ответ от LLM сервера: %s", response.text[:200])
                    return LLMResult(text=None)  # не ретраим: ответ пришёл, но невалидный JSON

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_exc = exc
                if attempt < 2:
                    delay = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    logger.warning(
                        "LLM недоступен (попытка %d/3), повтор через %ds: %s",
                        attempt + 1, delay, exc,
                    )
                    time.sleep(delay)
            except requests.RequestException as exc:
                logger.error("Ошибка при запросе к LLM серверу: %s", exc)
                return LLMResult(text=None)  # не ретраим: не transient error

        logger.error(
            "LLM недоступен после 3 попыток (timeout=%ds): %s", self.timeout, last_exc
        )
        return LLMResult(text=None)

    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> str | None:
        """Обратно-совместимая обёртка над :meth:`complete` — только текст ответа.

        Существующие вызовы (biography, graph и т.д.) продолжают получать
        ``str | None``. Новый код, которому нужен ``finish_reason``, зовёт
        :meth:`complete`.
        """
        return self.complete(messages, temperature, max_tokens).text


# Для обратной совместимости (если что-то ещё использует OllamaClient)
OllamaClient = LLMClient
