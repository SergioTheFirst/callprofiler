# LLM Rules

- Server: llama-server at http://127.0.0.1:8080/v1/chat/completions (OpenAI format)
- Use requests.post() directly. No openai SDK. No Ollama API.
- Prompt template: configs/prompts/analyze_v001.txt
- prompt_version field in analyses tracks which version produced result
- JSON parsing: strip markdown fences → extract {…} → fix truncated → dict.get(key, default)
- If parse fails completely: save raw_llm, return Analysis with defaults, mark as partial
- Timeout: 120 seconds per request
- Roles in transcript: [me]=owner, [s2]=other. Roles may be swapped.
- "Сергей/Серёжа/Серёж/Медведев" = ALWAYS owner regardless of label.
- Max input: if transcript > 3000 chars → first 1500 + "[...]" + last 1500
