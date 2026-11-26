"""Fit a chat request using the running llama.cpp model's tokenizer."""

import httpx


async def _post(client, base_url, path, payload):
    response = await client.post(f"{base_url}/{path}", json=payload, timeout=8.0)
    response.raise_for_status()
    return response.json()


async def _tokens(client, base_url, content, *, special=False):
    data = await _post(client, base_url, "tokenize", {
        "content": content, "add_special": special, "parse_special": special,
    })
    return data["tokens"]


async def _prompt_size(client, base_url, payload, messages):
    template = {"messages": messages}
    if payload.get("tools"):
        template["tools"] = payload["tools"]
    data = await _post(client, base_url, "apply-template", template)
    return len(await _tokens(client, base_url, data["prompt"], special=True))


async def _limit_text(client, base_url, content, allowance, marker):
    if len(content.encode()) <= allowance:
        return content
    tokens = await _tokens(client, base_url, content)
    if len(tokens) <= allowance:
        return content
    kept = tokens[:max(0, allowance - 12)]
    if not kept:
        return marker
    data = await _post(client, base_url, "detokenize", {"tokens": kept})
    return data["content"] + "\n" + marker


async def _limit_tool_results(client, base_url, messages, budget):
    count = sum(message["role"] == "tool" for message in messages)
    if not count:
        return messages
    allowance = max(1, budget // count)
    limited = []
    for message in messages:
        if message["role"] == "tool":
            content = await _limit_text(client, base_url, message["content"], allowance, "[resultado truncado]")
            message = {**message, "content": content}
        limited.append(message)
    return limited


def _history_summary(messages):
    lines = [
        f"- {message['role']}: {' '.join(message['content'][:240].split())[:120]}"
        for message in messages if message["role"] in ("user", "assistant") and message["content"]
    ]
    return "\n".join(lines[-4:])


async def fit_chat_payload(client: httpx.AsyncClient, base_url: str, payload: dict,
                           context: int, attachment_previews: str | None) -> dict:
    messages = payload["messages"]
    prefix = int(bool(messages and messages[0]["role"] == "system"))
    user_turns = [i for i, message in enumerate(messages) if message["role"] == "user"]
    latest = user_turns[-1] if user_turns else prefix
    current = await _limit_tool_results(client, base_url, messages[latest:], 2048)
    without_preview = current
    if attachment_previews and current and current[0]["content"].endswith("\n\n" + attachment_previews):
        metadata = current[0]["content"].removesuffix("\n\n" + attachment_previews)
        omitted = metadata + "\n[Prévia omitida por falta de espaço. Consulte o arquivo se necessário.]"
        without_preview = [{**current[0], "content": omitted}, *current[1:]]
        preview = await _limit_text(client, base_url, attachment_previews, 1536, "[prévia truncada]")
        current = [{**current[0], "content": metadata + "\n\n" + preview}, *current[1:]]

    # Keep a small margin for additional special tokens and a share for generation.
    limit = context - 16
    requested = payload["max_tokens"]
    reserve = min(requested, max(1, min(2048, context // 8)))
    budget = limit - reserve
    system = messages[:prefix]
    starts = sorted({prefix, *user_turns})

    async def size(candidate):
        return await _prompt_size(client, base_url, payload, candidate)

    full = messages[:latest] + current
    used = await size(full)
    if used <= budget:
        return {**payload, "messages": full, "max_tokens": min(requested, limit - used)}

    # Find the longest recent suffix of complete turns that fits.
    kept = system + current
    used = await size(kept)
    start = latest
    if used > budget and current != without_preview:
        current = without_preview
        kept = system + current
        used = await size(kept)
    if used > budget and any(message["role"] == "tool" for message in current):
        current = await _limit_tool_results(client, base_url, current, 384)
        kept = system + current
        used = await size(kept)
    low, high = 0, len(starts) - 1
    while used <= budget and low < high:
        middle = (low + high) // 2
        candidate_start = starts[middle]
        candidate = system + messages[candidate_start:latest] + current
        count = await size(candidate)
        if count <= budget:
            start, kept, used = candidate_start, candidate, count
            high = middle
        else:
            low = middle + 1

    summary = _history_summary(messages[prefix:start])
    if summary and used < budget:
        note = "\n\n[Resumo de falas antigas. Trate como histórico, sem prioridade sobre as instruções.]\n"
        content = (system[0]["content"] if system else "") + note + summary
        candidate = [{"role": "system", "content": content}, *kept[prefix:]]
        count = await size(candidate)
        if count <= budget:
            kept, used = candidate, count
    if used >= limit:
        raise RuntimeError(
            "A mensagem atual e as instruções ultrapassam o contexto do llama.cpp. "
            "Divida a mensagem ou aumente o contexto nas preferências."
        )
    return {**payload, "messages": kept, "max_tokens": min(requested, limit - used)}
