from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder


EXPLAIN_WITH_CONTEXT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are an assistant that augments a bot's tabular response with a brief, human-friendly explanation. "
            "You will receive the full conversation as chat messages, and the LAST human message includes the backend JSON payload. "
            "Carefully read that JSON (it can contain keys like caption, responseType, data.columns, data.values, etc.). "
            "Write a concise explanation (2-4 sentences) highlighting key insights. "
            "Do not invent values; only summarize what is present."
        ),
    ),
    MessagesPlaceholder(variable_name="messages"),
])


TTS_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are an assistant that rewrites long or complex text into a short, natural-sounding summary "
            "ideal for text-to-speech (TTS). Keep it 2-4 sentences, plain spoken English, no markdown, "
            "no bullet points, no tables, no URLs, and avoid numbers unless crucial. Focus on the big picture."
        ),
    ),
    (
        "human",
        (
            "Rewrite the following for TTS so it's easy to listen to. Keep it concise and conversational.\n\n"
            "Original text:\n{original}"
        ),
    ),
])


BACKCHANNEL_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You write brief, natural-sounding status updates while a long-running request executes. "
            "Constraints: 10-20 words, conversational, reassuring; no emojis/markdown/URLs/tables. "
            "CRITICAL: Each new update MUST be materially different from all previous ones and feel like real human progress. "
            "Do NOT paraphrase earlier lines. Make it consequential: reflect advancing steps, checks in progress, "
            "what you're focusing on now, or what you will confirm next. Reference the user's question/topic when helpful."
        ),
    ),
    (
        "human",
        (
            "User question: {question}\n\n"
            "Previously sent updates (do not repeat or rephrase):\n{history}\n\n"
            "Write ONE new, consequential status line now (just the sentence)."
        ),
    ),
])

