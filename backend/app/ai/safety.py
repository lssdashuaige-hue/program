from dataclasses import dataclass
import re
from typing import Literal
import unicodedata

from app.ai.models import AgentResult, ReviewDecision, RiskLevel


SafetyRisk = Literal["concerning", "urgent"]
SafetySignalCode = Literal[
    "explicit_self_harm",
    "explicit_urgent",
    "plan",
    "plan_denied",
    "immediate_time",
    "means_access",
    "alone",
    "intent",
]


@dataclass(frozen=True)
class SafetyAssessment:
    risk_level: SafetyRisk
    signal_codes: tuple[SafetySignalCode, ...]


@dataclass(frozen=True)
class _AttributedSafetySignals:
    explicit_urgent: bool = False
    plan_present: bool = False
    plan_denied: bool = False
    immediate_time: bool = False
    means_access: bool = False
    means_currently_accessible: bool = False
    alone: bool = False
    intent: bool = False


_CHINESE_SELF_HARM_MARKERS = (
    "不想活",
    "不想继续活",
    "想死",
    "自杀",
    "结束生命",
    "结束自己的生命",
    "杀了自己",
    "伤害自己",
    "伤害我自己",
    "醒不过来",
    "死了也好",
    "活着没意思",
    "消失就好了",
)
_ENGLISH_SELF_HARM_MARKERS = (
    "want to die",
    "kill myself",
    "end my life",
    "take my life",
    "suicide",
    "suicidal",
    "hurt myself",
    "harm myself",
    "don't want to live",
    "do not want to live",
    "wish i would not wake up",
    "wish i wouldn't wake up",
    "better off dead",
)
_EXPLICIT_URGENT_MARKERS = (
    "马上要自杀",
    "现在就自杀",
    "今晚结束生命",
    "今天结束生命",
    "已经准备好自杀",
    "正在伤害自己",
    "已经开始伤害自己",
    "about to kill myself",
    "going to kill myself now",
    "end my life tonight",
    "end my life today",
    "already hurting myself",
    "started hurting myself",
)
_PLAN_MARKERS = (
    "明确计划",
    "有计划",
    "计划好了",
    "已经想好",
    "想好了",
    "想好方法",
    "想好了方法",
    "准备好",
    "安排好",
    "a plan",
    "planned it",
    "chosen a method",
    "picked a method",
    "prepared to",
)
_PLAN_NEGATIONS = (
    "没有计划",
    "没计划",
    "无计划",
    "no plan",
    "do not have a plan",
    "don't have a plan",
)
_PLAN_DENIAL_PATTERNS = (
    re.compile(
        r"(?:没有|没|并没有|还没有|还没)(?:明确)?(?:计划|想好(?:了)?(?:方法)?)"
    ),
    re.compile(
        r"\b(?:have|has) not (?:made|formed|chosen) (?:a )?plan\b"
    ),
    re.compile(
        r"\b(?:haven't|hasn't) (?:made|formed|chosen) (?:a )?plan\b"
    ),
)
_IMMEDIATE_TIME_MARKERS = (
    "现在",
    "今晚",
    "今天",
    "马上",
    "立刻",
    "此刻",
    "right now",
    "tonight",
    "today",
    "immediately",
)
_MEANS_MARKERS = (
    "手段",
    "工具",
    "刀",
    "药",
    "绳",
    "枪",
    "在手边",
    "拿着",
    "准备了",
    "means",
    "weapon",
    "pills",
    "knife",
    "gun",
    "within reach",
    "in my hand",
)
_ALONE_MARKERS = (
    "一个人",
    "独自",
    "没人陪",
    "身边没人",
    "i am alone",
    "i'm alone",
    "by myself",
    "no one is with me",
)
_INTENT_MARKERS = (
    "决定了",
    "就要去做",
    "会去做",
    "准备实施",
    "控制不住",
    "不能保证安全",
    "made up my mind",
    "intend to do it",
    "going to do it",
    "cannot stay safe",
    "can't stay safe",
    "cannot control myself",
)
_FICTION_OR_QUOTE_MARKERS = (
    "电影",
    "台词",
    "小说",
    "角色",
    "引用",
    "叙事",
    "朋友说",
    "我的朋友",
    "movie",
    "film",
    "quote",
    "novel",
    "character",
    "fiction",
    "lyrics",
    "friend said",
    "my friend",
)
_NON_SELF_REFERENCE_MARKERS = (
    "不是我的想法",
    "不是我自己的想法",
    "不涉及我",
    "不涉及任何现实中的危险",
    "没有现实中的危险",
    "只是在分析",
    "说的不是我",
    "不是我本人",
    "明确不是我本人",
    "not my thought",
    "not my own thought",
    "not about me",
    "i am not feeling this",
    "i'm not feeling this",
    "no real-world danger",
    "no real world danger",
    "not me",
    "not about myself",
)
_SELF_RISK_DENIAL_MARKERS = (
    "我没有想死",
    "我并没有想死",
    "我不想死",
    "我没有自杀想法",
    "我没有自伤想法",
    "我没有伤害自己的念头",
    "没有自杀想法",
    "没有自杀的念头",
    "没有自伤想法",
    "没有伤害自己的念头",
    "我不会伤害自己",
    "i do not want to die",
    "i don't want to die",
    "i am not suicidal",
    "i'm not suicidal",
    "i have no thoughts of suicide",
    "i have no thoughts of self-harm",
    "i am not thinking of suicide",
)
_HAN_CHARACTER = re.compile(r"[\u3400-\u9fff]")
_CHINESE_DIRECT_LINK = r"[\s，,]*"
_CHINESE_DIRECT_MODIFIER = (
    r"(?:自己|本人|最近|现在|今晚|今天|马上|此刻|也|还|又|有时|一直|"
    r"已经|真的|确实|仍然|可能|开始|正在|越来越|非常|很|有点|好像|"
    r"感觉自己|似乎|其实|偶尔|有时候|甚至|会|大概|也许|或许|多少|"
    r"觉得|想好|想好了|计划|准备|决定|决定了)"
)
_CHINESE_DIRECT_SELF_HARM_PATTERN = re.compile(
    rf"(?<!告诉)我{_CHINESE_DIRECT_LINK}"
    rf"(?:{_CHINESE_DIRECT_MODIFIER}{_CHINESE_DIRECT_LINK}){{0,8}}"
    r"(?:想死|不想(?:继续)?活|(?:不太|不是很|不怎么)想(?:继续)?活|"
    r"想自杀|要自杀|"
    r"(?:想|要|准备|计划)?伤害(?:我)?自己|"
    r"(?:想|要|准备|计划)?(?:结束(?:我?自己)?的?生命|杀了?自己)|"
    r"(?:有|出现|反复有)?(?:自杀|自伤|伤害自己的)(?:的)?(?:念头|想法|冲动)|"
    r"(?:不能|无法)保证(?:自己)?(?:不会伤害自己|安全)|"
    r"(?:希望|但愿)(?:明天)?醒不过来|死了也好|活着没意思|消失就好(?:了)?)"
)
_CHINESE_IMPLICIT_PASSIVE_PATTERN = re.compile(
    r"(?:有时|一直|最近)?觉得如果(?:明天)?醒不过来(?:也)?好"
)
_CHINESE_CONTINUED_DISCLOSURE_PATTERN = re.compile(
    r"(?:但|不过|然而)?[\s，,]*(?:最近|现在|今晚|今天|有时|一直|也|还|又|"
    r"仍然|确实|真的|反复)*[\s，,]*(?:"
    r"(?:有|出现|反复有)(?:自杀|自伤|伤害自己的)(?:的)?(?:念头|想法|冲动)|"
    r"(?:想死|不想(?:继续)?活|想自杀|想伤害(?:我)?自己)|"
    r"觉得如果(?:明天)?醒不过来(?:也)?好)"
)
_ENGLISH_DIRECT_MODIFIER = (
    r"(?:myself|personally|lately|recently|currently|now|tonight|today|also|"
    r"still|sometimes|often|always|already|really|honestly|just|increasingly|"
    r"kinda|kind of|sort of|maybe|perhaps|possibly|probably|somewhat|a little|"
    r"occasionally)"
)
_ENGLISH_DIRECT_SELF_HARM_PATTERNS = (
    re.compile(
        rf"\bi\s+(?:{_ENGLISH_DIRECT_MODIFIER}\s+){{0,8}}(?:"
        r"want to die|(?:do not|don't)(?:\s+(?:really|actually|exactly|"
        r"necessarily)){0,2}\s+want to (?:keep )?live|"
        r"(?:want|plan|intend|am going|have decided|decided|made up my mind) "
        r"(?:to )?(?:kill myself|hurt myself|harm myself|end my life|take my life)|"
        r"wish i (?:would not|wouldn't) wake up|"
        r"(?:cannot|can't) (?:keep myself|stay) safe)\b"
    ),
    re.compile(
        rf"\bi\s+(?:{_ENGLISH_DIRECT_MODIFIER}\s+){{0,8}}(?:"
        rf"(?:am|feel)\s+(?:{_ENGLISH_DIRECT_MODIFIER}\s+){{0,8}}"
        r"(?:feeling\s+)?suicidal|"
        rf"have\s+(?:{_ENGLISH_DIRECT_MODIFIER}\s+){{0,8}}been thinking about suicide|"
        r"(?:am|keep|have been|have started|started) thinking about suicide|"
        r"(?:have|keep having) (?:suicidal|self-harm) (?:thoughts|urges))\b"
    ),
    re.compile(
        rf"\bi(?:'m|’m| am)\s+(?:{_ENGLISH_DIRECT_MODIFIER}\s+){{0,8}}"
        r"(?:(?:feeling\s+)?suicidal|thinking about suicide|going to (?:kill myself|"
        r"hurt myself|harm myself|end my life|take my life))\b"
    ),
)
_RISK_ATTRIBUTION_SEGMENT_SEPARATOR = re.compile(
    r"[。！？!?；;，,.]+|"
    r"\b(?:but|while|whereas|although|because)\b|"
    r"\band\s+(?=(?:i|my friend|the friend|he|she|they)\b)|"
    r"(?:但|不过|然而|而且|而|同时|因为|虽然|所以|因此|然后|接着|可是|但是)(?="
    r"(?:我|我的朋友|朋友|他|她|他们|她们|角色|人物))"
)
_SUBJECT_EVENT_PATTERN = re.compile(
    r"(?P<other>我的朋友|朋友|主人公|角色|人物|对方|别人|他们|她们|它们|"
    r"(?<![其吉])他|她|(?<!其)它|\b(?:my friend|the friend|a friend|friend|the character|"
    r"a character|character|protagonist|he|she|they)\b)|"
    r"(?P<user>^(?:(?:\s*)(?:其实|最后|后来|现在|今晚|今天|目前|此刻|最近|"
    r"然后|接着|不过|但是|而且|所以|因此|可是|而)){0,4}\s*我(?!的朋友)|"
    r"\b(?:i|i'm|i am)\b)"
)
_USER_MEANS_OWNERSHIP = re.compile(
    r"(?:在|就在)?我(?:的)?(?:手边|手里)|"
    r"\b(?:within my reach|in my hand)\b"
)
_OTHER_MEANS_OWNERSHIP = re.compile(
    r"(?:在|就在)?(?:他|她|他们|她们|朋友)(?:的)?(?:手边|手里)|"
    r"\b(?:within (?:his|her|their) reach|in (?:his|her|their) hand)\b"
)
_USER_PLAN_OWNERSHIP = re.compile(r"我的计划|\bmy plan\b")
_OTHER_PLAN_OWNERSHIP = re.compile(
    r"(?:他|她|他们|她们|朋友)的计划|"
    r"\b(?:his|her|their|the friend's|my friend's) plan\b"
)
_CURRENT_MEANS_ACCESS_MARKERS = (
    "在手边",
    "就在手边",
    "在我手边",
    "就在我手边",
    "拿着",
    "within reach",
    "within my reach",
    "in my hand",
    "with a knife",
)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _explicit_self_harm_disclosure_starts(value: str) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                match.start()
                for pattern in (
                    _CHINESE_DIRECT_SELF_HARM_PATTERN,
                    *_ENGLISH_DIRECT_SELF_HARM_PATTERNS,
                )
                for match in pattern.finditer(value)
            }
        )
    )


def _first_explicit_self_harm_disclosure_start(value: str) -> int | None:
    starts = _explicit_self_harm_disclosure_starts(value)
    return starts[0] if starts else None


def _has_explicit_first_person_self_harm_disclosure(value: str) -> bool:
    """Require a direct first-person self-harm predicate, not word co-occurrence."""

    return _first_explicit_self_harm_disclosure_start(value) is not None


def _continued_disclosure_after_self_denial_start(value: str) -> int | None:
    denial_ends = tuple(
        value.rfind(marker) + len(marker)
        for marker in _SELF_RISK_DENIAL_MARKERS
        if marker in value
    )
    if not denial_ends:
        return None
    suffix_start = max(denial_ends)
    disclosure = _CHINESE_CONTINUED_DISCLOSURE_PATTERN.search(value[suffix_start:])
    return suffix_start + disclosure.start() if disclosure is not None else None


def _non_self_suffix_start(value: str) -> int | None:
    if not _contains_any(value, _FICTION_OR_QUOTE_MARKERS):
        return None
    denial_ends = tuple(
        value.rfind(marker) + len(marker)
        for marker in _NON_SELF_REFERENCE_MARKERS
        if marker in value
    )
    return max(denial_ends) if denial_ends else None


def _is_explicit_non_self_reference(value: str) -> bool:
    suffix_start = _non_self_suffix_start(value)
    if suffix_start is None:
        return False
    return not _has_explicit_first_person_self_harm_disclosure(value[suffix_start:])


def _marker_starts(value: str, markers: tuple[str, ...]) -> tuple[int, ...]:
    starts: list[int] = []
    for marker in markers:
        start = value.find(marker)
        while start >= 0:
            starts.append(start)
            start = value.find(marker, start + len(marker))
    return tuple(starts)


def _marker_spans(
    value: str,
    markers: tuple[str, ...],
) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for marker in markers:
        start = value.find(marker)
        while start >= 0:
            spans.append((start, start + len(marker)))
            start = value.find(marker, start + len(marker))
    return tuple(spans)


def _plan_denial_spans(value: str) -> tuple[tuple[int, int], ...]:
    pattern_spans = tuple(
        (match.start(), match.end())
        for pattern in _PLAN_DENIAL_PATTERNS
        for match in pattern.finditer(value)
    )
    return tuple(sorted(set(_marker_spans(value, _PLAN_NEGATIONS) + pattern_spans)))


def _subject_events(
    segment: str,
) -> tuple[tuple[Literal["user", "other"], int], ...]:
    events: list[tuple[Literal["user", "other"], int]] = [
        (
            "other" if match.lastgroup == "other" else "user",
            match.start(),
        )
        for match in _SUBJECT_EVENT_PATTERN.finditer(segment)
    ]
    events.extend(
        ("user", direct_disclosure)
        for direct_disclosure in _explicit_self_harm_disclosure_starts(segment)
    )
    return tuple(sorted(set(events), key=lambda event: event[1]))


def _distance_to_position(match: re.Match[str], position: int) -> int:
    if match.start() <= position <= match.end():
        return 0
    return min(abs(position - match.start()), abs(position - match.end()))


def _owner_for_signal(
    segment: str,
    signal_start: int,
    inherited_owner: Literal["user", "other"],
    family: Literal["generic", "means", "plan"],
) -> Literal["user", "other"]:
    subject_events = _subject_events(segment)
    ownership_patterns = {
        "generic": None,
        "means": (_USER_MEANS_OWNERSHIP, _OTHER_MEANS_OWNERSHIP),
        "plan": (_USER_PLAN_OWNERSHIP, _OTHER_PLAN_OWNERSHIP),
    }[family]
    ownership_events = (
        tuple(
            ("user", match)
            for match in ownership_patterns[0].finditer(segment)
        )
        + tuple(
            ("other", match)
            for match in ownership_patterns[1].finditer(segment)
        )
        if ownership_patterns is not None
        else ()
    )
    ownership_events = tuple(
        event
        for event in ownership_events
        if not any(
            (
                signal_start < subject_start < event[1].start()
                if signal_start < event[1].start()
                else event[1].end() < subject_start < signal_start
            )
            for _subject_owner, subject_start in subject_events
        )
    )
    if ownership_events:
        return min(
            ownership_events,
            key=lambda event: _distance_to_position(event[1], signal_start),
        )[0]

    preceding_subject_events = tuple(
        event for event in subject_events if event[1] <= signal_start
    )
    if preceding_subject_events:
        return preceding_subject_events[-1][0]
    return inherited_owner


def _segment_spans(value: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    start = 0
    for separator in _RISK_ATTRIBUTION_SEGMENT_SEPARATOR.finditer(value):
        if start < separator.start():
            spans.append((start, separator.start()))
        start = separator.end()
    if start < len(value):
        spans.append((start, len(value)))
    return tuple(spans)


def _has_user_owned_marker(
    segment: str,
    markers: tuple[str, ...],
    inherited_owner: Literal["user", "other"],
    family: Literal["generic", "means", "plan"],
) -> bool:
    return any(
        _owner_for_signal(segment, start, inherited_owner, family) == "user"
        for start in _marker_starts(segment, markers)
    )


def _has_user_owned_positive_plan(
    segment: str,
    inherited_owner: Literal["user", "other"],
) -> bool:
    denial_spans = _plan_denial_spans(segment)
    positive_starts = tuple(
        start
        for start in _marker_starts(segment, _PLAN_MARKERS)
        if not any(span_start <= start < span_end for span_start, span_end in denial_spans)
    )
    return any(
        _owner_for_signal(segment, start, inherited_owner, "plan") == "user"
        for start in positive_starts
    )


def _has_user_owned_plan_denial(
    segment: str,
    inherited_owner: Literal["user", "other"],
) -> bool:
    return any(
        _owner_for_signal(segment, start, inherited_owner, "plan") == "user"
        for start, _end in _plan_denial_spans(segment)
    )


def _attributed_safety_signals(
    value: str,
    *,
    initial_owner: Literal["user", "other"] = "user",
) -> _AttributedSafetySignals:
    flags = {
        "explicit_urgent": False,
        "plan_present": False,
        "plan_denied": False,
        "immediate_time": False,
        "means_access": False,
        "means_currently_accessible": False,
        "alone": False,
        "intent": False,
    }
    active_owner = initial_owner
    marker_groups = (
        ("explicit_urgent", _EXPLICIT_URGENT_MARKERS, "generic"),
        ("means_access", _MEANS_MARKERS, "means"),
        ("means_currently_accessible", _CURRENT_MEANS_ACCESS_MARKERS, "means"),
        ("alone", _ALONE_MARKERS, "generic"),
        ("intent", _INTENT_MARKERS, "generic"),
    )
    for start, end in _segment_spans(value):
        segment = value[start:end]
        segment_flags: dict[str, bool] = {
            "plan_present": _has_user_owned_positive_plan(
                segment,
                active_owner,
            ),
            "plan_denied": _has_user_owned_plan_denial(
                segment,
                active_owner,
            ),
        }
        if segment_flags["plan_present"]:
            flags["plan_present"] = True
        if segment_flags["plan_denied"]:
            flags["plan_denied"] = True
        for name, markers, family in marker_groups:
            segment_flags[name] = _has_user_owned_marker(
                segment,
                markers,
                active_owner,
                family,
            )
            if not flags[name] and segment_flags[name]:
                flags[name] = True
        time_is_user_owned = _has_user_owned_marker(
            segment,
            _IMMEDIATE_TIME_MARKERS,
            active_owner,
            "generic",
        )
        local_risk_anchor = (
            _has_explicit_first_person_self_harm_disclosure(segment)
            or _CHINESE_IMPLICIT_PASSIVE_PATTERN.search(segment) is not None
            or (
                segment_flags["plan_present"]
                and not segment_flags["plan_denied"]
            )
            or segment_flags["intent"]
            or segment_flags["explicit_urgent"]
            or segment_flags["means_currently_accessible"]
        )
        if time_is_user_owned and local_risk_anchor:
            flags["immediate_time"] = True
        subject_events = _subject_events(segment)
        if subject_events:
            active_owner = subject_events[-1][0]
    return _AttributedSafetySignals(**flags)


def _is_explicit_self_risk_denial(value: str) -> bool:
    matched_denials = tuple(
        marker for marker in _SELF_RISK_DENIAL_MARKERS if marker in value
    )
    explicit_denial = bool(matched_denials)
    residual = value
    for marker in sorted(matched_denials, key=len, reverse=True):
        residual = residual.replace(marker, " ")
    residual_self_harm_disclosure = _contains_any(
        residual,
        _CHINESE_SELF_HARM_MARKERS + _ENGLISH_SELF_HARM_MARKERS,
    ) or _has_explicit_first_person_self_harm_disclosure(residual)
    return explicit_denial and not residual_self_harm_disclosure


def classify_preflight_risk(user_message: str) -> SafetyAssessment | None:
    """Catch explicit high-confidence self-harm language before any provider call."""

    normalized = " ".join(
        unicodedata.normalize("NFKC", user_message).casefold().split()
    )
    non_self_suffix_start = _non_self_suffix_start(normalized)
    if non_self_suffix_start is not None:
        local_disclosure_start = _first_explicit_self_harm_disclosure_start(
            normalized[non_self_suffix_start:]
        )
        disclosure_start = (
            non_self_suffix_start + local_disclosure_start
            if local_disclosure_start is not None
            else None
        )
    else:
        disclosure_start = _first_explicit_self_harm_disclosure_start(normalized)
    if disclosure_start is None:
        disclosure_start = _continued_disclosure_after_self_denial_start(normalized)
    if disclosure_start is None:
        implicit_disclosure = _CHINESE_IMPLICIT_PASSIVE_PATTERN.search(normalized)
        disclosure_start = (
            implicit_disclosure.start() if implicit_disclosure is not None else None
        )
    if (
        disclosure_start is None
        or _is_explicit_non_self_reference(normalized)
        or _is_explicit_self_risk_denial(normalized)
    ):
        return None

    signal_text = (
        normalized[non_self_suffix_start:]
        if non_self_suffix_start is not None
        else normalized
    )
    attributed_signals = _attributed_safety_signals(signal_text)
    explicit_urgent = attributed_signals.explicit_urgent
    plan_denied = attributed_signals.plan_denied
    plan_present = attributed_signals.plan_present
    immediate_time = attributed_signals.immediate_time
    means_access = attributed_signals.means_access
    means_currently_accessible = attributed_signals.means_currently_accessible
    alone = attributed_signals.alone
    intent = attributed_signals.intent

    signal_codes: list[SafetySignalCode] = ["explicit_self_harm"]
    if explicit_urgent:
        signal_codes.append("explicit_urgent")
    if plan_present:
        signal_codes.append("plan")
    if plan_denied:
        signal_codes.append("plan_denied")
    if immediate_time:
        signal_codes.append("immediate_time")
    if means_access:
        signal_codes.append("means_access")
    if alone:
        signal_codes.append("alone")
    if intent:
        signal_codes.append("intent")

    if (
        explicit_urgent
        or (plan_present and (immediate_time or means_access or alone or intent))
        or intent
        or alone
        or means_currently_accessible
        or (immediate_time and means_access)
    ):
        return SafetyAssessment(
            risk_level="urgent",
            signal_codes=tuple(signal_codes),
        )
    return SafetyAssessment(
        risk_level="concerning",
        signal_codes=tuple(signal_codes),
    )


def _uses_chinese(user_message: str) -> bool:
    return _HAN_CHARACTER.search(user_message) is not None


def deterministic_safety_response(
    user_message: str,
    risk_level: RiskLevel,
) -> str:
    if risk_level == "concerning":
        if _uses_chinese(user_message):
            return (
                "你写下的内容显示，你可能正承受不想继续活着的念头；这需要被认真对待。"
                "即使目前没有计划，也不等于风险可以忽略。"
                "先暂停原因或童年经历的深挖。"
                "请直接确认当前安全：你现在是否有伤害自己的冲动、能否保证此刻安全、"
                "是否独处，以及身边是否有可用于伤害自己的物品或手段？"
                "请现在联系一位现实中可信任的人，把情况告诉对方并请其陪着你；"
                "同时把可能伤害自己的物品移远或交给对方保管。"
                "如果冲动增强、无法保证安全或已经准备行动，请立即结束独处，"
                "前往有人的安全地点或最近的急诊，并联系当地紧急服务或危机支持。"
            )
        return (
            "What you wrote suggests that you may be carrying thoughts of not "
            "wanting to be alive, and that needs to be taken seriously. Even "
            "without a plan right now, the risk is not safe to ignore. Pause "
            "any deeper analysis of causes or childhood for now. Please "
            "answer directly about immediate safety: do you have an urge to harm "
            "yourself right now, can you stay safe at this moment, are you alone, "
            "and do you have access to anything you could use to hurt yourself? "
            "Contact a trusted person in your real life now, tell them what is "
            "happening, and ask them to stay with you; move any possible means "
            "away or hand them to that person. If the urge grows, you cannot stay "
            "safe, or you have begun preparing, leave isolation immediately, go "
            "to a staffed safe place or the nearest emergency department, and "
            "contact local emergency or crisis support."
        )

    if risk_level == "urgent":
        if _uses_chinese(user_message):
            return (
                "你写下的内容显示，当前存在需要立即处理的紧急自伤危险；"
                "先暂停童年经历或原因分析。"
                "请只回答当前安全：你是否已经开始行动，伤害自己的手段是否就在身边？"
                "无论答案是什么，现在都请立刻放下并远离任何可能伤害自己的物品或手段，"
                "把它们交给别人，结束独处并去到有人的安全地点。"
                "请马上联系一位现实中可信任的人，请对方来陪你；同时立即联系当地紧急服务，"
                "或直接前往最近的急诊。"
            )
        return (
            "What you wrote indicates an immediate self-harm emergency that "
            "requires action now; pause "
            "any analysis of childhood or causes. Answer only about immediate "
            "safety: have you started acting, and are any means within reach? "
            "Regardless of the answer, put down and move away from anything you "
            "could use to hurt yourself now, hand it to someone else, leave "
            "isolation, and go where other people are present. Contact a trusted "
            "person immediately and ask them to stay with you; at the same time, "
            "contact local emergency services or go directly to the nearest "
            "emergency department."
        )

    raise ValueError("A deterministic safety response requires elevated risk.")


def safe_fallback_response(user_message: str) -> str:
    if _uses_chinese(user_message):
        return (
            "我这次没能及时完成安全审核，因此不会返回未经审核的内容。请稍后重试；"
            "如果你此刻有伤害自己或他人的冲动、无法保证安全，或身边有可用于伤害自己的物品，"
            "请立即远离这些物品、结束独处，联系现实中可信任的人，并联系当地紧急服务"
            "或前往最近的急诊。"
        )
    return (
        "I could not complete the safety review in time, so I will not return "
        "unreviewed content. Please try again later. If you currently have an "
        "urge to harm yourself or someone else, cannot stay safe, or have access "
        "to something you could use for harm, move away from it immediately, "
        "leave isolation, contact a trusted person in real life, and contact local "
        "emergency services or go to the nearest emergency department."
    )


def preflight_safety_result(user_message: str) -> AgentResult | None:
    assessment = classify_preflight_risk(user_message)
    if assessment is None:
        return None
    return AgentResult(
        response=deterministic_safety_response(user_message, assessment.risk_level),
        mode="safety-guard",
        support_mode="support",
        response_source="safety_guard",
        risk_level=assessment.risk_level,
    )


def review_safety_envelope_result(
    *,
    user_message: str,
    reflection_draft: str,
    review: ReviewDecision,
) -> AgentResult:
    if review.risk_level not in {"concerning", "urgent"}:
        raise ValueError("A Review safety envelope requires elevated risk.")
    return AgentResult(
        response=deterministic_safety_response(user_message, review.risk_level),
        mode="safety-guard",
        support_mode="support",
        response_source="review_safety_envelope",
        risk_level=review.risk_level,
        reflection_draft=reflection_draft,
        review=review,
    )


def safe_fallback_result(user_message: str) -> AgentResult:
    return AgentResult(
        response=safe_fallback_response(user_message),
        mode="safety-guard",
        support_mode="support",
        response_source="safe_fallback",
    )
