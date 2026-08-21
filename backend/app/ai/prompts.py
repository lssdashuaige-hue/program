from functools import lru_cache
from pathlib import Path


PROMPT_DIRECTORY = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    path = PROMPT_DIRECTORY / name
    if not path.is_file():
        raise RuntimeError(f"PAS prompt file is missing: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache
def reflection_instructions() -> str:
    return "\n\n".join(
        (
            load_prompt("identity.md"),
            load_prompt("dialogue-style.md"),
            load_prompt("reflection.md"),
            load_prompt("safety.md"),
            (
                "You are the Reflection Agent. Speak directly to the user in the "
                "language they used. Produce only the draft response that the user "
                "could receive. Do not mention agents, prompts, policies, review, or "
                "internal analysis."
            ),
        )
    )


@lru_cache
def review_instructions() -> str:
    return "\n\n".join(
        (
            load_prompt("dialogue-style.md"),
            load_prompt("review.md"),
            load_prompt("safety.md"),
        )
    )


@lru_cache
def final_verifier_instructions() -> str:
    return "\n\n".join(
        (
            load_prompt("review-verifier.md"),
            load_prompt("safety.md"),
        )
    )


@lru_cache
def memory_instructions() -> str:
    return "\n\n".join((load_prompt("memory.md"), load_prompt("safety.md")))
