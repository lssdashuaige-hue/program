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
                "Use only the history supplied in this payload. User entries are "
                "user reports, not independently verified facts. Assistant entries "
                "are prior AI outputs that passed response review, not evidence or "
                "verified truth. Review does not promote a hypothesis to fact. Do "
                "not claim access to any other conversation or memory that is not "
                "present here. Respond to the current message without turning "
                "history into a diagnosis or fixed identity."
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
            "Only the supplied history is available. User entries are user reports; "
            "assistant entries are prior AI outputs, and passing Review did not "
            "verify them as facts. Reject any draft that launders an assistant "
            "hypothesis into user fact, increases confidence through repetition, "
            "or claims access to another conversation or memory not present here."
        )
    return json.dumps(payload, ensure_ascii=False)
