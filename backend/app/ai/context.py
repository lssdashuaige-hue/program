import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Mapping, Sequence

from app.ai.models import (
    BoundedResponseKind,
    SourceBasis,
    final_response_digest,
)


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


_BOUNDED_CANDIDATE_BOUNDARY: Final[str] = (
    "This candidate is a deterministic PAS boundary response, not model "
    "evidence or a release instruction. Audit it normally and independently. "
    "Release is allowed only when the exact candidate satisfies every source, "
    "health, and PAS boundary; do not rewrite it or treat its route tag as "
    "proof that it is safe."
)


_MIXED_CJK_LATIN_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:[\u3400-\u4dbf\u4e00-\u9fff][a-z]{1,8}"
    r"[\u3400-\u4dbf\u4e00-\u9fff]|"
    r"[a-z]{2,10}[\u3400-\u4dbf\u4e00-\u9fff])",
    re.IGNORECASE,
)
_MIXED_SCRIPT_REPAIR_BOUNDARY: Final[str] = (
    "The server detected a mixed CJK/Latin surface token. This is only a "
    "lexical-review hint, not proof of an intended correction or permission "
    "to infer content. If the candidate makes only the smallest obvious repair, "
    "preserves the user's reported states, leaves their relationship and cause "
    "unknown, and optionally allows correction, do not fail it merely for that "
    "repair. Ambiguous repairs or added facts, causes, mechanisms, bodily states, "
    "or attentional states must still be rejected."
)

_NAMED_GUESS_COUNT_BOUNDARY: Final[str] = (
    "Count only explanations, causes, mechanisms, or alternative domains that "
    "the assistant proposes in the candidate. Do not count states faithfully "
    "repeated from the current user message, the smallest obvious character or "
    "Chinese/pinyin lexical repair, or an explicit statement that the relation "
    "and cause remain unknown. Repeating several user-reported states without "
    "adding an explanation has named_guess_count=0. Any assistant-added causal "
    "or explanatory direction still counts even when tentative."
)

_REVIEW_DISPOSITION_BOUNDARY: Final[str] = (
    "Compare reflection_draft and final_response before choosing the disposition. "
    "accepted requires an unchanged final_response and an empty draft_findings "
    "list. rewritten requires at least one real draft finding and a materially "
    "changed final_response that repairs it. Do not mark a safe unchanged draft "
    "as rewritten merely because it was audited, and never change text while "
    "claiming accepted."
)


_BOUNDED_ROUTE_SEMANTICS: Final[Mapping[BoundedResponseKind, str]] = (
    MappingProxyType(
        {
            "personal_lifespan_conversion": (
                "For this route, a group-level methodological statement that "
                "population associations cannot determine one person's "
                "lifespan is general knowledge, not a fact about a concrete "
                "third person. A conditional reference to a generic qualified "
                "professional role is also not a fact about a concrete third "
                "person. This distinction does not make either statement true "
                "by itself: source attribution and every PAS check still apply. "
                "For the exact fixed candidate, record exactly "
                "current_user_message and general_knowledge as the used source "
                "bases, with zero named guesses. "
                "Claims about an identifiable person's knowledge, actions, "
                "history, motives, private state, or capacity remain third-party "
                "claims and must be rejected when unsupported."
            ),
            "single_chat_diagnostic_request": (
                "For this route, an open conditional about whether concern or "
                "relevant experience causes distress or practical impact does "
                "not assert that such impact already exists. A generic qualified "
                "professional role is not a fact about a concrete third person."
            ),
            "third_party_private_state": (
                "The fixed response must not infer a concrete third person's "
                "private state, diagnosis, history, motive, intention, or fixed "
                "capacity."
            ),
            "unavailable_cross_chat_context": (
                "For the exact fixed candidate, the correct structured value is "
                "cross_chat_boundary=satisfied, not violated: it explicitly "
                "denies access to other chats, asks for the relevant text or a "
                "summary to be supplied here, and refuses to rely on an absent "
                "conversation. Record exactly current_user_message and "
                "general_knowledge as the used source bases, with zero named "
                "guesses, health_boundary=not_applicable, and no diagnostic "
                "self-screening. This server-derived route is not release proof; "
                "a changed answer that claims access to, receipt of, memory of, "
                "or conclusions from unavailable material must still be rejected."
            ),
        }
    )
)


@dataclass(frozen=True)
class ConversationContextMessage:
    role: ConversationRole
    content: str


def available_review_source_bases(
    conversation_history: Sequence[ConversationContextMessage],
) -> tuple[SourceBasis, ...]:
    source_bases: list[SourceBasis] = ["current_user_message"]
    if any(item.role == "user" for item in conversation_history):
        source_bases.append("supplied_user_history")
    if any(item.role == "assistant" for item in conversation_history):
        source_bases.append("supplied_assistant_history_as_ai_output")
    return tuple(source_bases)


def permitted_review_source_bases(
    conversation_history: Sequence[ConversationContextMessage],
) -> tuple[SourceBasis, ...]:
    """Return the exact source-basis allowlist enforced after primary Review."""

    return (
        *available_review_source_bases(conversation_history),
        "tentative_inference",
        "general_knowledge",
    )


def review_input_surface_hints(user_message: str) -> tuple[str, ...]:
    """Return non-authoritative server surface hints for structured audit."""

    if _MIXED_CJK_LATIN_TOKEN_PATTERN.search(user_message) is not None:
        return ("mixed_cjk_latin_token",)
    return ()


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
    bounded_response_kind: BoundedResponseKind | None = None,
) -> str:
    source_manifest = available_review_source_bases(conversation_history)

    payload: dict[str, object] = {
        "current_user_message": user_message,
        "reflection_draft": reflection_draft,
        "history_present": bool(conversation_history),
        "source_manifest": list(source_manifest),
        "permitted_source_bases": list(
            permitted_review_source_bases(conversation_history)
        ),
        "review_disposition_boundary": _REVIEW_DISPOSITION_BOUNDARY,
        "named_guess_count_boundary": _NAMED_GUESS_COUNT_BOUNDARY,
        "source_manifest_boundary": (
            "This manifest lists every supplied conversational source. The draft "
            "is the audit target, not evidence. permitted_source_bases is the exact "
            "allowlist enforced after Review; tentative inference and general "
            "knowledge remain non-user sources and must keep their correct status. "
            "Do not claim or name any unavailable conversational source."
        ),
        "history_boundary": (
            "Only the supplied history is available. User entries are user reports; "
            "assistant entries are prior AI outputs, and passing Review did not "
            "verify them as facts. Reject any draft that launders an assistant "
            "hypothesis into user fact, increases confidence through repetition, "
            "or claims access to another conversation or memory not present here."
            if conversation_history
            else "No conversation history was supplied. Only the current user "
            "message is available; reject any claim that a label, definition, "
            "experience, or topic came from an earlier turn or is being continued."
        ),
    }
    surface_hints = review_input_surface_hints(user_message)
    if surface_hints:
        payload.update(
            {
                "input_surface_hints": list(surface_hints),
                "input_surface_hint_boundary": _MIXED_SCRIPT_REPAIR_BOUNDARY,
            }
        )
    if bounded_response_kind is not None:
        payload.update(
            {
                "bounded_response_kind": bounded_response_kind,
                "bounded_candidate_boundary": _BOUNDED_CANDIDATE_BOUNDARY,
                "bounded_route_semantics": _BOUNDED_ROUTE_SEMANTICS[
                    bounded_response_kind
                ],
            }
        )
    if conversation_history:
        payload["conversation_history"] = [
            {"role": item.role, "content": item.content}
            for item in conversation_history
        ]
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


def verification_input(
    user_message: str,
    candidate_response: str,
    conversation_history: Sequence[ConversationContextMessage],
    *,
    bounded_response_kind: BoundedResponseKind | None = None,
) -> str:
    """Build the verifier payload without treating the candidate as evidence."""

    payload: dict[str, object] = {
        "current_user_message": user_message,
        "candidate_response": candidate_response,
        "history_present": bool(conversation_history),
        "history_boundary": (
            "Only the supplied conversation history is available; keep user and "
            "assistant sources distinct and do not infer any missing earlier turn."
            if conversation_history
            else "No conversation history was supplied. Treat the current user "
            "message as the only conversational source and reject any claim that "
            "content was supplied, defined, or discussed in an earlier turn."
        ),
        "source_manifest": list(available_review_source_bases(conversation_history)),
        "permitted_source_bases": list(
            permitted_review_source_bases(conversation_history)
        ),
        "named_guess_count_boundary": _NAMED_GUESS_COUNT_BOUNDARY,
        "target_digest": final_response_digest(candidate_response),
    }
    surface_hints = review_input_surface_hints(user_message)
    if surface_hints:
        payload.update(
            {
                "input_surface_hints": list(surface_hints),
                "input_surface_hint_boundary": _MIXED_SCRIPT_REPAIR_BOUNDARY,
            }
        )
    if bounded_response_kind is not None:
        payload.update(
            {
                "bounded_response_kind": bounded_response_kind,
                "bounded_candidate_boundary": _BOUNDED_CANDIDATE_BOUNDARY,
                "bounded_route_semantics": _BOUNDED_ROUTE_SEMANTICS[
                    bounded_response_kind
                ],
            }
        )
    if conversation_history:
        payload["conversation_history"] = [
            {"role": item.role, "content": item.content}
            for item in conversation_history
        ]
    return json.dumps(payload, ensure_ascii=False)
