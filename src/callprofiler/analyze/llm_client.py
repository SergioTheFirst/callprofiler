# -*- coding: utf-8 -*-
"""
llm_client.py — клиент Ollama для локального LLM анализа.

Используется для отправки промптов на локально запущенный Ollama
и получения ответов (обычно Qwen 2.5 14B или аналогичная модель).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OllamaClient:
    """Клиент для взаимодействия с локальным Ollama сервером.

    Ollama должен быть запущен и доступен по адресу base_url (обычно http://localhost:11434).

    Использование:
        client = OllamaClient(base_url="http://localhost:11434", model="qwen2.5:14b-instruct-q4_K_M")
        response = client.generate(prompt="Анализируй стенограмму...")
        print(response)  # JSON строка или текст ответа
    """

    def __init__(self, base_url: str, model: str, timeout: int = 300) -> None:
        """Инициализировать Ollama клиент.

        Параметры:
            base_url  — URL базового сервера Ollama (например, http://localhost:11434)
            model     — название модели (например, "qwen2.5:14b-instruct-q4_K_M")
            timeout   — timeout для запроса в секундах (по умолчанию 300 для больших моделей)
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._verify_connection()

    def _verify_connection(self) -> None:
        """Проверить что Ollama доступен при инициализации.

        Raises:
            ConnectionError  — если Ollama недоступен
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            response.raise_for_status()
            logger.info("✓ Ollama доступен на %s", self.base_url)
        except requests.ConnectionError as exc:
            raise ConnectionError(
                f"Не удаётся подключиться к Ollama на {self.base_url}. "
                f"Убедитесь что Ollama запущен: ollama serve"
            ) from exc
        except requests.RequestException as exc:
            logger.warning("Предупреждение при проверке Ollama: %s", exc)

    def generate(self, prompt: str, stream: bool = False) -> str:
        """Отправить промпт в LLM и получить ответ.

        Параметры:
            prompt  — промпт для анализа
            stream  — если True, поточный режим (для больших ответов)

        Возвращает:
            Полный ответ модели (текст или JSON)

        Raises:
            RuntimeError  — если запрос к Ollama упал
        """
        logger.debug(
            "Отправка промпта в Ollama (модель: %s, длина: %d)",
            self.model, len(prompt),
        )

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": stream,
                    "temperature": 0.3,  # Низкая температура для консистентного JSON
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            if stream:
                # Собрать потоковый ответ
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            full_response += chunk.get("response", "")
                        except json.JSONDecodeError:
                            logger.warning("Невалидный JSON в потоке: %s", line)
                            continue
                return full_response
            else:
                # Обычный ответ
                try:
                    result = response.json()
                    return result.get("response", "")
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Ollama вернул невалидный JSON: {response.text[:200]}"
                    ) from exc

        except requests.Timeout as exc:
            raise RuntimeError(
                f"Timeout при запросе к Ollama (timeout={self.timeout}s): {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Ошибка при запросе к Ollama: {exc}") from exc

    def list_models(self) -> list[str]:
        """Получить список доступных моделей на сервере.

        Возвращает:
            Список имён моделей

        Raises:
            RuntimeError  — если запрос упал
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            logger.debug("Доступные модели на Ollama: %s", models)
            return models
        except requests.RequestException as exc:
            raise RuntimeError(f"Ошибка при получении списка моделей: {exc}") from exc
