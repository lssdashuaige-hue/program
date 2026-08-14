import json
from dataclasses import dataclass
from typing import Literal, Sequence


ConversationRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ConversationContextMessage:
    role: ConversationRole
    content: str


def reflection_input(
    user_message: str,
    conversation_history: Sequence[ConversationContextMessage],
) -> str:
    if not conversation_history:
        return user_message
    return json.dumps(
        {
            "conversation_history": [
                {"role": item.role, "content": item.content}
                for item in conversation_history
            ],
            "current_user_message": user_message,
            "instruction": (
                "Use the history only as prior reviewed context. Respond to the "
                "current user message and do not claim that history is a diagnosis "
                "or a fixed truth about the user."
            ),
        },
        ensure_ascii=False,
    )


def review_input(
    user_message: str,
    reflection_draft: str,
    conversation_history: Sequence[ConversationContextMessage],
) -> str:
    payload: dict[str, object] = {
        "current_user_message": user_message,
        "reflection_draft": reflection_draft,
    }
    if conversation_history:
        payload["conversation_history"] = [
            {"role": item.role, "content": item.content}
            for item in conversation_history
        ]
        payload["history_boundary"] = (
            "History is prior reviewed context only. Evaluate the draft against "
            "the current message and PAS constraints; do not treat history as a "
            "diagnosis or fixed truth."
        )
    return json.dumps(payload, ensure_ascii=False)
