import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Mapping, Sequence


ConversationRole = Literal["user", "assistant"]
ResponsePreference = Literal[
    "listen",
    "organize",
    "explore_causes",
    "next_step",
]


RESPONSE_PREFERENCE_GUIDANCE: Final[Mapping[ResponsePreference, str]] = (
    MappingProxyType(
        {
            "listen": (
                "Make space and reflect only what is explicitly present. Prefer "
                "listening and one gentle invitation over analysis, causal "
                "explanation, or action advice."
            ),
            "organize": (
                "Help organize the user's own material. Clearly separate what "
                "they stated, feelings or needs they directly expressed, and "
                "what remains unknown; do not add a theory."
            ),
            "explore_causes": (
                "Offer at most two grounded, tentative, and correctable possible "
                "explanations. Label them as possibilities and invite correction; "
                "do not diagnose or turn correlation into a single cause."
            ),
            "next_step": (
                "Offer one small, reversible, user-controlled next step that "
                "follows from what the user said. Avoid pressure and do not "
                "present it as treatment."
            ),
        }
    )
)


_RESPONSE_PREFERENCE_BOUNDARY: Final[str] = (
    "This preference is a soft, single-turn response-shaping hint supplied "
    "separately from the user's message. It is not user-authored content, "
    "evidence, a fact, a diagnosis, or permission to infer missing details. "
    "Never quote it as something the user said or treat it as material for "
    "conversation history, a title, or memory. It must not weaken safety, health, "
    "source, or Review requirements; those requirements take priority."
)


@dataclass(frozen=True)
class ConversationContextMessage:
    role: ConversationRole
    content: str


def reflection_input(
    user_message: str,
    conversation_history: Sequence[ConversationContextMessage],
    response_preference: ResponsePreference | None = None,
) -> str:
    if not conversation_history and response_preference is None:
        return user_message
    payload: dict[str, object] = {
        "current_user_message": user_message,
    }
    if conversation_history:
        payload.update(
            {
                "conversation_history": [
                    {"role": item.role, "content": item.content}
                    for item in conversation_history
                ],
                "instruction": (
                    "Use only the history supplied in this payload. User entries "
                    "are user reports, not independently verified facts. Assistant "
                    "entries are prior AI outputs that passed response review, not "
                    "evidence or verified truth. Review does not promote a "
                    "hypothesis to fact. Do not claim access to any other "
                    "conversation or memory that is not present here. Respond to "
                    "the current message without turning history into a diagnosis "
                    "or fixed identity."
                ),
            }
        )
    if response_preference is not None:
        payload.update(
            {
                "response_preference": response_preference,
                "response_preference_guidance": (
                    RESPONSE_PREFERENCE_GUIDANCE[response_preference]
                ),
                "response_preference_boundary": _RESPONSE_PREFERENCE_BOUNDARY,
            }
        )
    return json.dumps(payload, ensure_ascii=False)


def review_input(
    user_message: str,
    reflection_draft: str,
    conversation_history: Sequence[ConversationContextMessage],
    response_preference: ResponsePreference | None = None,
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
    if response_preference is not None:
        payload.update(
            {
                "response_preference": response_preference,
                "response_preference_guidance": (
                    RESPONSE_PREFERENCE_GUIDANCE[response_preference]
                ),
                "response_preference_boundary": _RESPONSE_PREFERENCE_BOUNDARY,
                "review_instruction": (
                    "Check the preference only as a soft style target. Reject or "
                    "rewrite any draft that uses it to invent user facts, overstate "
                    "causes, diagnose, reduce safety support, or bypass PAS rules."
                ),
            }
        )
    return json.dumps(payload, ensure_ascii=False)
