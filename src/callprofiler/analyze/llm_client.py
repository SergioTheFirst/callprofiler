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

import requests

logger = logging.getLogger(__name__)


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
        print(response)  # JSON строка или текст ответа
    """

    def __init__(self, base_url: str, timeout: int = 300) -> None:
        """Инициализировать LLM клиент.

        Параметры:
            base_url  — URL endpoint (обычно http://127.0.0.1:8080/v1/chat/completions)
            timeout   — timeout для запроса в секундах (по умолчанию 300)
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

    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Отправить сообщения в LLM и получить ответ.

        Параметры:
            messages     — список сообщений в формате OpenAI API
                          [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            temperature  — параметр температуры (0.0-2.0), по умолчанию 0.3 для консистентного JSON
            max_tokens   — максимальное число токенов в ответе

        Возвращает:
            Полный ответ модели (текст или JSON)

        Raises:
            RuntimeError  — если запрос к серверу упал
        """
        logger.debug(
            "Отправка промпта в LLM сервер (сообщений: %d, max_tokens: %d)",
            len(messages), max_tokens,
        )

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
                # OpenAI API format: response["choices"][0]["message"]["content"]
                return result["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError) as exc:
                raise RuntimeError(
                    f"Невалидный ответ от LLM сервера: {response.text[:200]}"
                ) from exc

        except requests.Timeout as exc:
            raise RuntimeError(
                f"Timeout при запросе к LLM серверу (timeout={self.timeout}s): {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Ошибка при запросе к LLM серверу: {exc}") from exc


# Для обратной совместимости (если что-то ещё использует OllamaClient)
OllamaClient = LLMClient
