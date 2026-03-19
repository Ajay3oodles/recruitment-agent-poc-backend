"""
chatbot/services/prompt_builder.py

All LLM prompts live here.
Nothing else — no API calls, no DB, just prompt strings.
"""


def build_chat_prompt(query: str, context: str, history: str) -> str:
    """
    System prompt for the main chat — answer + summary in one call.
    """
    return (
        "You are the official virtual assistant for Ontario Tech University. "
        "Help prospective students with questions about admissions, programs, "
        "campus life, fees, housing, and university services.\n\n"

        "Rules:\n"
        "- Answer ONLY using the retrieved CMS content below.\n"
        "- Be concise and friendly — under 150 words unless listing specifics.\n"
        "- If the content does not answer the question, say so honestly and "
        "suggest contacting the relevant department.\n"
        "- Always end the answer with the relevant source page title.\n\n"

        "You must respond in this EXACT JSON format with no extra text outside it:\n"
        "{\n"
        '  "answer": "your answer to the student here",\n'
        '  "summary": "1-2 sentence summary of the full conversation so far '
        'including this exchange"\n'
        "}\n\n"
        "IMPORTANT: Output ONLY the JSON object. No intro text, no explanation, nothing before or after the {{ }}.\n\n"
        f"Retrieved content from Ontario Tech University website:\n\n{context}"
        f"{history}"
    )


def build_context(pages: list) -> str:
    """
    Convert retrieved CMS pages into a context string for the prompt.
    """
    if not pages:
        return "No relevant content found."

    return "\n\n---\n\n".join(
        f"**Page: {p.title}**\nURL: {p.url}\n{p.content}"
        for p in pages
    )


def build_history(previous_messages: list[dict]) -> str:
    """
    Convert previous chat messages into a conversation history string.

    previous_messages = [
        {"role": "user", "message": "What is tuition?"},
        {"role": "bot",  "message": "Tuition is $54,320..."},
    ]
    """
    if not previous_messages:
        return ""

    lines = "\n".join(
        f"{'Student' if m['role'] == 'user' else 'Assistant'}: {m['message']}"
        for m in previous_messages
    )
    return f"\n\nConversation so far:\n{lines}"