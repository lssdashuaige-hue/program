"""High-precision deterministic candidates for narrow PAS boundaries.

These finite matchers deliberately do not claim broad intent classification.
Unmatched, ambiguous, educational, or ordinary health messages stay on the
normal Reflection -> Review -> Final Verifier path.
"""

from dataclasses import dataclass
import re
import unicodedata

from app.ai.models import BoundedResponseKind


@dataclass(frozen=True)
class BoundedResponseCandidate:
    kind: BoundedResponseKind
    response: str


_HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

_THIRD_PARTY_ZH = re.compile(
    r"(?:父母|父亲|母亲|爸(?:爸)?|妈(?:妈)?|家人|伴侣|对象|丈夫|妻子|"
    r"男友|女友|朋友|同事|老师|领导|(?<!其)他(?:们)?|她(?:们)?)"
)
_PHYSICAL_CAUSE_ZH = re.compile(
    r"(?:头痛|头疼|疼痛|腿痛|肚子痛|发烧|咳嗽|摔倒|受伤|流血|骨折|"
    r"头晕|身体不适|生病|偏头痛|睡眠不足|恶心|呕吐|失眠|吃坏|咖啡|"
    r"药物|症状|身体原因|医学原因)"
)
_PRIVATE_INTERACTION_ZH = re.compile(
    r"(?:动机|心里|内心|性格|人格|经历|态度|行为|对我|忽视|控制|回应|"
    r"疏远|排斥|责备|批评|指责|冷落|针对|讨厌|喜欢|爱我|恨我|"
    r"抑郁症|焦虑症|双相|精神分裂|自闭症|孤独症)"
)
_THIRD_PARTY_REQUEST_ZH = (
    re.compile(
        r"(?:你|帮我|请|能不能|可以|替我)[^。！？?\n]{0,12}猜"
        r"[^。！？?\n]{0,100}(?:为什么(?:会)?(?:这样|这么|那样)|动机|心里|"
        r"内心|性格|经历)"
    ),
    re.compile(
        r"猜猜[^。！？?\n]{0,100}(?:为什么(?:会)?(?:这样|这么|那样)|动机|"
        r"心里|内心|性格|经历)"
    ),
    re.compile(r"(?:为什么|为何)(?:会)?(?:这样|这么|那样)(?:对我)?"),
    re.compile(r"(?:心里|内心)(?:到底)?(?:怎么想|在想什么)"),
    re.compile(r"(?:家庭|性格|环境)[^。！？?\n]{0,60}(?:各占|比例|百分)"),
    re.compile(
        r"你觉得[^。！？?\n]{0,100}(?:为什么|为何)(?:总|会)?"
        r"(?:这样|这么|那样)(?:对我)?"
    ),
    re.compile(
        r"(?:是不是|有没有|算不算)[^。！？?\n]{0,30}"
        r"(?:人格|抑郁症|焦虑症|双相|精神分裂|自闭症|孤独症)"
        r"[^。！？?\n]{0,30}(?:[。！？?]\s*)?(?:帮我|你)?猜"
    ),
    re.compile(
        r"(?:为什么|为何)[^。！？?\n]{0,45}"
        r"(?:疏远|排斥|责备|批评|指责|冷落|针对|忽视|控制|拒绝)"
    ),
    re.compile(
        r"(?:你觉得|你认为|你猜|告诉我)[^。！？?\n]{0,80}"
        r"(?:动机|内心|心里|性格|人格|经历)[^。！？?\n]{0,18}"
        r"(?:是什么|为什么|如何|怎样|怎么)"
    ),
)
_THIRD_PARTY_EN = re.compile(
    r"\b(?:(?:my|our)\s+)?(?:parent|parents|mother|mom|mum|father|dad|"
    r"family|partner|boyfriend|girlfriend|husband|wife|friend|teacher|boss|"
    r"coworker|colleague|they|them|he|him|she|her)\b"
)
_PHYSICAL_CAUSE_EN = re.compile(
    r"\b(?:headache|migraine|pain|fever|cough|fell|fall|injury|bleeding|"
    r"fracture|dizzy|sick|sleep deprivation|nausea|vomiting|insomnia|"
    r"medication|physical cause|medical cause|symptom)\b"
)
_PRIVATE_INTERACTION_EN = re.compile(
    r"\b(?:motive|thinking|personality|upbringing|history|attitude|behavior|"
    r"behaviour|act|behave|treat(?:s|ed|ing)?|ignor(?:e|es|ed|ing)|control|"
    r"reject|blame|criticize|avoid|depression|"
    r"depressed|anxiety disorder|bipolar|personality disorder|schizophrenia|"
    r"autism|adhd)\b"
)
_THIRD_PARTY_REQUEST_EN = (
    re.compile(
        r"\b(?:guess|tell me|help me guess|figure out)\b.{0,100}"
        r"\b(?:motive|thinking|personality|upbringing|history|"
        r"percentage|percent)\b"
    ),
    re.compile(
        r"\b(?:guess|tell me|help me guess|figure out)\b.{0,80}\bwhy\b"
        r".{0,50}\b(?:act|behave|treat(?:s|ed|ing)?|respond|react|feel|think|"
        r"want|avoid(?:s|ed|ing)?|control(?:s|led|ling)?)\b"
    ),
    re.compile(
        r"\bwhy (?:would|did|does|are|is|were) "
        r"(?:(?:my|our)\s+)?(?:parent|parents|mother|mom|mum|father|dad|"
        r"partner|friend|boss|they|he|she)\b.{0,50}"
        r"\b(?:act|behave|treat|respond|react|feel|think|want|avoid|control)\b"
    ),
    re.compile(r"\bwhat (?:are|were|is|was) (?:they|he|she) really thinking\b"),
    re.compile(
        r"\bwhat (?:is|was|could be)\b.{0,25}"
        r"\b(?:motive|reason|thinking|personality)\b"
    ),
    re.compile(
        r"\b(?:is|does|could|might|do you think) (?:they|he|she)\b.{0,45}"
        r"\b(?:depression|depressed|anxiety disorder|bipolar|personality "
        r"disorder|schizophrenia|autism|adhd)\b"
    ),
    re.compile(
        r"\bwhy (?:would|did|does|is|was|are|were)\b.{0,30}"
        r"\b(?:ignor(?:e|es|ed|ing)|treat(?:s|ed|ing)?|avoid(?:s|ed|ing)?|"
        r"reject(?:s|ed|ing)?|control(?:s|led|ling)?)\b"
    ),
)

_DIAGNOSIS_ZH_TEXT = (
    r"分裂样人格(?:障碍)?|人格障碍|心理疾病|精神疾病|抑郁症|焦虑症|"
    r"双相(?:情感)?障碍|边缘型人格(?:障碍)?|"
    r"回避型人格(?:障碍)?|自恋型人格(?:障碍)?|强迫症|创伤后应激(?:障碍)?|"
    r"精神分裂症|注意缺陷多动障碍|自闭症|孤独症|ptsd|adhd"
)
_DIAGNOSIS_ZH = re.compile(rf"(?:{_DIAGNOSIS_ZH_TEXT})")
_SELF_DIAGNOSIS_ZH = re.compile(
    rf"(?:我|本人)(?:(?!(?:朋友|父母|父亲|母亲|爸爸|妈妈|家人|伴侣|对象|"
    rf"同事|同学|室友|老师|孩子))[^。！？?\n]){{0,12}}"
    rf"(?:是不是|有没有|算不算|可能是|会不会是|符合)"
    rf"[^。！？?\n]{{0,12}}(?:{_DIAGNOSIS_ZH_TEXT})|"
    rf"(?:我|本人)\s*(?:是否)?(?:有|患有)\s*(?:{_DIAGNOSIS_ZH_TEXT})"
    rf"\s*(?:吗|么|嘛|[?？]|$)"
)
_DIAGNOSIS_EN_TEXT = (
    r"depression|depressed|major depressive disorder|anxiety disorder|bipolar(?: disorder)?|"
    r"schizoid personality(?: disorder)?|borderline personality(?: disorder)?|"
    r"avoidant personality(?: disorder)?|narcissistic personality(?: disorder)?|"
    r"ocd|ptsd|adhd|autism|autistic|autism spectrum disorder|schizophrenia"
)
_DIAGNOSIS_EN = re.compile(rf"\b(?:{_DIAGNOSIS_EN_TEXT})\b")
_SELF_DIAGNOSIS_EN = re.compile(
    rf"\b(?:am i|could i be|might i be|would i count as)\b.{{0,24}}"
    rf"\b(?:{_DIAGNOSIS_EN_TEXT})\b|"
    rf"\b(?:do i have|do you think i have)\b.{{0,16}}"
    rf"\b(?:{_DIAGNOSIS_EN_TEXT})\b|"
    rf"\bdo you think\b.{{0,24}}\bi (?:have|am)\b.{{0,16}}"
    rf"\b(?:{_DIAGNOSIS_EN_TEXT})\b"
)

_MENTAL_HEALTH_ZH = re.compile(
    r"(?:心理疾病|精神疾病|心理障碍|精神障碍|抑郁症|焦虑症|双相(?:情感)?障碍|"
    r"精神分裂症|人格障碍)"
)
_PERSONAL_LIFESPAN_ZH = (
    re.compile(r"(?:让|使)我[^。！？?\n]{0,12}(?:少活|寿命缩短|少几年|短命)"),
    re.compile(r"(?:我的|我个人的|对我(?:个人)?)\s*(?:预期)?寿命"),
    re.compile(r"我(?:个人)?(?:会|要|可能会|将会)?\s*(?:少活|短命|活几年)"),
    re.compile(r"(?:我会|我能)[^。！？?\n]{0,12}(?:少活|活到|活几年)"),
)
_MENTAL_HEALTH_EN = re.compile(
    r"\b(?:mental illness|mental disorder|psychiatric disorder|depression|"
    r"anxiety disorder|bipolar(?: disorder)?|schizophrenia|personality disorder)\b"
)
_PERSONAL_LIFESPAN_EN = (
    re.compile(r"\b(?:my|for me)\b.{0,35}\b(?:life expectancy|lifespan|years? (?:lost|shorter))\b"),
    re.compile(r"\b(?:take|cost|cut)\b.{0,35}\b(?:off|from) my life\b"),
    re.compile(r"\bhow many years? (?:will|would|could) i (?:lose|live less)\b"),
    re.compile(r"\bmake me (?:live|die)\b.{0,20}\b(?:years?|earlier|shorter)\b"),
    re.compile(r"\b(?:shorten|reduce) my (?:life|lifespan|life expectancy)\b"),
)

_DENIED_PERSONAL_LIFESPAN_ZH = re.compile(
    r"(?:我(?:没有|不是|未患)[^。！？?\n]{0,30}"
    r"(?:心理疾病|精神疾病|抑郁症|焦虑症|双相|精神分裂|人格障碍)|"
    r"(?:不会|并不会|不可能)[^。！？?\n]{0,20}(?:少活|短命|寿命缩短))"
)
_DENIED_PERSONAL_LIFESPAN_EN = re.compile(
    r"\b(?:i (?:do not|don't|dont) have|i am not diagnosed with)\b.{0,35}"
    r"\b(?:mental illness|depression|anxiety disorder|bipolar|schizophrenia)\b|"
    r"\b(?:will not|won't|wont|does not|doesn't|doesnt)\b.{0,25}"
    r"\b(?:shorten|reduce|take years off)\b.{0,20}\bmy life\b"
)

_NEGATED_BOUNDED_REQUEST = re.compile(
    r"(?:不要|别|无需|不必)[^。！？?\n]{0,8}(?:猜|诊断|自测|测试|换算|计算)|"
    r"(?:我)?(?:不是|并非)(?:在)?(?:问|询问|想问)[^。！？?\n]{0,24}"
    r"(?:我|自己)(?:是不是|有没有|是否有)|"
    r"\b(?:do not|don't|dont|no need to)\b.{0,20}"
    r"\b(?:guess|diagnose|test|calculate|convert)\b|"
    r"\bi(?:'m| am) not asking (?:whether|if) i\b"
)
_QUOTED_OR_FICTION_FRAME = re.compile(
    r"(?:电影|小说|剧本|台词|角色|例句|引用|教材|案例|字符串|提示词)"
    r"[^。！？?\n]{0,30}(?:说|写|问|是|分类|内容)|"
    r"朋友[^。！？?\n]{0,16}问[^。！？?\n]{0,24}(?:你猜|猜猜|为什么)|"
    r"(?:朋友|他|她|别人|医生)[^。！？?\n]{0,16}(?:问|说|写|觉得)"
    r"[^。！？?\n]{0,16}(?:我|自己)(?:是不是|有没有|算不算)|"
    r"\b(?:in|from) (?:a|the) (?:movie|novel|script)\b|"
    r"\b(?:a|the) character (?:says|asks)\b|"
    r"\bmy friend (?:said|asked)\b|"
    r"\b(?:quote|example|string|prompt)\s*:"
)
_META_CLASSIFIER_QUESTION = re.compile(
    r"(?:人工智能|ai)[^。！？?\n]{0,20}(?:应该|能不能|可以)(?:去)?猜|"
    r"\b(?:should|can|may) (?:an? )?ai\b.{0,25}\bguess\b|"
    r"(?:字符串|内容)[^。！？?\n]{0,30}(?:分类|不要回答|无需回答)|"
    r"\b(?:classify|string|prompt)\b.{0,40}\b(?:do not|don't) answer\b"
)
_EDUCATIONAL_OR_META_FRAME = re.compile(
    r"(?:教材|课程|课堂(?:题|练习|案例|讨论)?|作业|论文|问卷|题目|文案|字符串|提示词|例句|例子|示例|例如|比如|举例|引用|"
    r"电影|小说|剧本|台词|角色|研究题|课程作业|检查文案|翻译|译成|改写|"
    r"释义)|"
    r"(?:我的|这篇|一篇|该项?)研究|研究[^。！？?\n]{0,12}(?:主题|题目|课题|案例|调查)|"
    r"\b(?:my paper|class assignment|course assignment|textbook|case study|"
    r"questionnaire|survey item|prompt injection|translate|translation|"
    r"for example|for instance|as an example|example|"
    r"paraphrase|rewrite)\b|"
    r"\b(?:my|this|the) (?:research|study|topic)\b|"
    r"\bresearch (?:question|project|paper|topic|study)\b|"
    r"\bthis is (?:a )?(?:test|quiz|class exercise)\b|"
    r"\b(?:check|review|explain) (?:the )?wording\b"
)
_PAIRED_QUOTE_FRAME = re.compile(
    r"「[^」\n]{1,500}」|『[^』\n]{1,500}』|“[^”\n]{1,500}”|"
    r"‘[^’\n]{1,500}’|"
    r'"[^"\n]{1,500}"'
)

_OTHER_CHAT_REFERENCE_ZH = re.compile(
    r"(?:另一个|另一段|另一|其他|其它|别的|不同|那段|上一个|上次|之前|"
    r"先前|此前|过去)(?:的)?(?:聊天框?|聊天|对话|会话)"
)
_OTHER_CHAT_REFERENCE_EN = re.compile(
    r"\b(?:my\s+|the\s+|your\s+)?(?:other|another|previous|prior|past|last|"
    r"separate)\s+(?:chat|conversation|thread)\b"
)
_CROSS_CHAT_ACTION_ZH_TEXT = (
    r"读取|查看|调取|访问|打开|同步|导入|记起|记住|回忆|沿用|延续|"
    r"接着|继续|贴|粘贴|复制|带过来"
)
_CROSS_CHAT_REQUEST_ACTION_ZH = re.compile(
    rf"(?:^|[，,。！？?；;\n])\s*(?:所以|那么|那就|现在|接下来)?\s*"
    rf"(?:(?:请(?:你)?|麻烦你|帮我|替我|能否请你|可以请你|"
    rf"我(?:希望|想让|要)你)[^。！？?；;\n]{{0,12}})"
    rf"(?:{_CROSS_CHAT_ACTION_ZH_TEXT})(?!了|过)|"
    rf"(?:^|[，,。！？?；;\n])\s*你"
    rf"(?:直接|先|现在|继续|接着)[^。！？?；;\n]{{0,6}}"
    rf"(?:{_CROSS_CHAT_ACTION_ZH_TEXT})(?!了|过)|"
    rf"(?:^|[，,。！？?；;\n])\s*(?:请|直接|先|现在)?\s*"
    rf"(?:{_CROSS_CHAT_ACTION_ZH_TEXT})(?!了|过)|"
    rf"(?:^|[，,。！？?；;\n])\s*(?:请)?\s*(?:把|将)"
    rf"[^。！？?；;\n]{{0,36}}(?:贴|粘贴|复制|带过来)(?!了|过)"
)
_CROSS_CHAT_ACTION_EN_TEXT = (
    r"read|view|access|retrieve|open|import|sync|remember|recall|use|paste|"
    r"copy|bring|continue|carry\s+(?:it\s+)?forward|rely\s+on|refer\s+to"
)
_CROSS_CHAT_REQUEST_ACTION_EN = re.compile(
    rf"(?:^|[.!?;\n])\s*(?:so\s+|now\s+|then\s+)?"
    rf"(?:please|can\s+you|could\s+you|would\s+you|will\s+you|"
    rf"i\s+(?:want|need|would\s+like)\s+you\s+to)\s+"
    rf"(?:directly\s+)?(?:{_CROSS_CHAT_ACTION_EN_TEXT})\b|"
    rf"(?:^|[.!?;\n])\s*(?:please\s+|just\s+|directly\s+)?"
    rf"(?:{_CROSS_CHAT_ACTION_EN_TEXT})\b"
)
_CROSS_CHAT_BASIS_REQUEST_ZH = re.compile(
    r"(?:^|[，,。！？?；;\n])\s*(?:请(?:你)?|麻烦你|帮我|你)?\s*"
    r"(?:依据|根据|结合|参考)[^。！？?；;\n]{0,28}"
    r"(?:另一个|另一段|另一|其他|其它|别的|那段|上一个|上次|之前|先前|"
    r"此前|过去)(?:的)?(?:聊天框?|聊天|对话|会话)"
    r"[^。！？?；;\n]{0,24}(?:告诉我|回答我|回复我|给出|分析|判断|"
    r"继续|接着)"
)
_CROSS_CHAT_BASIS_REQUEST_EN = re.compile(
    r"(?:^|[.!?;\n])\s*(?:please\s+)?"
    r"(?:based\s+on|according\s+to|using|from)\b[^.!?;\n]{0,36}"
    r"(?:other|another|previous|prior|past|last|separate)\s+"
    r"(?:chat|conversation|thread)\b[^.!?;\n]{0,24}"
    r"\b(?:tell\s+me|answer|reply|respond|analy[sz]e|assess|conclude|"
    r"continue|pick\s+up|carry\s+on)\b"
)
_CROSS_CHAT_ALREADY_SUPPLIED_ZH = re.compile(
    r"(?:我|用户)?(?:已经|已|刚刚|刚才)(?:把|将)?[^。！？?\n]{0,36}"
    r"(?:贴|粘贴|复制|发|发送|提供|带)(?:了|过)?(?:到|在)?"
    r"(?:这里|当前(?:聊天|对话)|本(?:条)?消息|下面|以下|上面)|"
    r"(?:我|用户)(?:把|将)?[^。！？?\n]{0,36}"
    r"(?:贴|粘贴|复制|发|发送|提供|带)(?:了|过)(?:到|在)?"
    r"(?:这里|当前(?:聊天|对话)|本(?:条)?消息|下面|以下|上面)|"
    r"(?:我|用户)(?:把|将)?[^。！？?\n]{0,36}"
    r"(?:贴|粘贴|复制|发|发送|提供|带)(?:到|在)?"
    r"(?:这里|当前(?:聊天|对话)|本(?:条)?消息|下面|以下|上面)(?:了|过)|"
    r"(?:以下|下面|上面)(?:就是|是)?[^。！？?\n]{0,36}"
    r"(?:从)?(?:另一个|另一段|其他|别的|之前|先前)(?:的)?"
    r"(?:聊天|对话|会话)[^。！？?\n]{0,18}(?:复制|贴|粘贴|带)(?:来|过来)?"
)
_CROSS_CHAT_ALREADY_SUPPLIED_EN = re.compile(
    r"\bi\s+(?:have\s+|already\s+|just\s+)?"
    r"(?:pasted|copied|provided|shared|sent|brought)\b[^.!?\n]{0,32}"
    r"\b(?:here|below|above|into\s+this\s+(?:chat|conversation)|"
    r"in\s+this\s+message)\b|"
    r"\b(?:below|above|here)\s+(?:is|are)\b[^.!?\n]{0,32}"
    r"\b(?:copied|pasted|shared)\s+from\s+(?:my\s+|the\s+)?"
    r"(?:other|another|previous|prior)\s+(?:chat|conversation|thread)\b"
)
_CROSS_CHAT_CONDITIONAL_SUPPLY_ZH = re.compile(
    r"(?:如果|假如|要是|等我|等到我|以后|之后)[^。！？?\n]{0,40}"
    r"(?:贴|粘贴|复制|发|发送|提供|带)(?:到|在)?"
    r"(?:这里|当前(?:聊天|对话)|本(?:条)?消息|下面|以下|上面)"
)
_CROSS_CHAT_CONDITIONAL_SUPPLY_EN = re.compile(
    r"\b(?:if|when|once|after)\s+i\s+[^.!?\n]{0,24}"
    r"(?:paste|copy|provide|share|send|bring)(?:d|ied|t)?\b[^.!?\n]{0,24}"
    r"\b(?:here|below|above|this\s+(?:chat|conversation|message))\b"
)
_NEGATED_CROSS_CHAT_REQUEST_ZH = re.compile(
    r"(?:不要|别|请勿|无需|不用|不必|禁止|并非要|不是要|不是让你)"
    r"(?:再|去|直接|替我|帮我)?"
    r"(?:读取|查看|调取|访问|打开|同步|导入|记起|记住|回忆|沿用|延续|"
    r"接着|继续|依据|根据|结合|参考)|"
    r"(?:读取|查看|调取|访问|打开|同步|导入|记起|记住|回忆|沿用|延续|"
    r"接着|继续|依据|根据|结合|参考)"
    r"[^。！？?；;\n]{0,28}(?:并不必要|并非必要|不必要|不是(?:我)?的要求|"
    r"并非(?:我)?的要求)"
)
_NEGATED_CROSS_CHAT_REQUEST_EN = re.compile(
    r"\b(?:do\s+not|don't|dont|never|no\s+need\s+to|must\s+not|should\s+not|"
    r"i(?:'m|\s+am)\s+not\s+asking\s+you\s+to)\s+"
    r"(?:read|view|access|retrieve|open|import|sync|remember|recall|use|"
    r"continue|carry\s+(?:it\s+)?forward|rely\s+on|refer\s+to)\b|"
    r"\b(?:read|view|access|retrieve|open|import|sync|remember|recall|use|"
    r"continue|carry\s+(?:it\s+)?forward|rely\s+on|refer\s+to)\b"
    r"[^.!?;\n]{0,40}\b(?:is\s+not|isn't)\s+(?:necessary|needed|what\s+i(?:'m|\s+am)\s+asking(?:\s+for)?)\b"
)
_CROSS_CHAT_CAPABILITY_ONLY_ZH = re.compile(
    r"(?:^|[，,。！？?；;\n])\s*(?:你|ai|人工智能|系统)(?:到底)?"
    r"(?:能不能|能否|是否能|可不可以)"
    r"[^。！？?\n]{0,24}(?:读取|查看|访问|调取)(?:其他|另一个|别的)"
    r"(?:聊天|对话|会话)(?:吗|么|嘛)?"
)
_CROSS_CHAT_CAPABILITY_ONLY_EN = re.compile(
    r"(?:^|[.!?;\n])\s*can\s+(?:you|an?\s+ai|the\s+system)\s+"
    r"(?:read|view|access|retrieve)"
    r"\s+(?:other|another)\s+(?:chats?|conversations?|threads?)\b"
)
_CROSS_CHAT_CAPABILITY_WITH_RESULT_ZH = re.compile(
    r"(?:^|[，,。！？?；;\n])\s*(?:你)?(?:能不能|能否|是否能|可不可以)"
    r"[^。！？?；;\n]{0,28}"
    r"(?:读取|查看|访问|调取|打开)(?:其他|另一个|别的)"
    r"(?:聊天|对话|会话)[^。！？?；;\n]{0,18}"
    r"(?:然后|并且|并|后|再)(?:告诉|回答|回复|分析|总结|判断|给出)"
)
_CROSS_CHAT_CAPABILITY_WITH_RESULT_EN = re.compile(
    r"(?:^|[.!?;\n])\s*can\s+you\s+(?:read|view|access|retrieve|open)\s+"
    r"(?:my\s+|the\s+)?(?:other|another)\s+"
    r"(?:chat|conversation|thread)[^.!?;\n]{0,18}"
    r"\b(?:and|then)\s+(?:tell|answer|reply|respond|analy[sz]e|summari[sz]e|"
    r"conclude|continue)\b"
)
_CROSS_CHAT_MIXED_TASK_ZH = re.compile(
    r"(?:另外|顺便|同时|还要|还请|然后再|并且还)[^。！？?\n]{0,24}"
    r"(?:写|翻译|搜索|查找|计算|画|生成|制定|预订|发邮件)"
)
_CROSS_CHAT_MIXED_TASK_EN = re.compile(
    r"\b(?:also|separately|in\s+addition|and\s+then)\b[^.!?\n]{0,28}"
    r"\b(?:write|translate|search|calculate|draw|generate|plan|book|email)\b"
)

_RESPONSES: dict[tuple[BoundedResponseKind, bool], str] = {
    (
        "unavailable_cross_chat_context",
        True,
    ): (
        "我只能看到当前对话，无法查看或读取其他聊天。请把希望我依据的相关原文粘贴"
        "到这里，或在这里简要概括；在你提供之前，我不能依据另一段聊天的内容或结论"
        "作答。"
    ),
    (
        "unavailable_cross_chat_context",
        False,
    ): (
        "I can see only this conversation and cannot view or read other chats. "
        "Please paste the relevant text you want me to use here or summarize it "
        "here; until you provide it, I cannot base an answer on the content or "
        "conclusions of another chat."
    ),
    (
        "third_party_private_state",
        True,
    ): (
        "我可以依据你说出的互动来帮你整理，但不能从有限信息推断对方未说出的动机、"
        "性格、经历或内心原因，也不能据此判断对方是否有某种心理诊断或给这些原因分配"
        "比例。比较稳妥的是分开看：你实际观察到了什么、这段互动怎样影响了你，以及哪些"
        "原因仍然未知。你想先整理哪一次具体互动？"
    ),
    (
        "third_party_private_state",
        False,
    ): (
        "I can help you organize the interaction you described, but I cannot "
        "infer another person's undisclosed motives, personality, history, or "
        "inner causes from limited information, determine whether they have a "
        "psychological diagnosis, or assign causal percentages. A safer approach "
        "is to separate what you directly observed, how the interaction affected "
        "you, and what remains unknown. Which specific interaction would you like "
        "to examine first?"
    ),
    (
        "single_chat_diagnostic_request",
        True,
    ): (
        "单凭当前聊天里的有限信息，不能判断你是否有某种心理或人格诊断，我也不会用"
        "特征清单让你自行对照。如果这份担心或相关体验让你困扰、明显影响日常生活，"
        "可以考虑请合格的心理健康专业人员做完整评估。目前有没有实际影响是你想先"
        "处理的？"
    ),
    (
        "single_chat_diagnostic_request",
        False,
    ): (
        "Limited information from this chat cannot determine whether you have a "
        "psychological or personality diagnosis, and I will not give you a trait "
        "checklist for self-diagnosis. If this concern or any related experience "
        "is distressing or significantly affects daily life, a full assessment by "
        "a qualified mental-health professional may help. Is there a practical "
        "impact you would like to address first?"
    ),
    (
        "personal_lifespan_conversion",
        True,
    ): (
        "群体研究中的统计关联不能换算成你个人的寿命或‘少活几年’，疾病名称和严重度也"
        "不能给出可靠的个人年数。它们只能说明群体层面的差异，不能替代对你个人结果的"
        "判断；如果你关心自身风险，可以和合格的医疗或心理健康专业人员讨论你的具体情况"
        "和下一步，而不是接受一个虚假的精确数字。你想先讨论哪一步？"
    ),
    (
        "personal_lifespan_conversion",
        False,
    ): (
        "Statistical associations in group research cannot be converted into "
        "your personal lifespan or a number of years you will lose, and a "
        "condition name or severity does not yield a reliable individual number. "
        "They can describe differences at the group level, but cannot determine "
        "your individual outcome; if you are concerned about your own risk, "
        "discuss your situation and next steps with a qualified medical or "
        "mental-health professional instead of accepting false precision. Which "
        "next step would you like to discuss first?"
    ),
}


_THIRD_SUBJECT_ZH_TEXT = (
    r"(?:我(?:的)?(?:父母|父亲|母亲|爸(?:爸)?|妈(?:妈)?|家人|伴侣|对象|丈夫|妻子|男友|"
    r"女友|朋友|同事|老师|领导)|父母|父亲|母亲|爸爸|妈妈|家人|伴侣|对象|"
    r"丈夫|妻子|男友|女友|朋友|同事|老师|领导|他(?:们)?|她(?:们)?)"
)
_INTERACTION_VERB_ZH_TEXT = (
    r"(?:疏远|排斥|责备|批评|指责|冷落|针对|忽视|控制|拒绝|盯着|贬低|"
    r"羞辱|讨厌|喜欢|回避)"
)
_SELF_DIAGNOSIS_DIRECT_ZH = re.compile(
    rf"(?:^|[,，:：]\s*)(?:我|本人)\s*"
    rf"(?:(?:(?:到底|究竟)\s*)?"
    rf"(?:是不是|有没有|是否有|会不会是)\s*(?:{_DIAGNOSIS_ZH_TEXT})|"
    rf"可能(?:是|有)\s*(?:{_DIAGNOSIS_ZH_TEXT})\s*(?:吗|么|嘛))"
)
_SELF_DIAGNOSIS_HAVE_QUESTION_ZH = re.compile(
    rf"(?:^|[,，:：]\s*)(?:我|本人)\s*(?:有|患有)\s*"
    rf"(?:{_DIAGNOSIS_ZH_TEXT})\s*(?:吗|么|嘛)"
)
_SELF_DIAGNOSIS_REQUEST_ZH = re.compile(
    rf"(?:你觉得|你认为|你猜|猜猜|猜一下|帮我猜|请判断|可以判断|能判断|帮我判断|判断一下|"
    rf"诊断一下|自测)[^。！？?\n]{{0,24}}(?:我|本人)\s*"
    rf"(?:(?:是不是|有没有|是否有|会不会是|可能(?:是|有))\s*"
    rf"(?:{_DIAGNOSIS_ZH_TEXT})|(?:有|患有)\s*(?:{_DIAGNOSIS_ZH_TEXT})\s*"
    rf"(?:吗|么|嘛)?)"
)
_THIRD_DIAGNOSIS_REQUEST_ZH = re.compile(
    rf"(?:你觉得|你认为|你猜|帮我猜|请判断|我想知道|我想问|我问)"
    rf"[^。！？?\n]{{0,20}}(?:{_THIRD_SUBJECT_ZH_TEXT})\s*"
    rf"(?:(?:是不是|有没有|是否有|会不会是|会不会有|可能是)\s*"
    rf"(?:{_DIAGNOSIS_ZH_TEXT})|(?:有|患有)\s*(?:{_DIAGNOSIS_ZH_TEXT})"
    rf"\s*(?:吗|么|嘛))"
)
_THIRD_DIAGNOSIS_DIRECT_ZH = re.compile(
    rf"(?:^|[,，:：]\s*)(?:{_THIRD_SUBJECT_ZH_TEXT})\s*"
    rf"(?:(?:是不是|有没有|是否有|会不会是|会不会有)\s*"
    rf"(?:{_DIAGNOSIS_ZH_TEXT})|可能是\s*(?:{_DIAGNOSIS_ZH_TEXT})"
    rf"\s*(?:吗|么|嘛)|(?:有|患有)\s*(?:{_DIAGNOSIS_ZH_TEXT})"
    rf"\s*(?:吗|么|嘛))"
)
_THIRD_INTERACTION_DIRECT_ZH = (
    re.compile(
        rf"(?:^|[,，:：]\s*)(?:{_THIRD_SUBJECT_ZH_TEXT})\s*"
        rf"(?:为什么|为何)[^。！？?\n]{{0,16}}(?:{_INTERACTION_VERB_ZH_TEXT})"
    ),
    re.compile(
        rf"(?:为什么|为何)\s*(?:{_THIRD_SUBJECT_ZH_TEXT})"
        rf"[^。！？?\n]{{0,16}}(?:{_INTERACTION_VERB_ZH_TEXT})"
    ),
)
_THIRD_INTERACTION_REQUEST_ZH = (
    re.compile(
        rf"(?:你猜|帮我猜|猜猜|请告诉我|你觉得|你认为)[^。！？?\n]{{0,16}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})\s*(?:为什么|为何)"
        rf"[^。！？?\n]{{0,16}}(?:{_INTERACTION_VERB_ZH_TEXT})"
    ),
    re.compile(
        rf"(?:你觉得|你认为|你猜|帮我猜|请告诉我)[^。！？?\n]{{0,18}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})[^。！？?\n]{{0,28}}"
        rf"(?:{_INTERACTION_VERB_ZH_TEXT})[^。！？?\n]{{0,18}}"
        rf"(?:动机|原因|内心|心里)[^。！？?\n]{{0,8}}"
        rf"(?:是什么|为什么|如何|怎样|怎么)"
    ),
    re.compile(
        rf"(?:你觉得|你认为|你猜|帮我猜|请告诉我)[^。！？?\n]{{0,18}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})\s*(?:为什么|为何)[^。！？?\n]{{0,20}}"
        rf"(?:这样|这么|那样)[^。！？?\n]{{0,10}}对我"
    ),
    re.compile(
        rf"(?:你猜|帮我猜|请告诉我)[^。！？?\n]{{0,16}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})\s*(?:为什么|为何)(?:会)?"
        rf"(?:这样|这么|那样)[^。！？?\n]{{0,30}}"
        rf"(?:家庭|性格|环境|动机|内心|心里)"
    ),
    re.compile(
        rf"(?:你猜|你能猜|猜猜|帮我猜|你觉得|你认为)[^。！？?\n]{{0,16}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})[^。！？?\n]{{0,12}}"
        rf"(?:心里|内心)[^。！？?\n]{{0,10}}(?:怎么想|在想什么|想什么)"
    ),
    re.compile(
        rf"(?:^|[,，:：]\s*)(?:{_THIRD_SUBJECT_ZH_TEXT})[^。！？?\n]{{0,8}}"
        rf"(?:心里|内心)[^。！？?\n]{{0,8}}(?:怎么想|在想什么|想什么)"
    ),
    re.compile(
        rf"(?:你猜|你能猜|猜猜|帮我猜|你觉得|你认为)[^。！？?\n]{{0,18}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})[^。！？?\n]{{0,14}}"
        rf"(?:是什么性格|性格(?:是什么|怎么样|如何)|经历过怎样的童年|"
        rf"有怎样的童年|小时候经历了什么)"
    ),
    re.compile(
        rf"(?:^|[,，:：]\s*)(?:{_THIRD_SUBJECT_ZH_TEXT})\s*"
        rf"(?:到底\s*)?(?:在想什么|想什么|怎么想)"
    ),
    re.compile(
        rf"(?:你猜|你能猜|猜猜|帮我猜|你觉得|你认为)[^。！？?\n]{{0,16}}"
        rf"(?:{_THIRD_SUBJECT_ZH_TEXT})\s*(?:到底\s*)?"
        rf"(?:在想什么|想什么|怎么想)"
    ),
)

_THIRD_SUBJECT_EN_TEXT = (
    r"(?:my (?:parents?|mother|mom|mum|father|dad|family|partner|boyfriend|"
    r"girlfriend|husband|wife|friend|teacher|boss|coworker|colleague)|"
    r"they|he|she)"
)
_THIRD_POSSESSIVE_EN_TEXT = r"(?:their|his|her|my (?:parent|mother|father|partner|friend)'s)"
_INTERACTION_VERB_EN_TEXT = (
    r"(?:ignor(?:e|es|ed|ing)|treat(?:s|ed|ing)?|avoid(?:s|ed|ing)?|"
    r"reject(?:s|ed|ing)?|control(?:s|led|ling)?|blame(?:s|d|ing)?|"
    r"criticiz(?:e|es|ed|ing)|distance(?:s|d|ing)?|exclude(?:s|d|ing)?)"
)
_SELF_DIAGNOSIS_REQUEST_EN = (
    re.compile(
        rf"\bam i\s+(?:{_DIAGNOSIS_EN_TEXT})\b|"
        rf"\b(?:could|might) i\s+(?:be|have)\s+(?:{_DIAGNOSIS_EN_TEXT})\b"
    ),
    re.compile(rf"\bdo i have\s+(?:{_DIAGNOSIS_EN_TEXT})\b"),
    re.compile(
        rf"\b(?:do you think|can you guess|could you judge)\s+i\s+"
        rf"(?:have|am)\s+(?:{_DIAGNOSIS_EN_TEXT})\b"
    ),
)
_THIRD_DIAGNOSIS_REQUEST_EN = (
    re.compile(
        rf"\b(?:do you think|can you guess|could you judge)\s+"
        rf"(?:{_THIRD_SUBJECT_EN_TEXT})\s+(?:has|have|is|are)\s+"
        rf"(?:an?\s+)?(?:{_DIAGNOSIS_EN_TEXT}|personality disorder)\b"
    ),
    re.compile(
        rf"\b(?:does|do|could|might)\s+(?:{_THIRD_SUBJECT_EN_TEXT})\s+"
        rf"(?:have|be)\s+(?:an?\s+)?(?:{_DIAGNOSIS_EN_TEXT}|personality disorder)\b"
    ),
    re.compile(
        rf"\b(?:is|are)\s+(?:{_THIRD_SUBJECT_EN_TEXT})\s+"
        rf"(?:an?\s+)?(?:{_DIAGNOSIS_EN_TEXT}|personality disorder)\b"
    ),
)
_THIRD_INTERACTION_REQUEST_EN = (
    re.compile(
        rf"\bwhy\s+(?:does|did|is|are|would|was|were)\s+"
        rf"(?:{_THIRD_SUBJECT_EN_TEXT})\s+[^?.!\n]{{0,18}}"
        rf"(?:{_INTERACTION_VERB_EN_TEXT})\b"
    ),
    re.compile(
        rf"\b(?:can you guess|tell me|help me understand)\s+why\s+"
        rf"(?:{_THIRD_SUBJECT_EN_TEXT})\s+[^?.!\n]{{0,18}}"
        rf"(?:{_INTERACTION_VERB_EN_TEXT}|act(?:s|ed|ing)?|behav(?:e|es|ed|ing))\b"
    ),
    re.compile(
        rf"\bwhat\s+(?:is|was|could be)\s+(?:{_THIRD_POSSESSIVE_EN_TEXT})\s+"
        rf"(?:motive|reason|thinking|intention)\b[^?.!\n]{{0,24}}"
        rf"(?:{_INTERACTION_VERB_EN_TEXT})?"
    ),
    re.compile(
        rf"\bwhat\s+(?:is|was)\s+(?:{_THIRD_SUBJECT_EN_TEXT})\s+"
        rf"(?:really\s+)?thinking\b"
    ),
    re.compile(
        rf"\b(?:can you guess|tell me)\s+(?:{_THIRD_POSSESSIVE_EN_TEXT})\s+"
        rf"(?:personality|inner thoughts|motive)\b"
    ),
    re.compile(
        rf"\btell me what childhood\s+(?:{_THIRD_SUBJECT_EN_TEXT})\s+had\b"
    ),
    re.compile(
        rf"\bwhat personality (?:does|did)\s+(?:{_THIRD_SUBJECT_EN_TEXT})\s+have\b"
    ),
)
_CLAUSE_PATTERN = re.compile(r"([^。！？?!；;\n.]+)([。！？?!；;\n.]|$)")
_THIRD_PARTY_SUPPORT_REQUEST = re.compile(
    r"(?:(?:我)?(?:该|应该|能|可以)?(?:怎样|怎么|如何)(?:去|来)?"
    r"(?:支持|回应|帮助|照顾)|"
    r"(?:我)?(?:该|应该|能|可以)(?:做什么|怎么做)(?:来|去)?"
    r"(?:支持|帮助|照顾)|(?:就医|支持|回应|帮助)建议)|"
    r"\b(?:(?:how (?:should|can|could|do) i (?:best )?"
    r"(?:respond|support|help|care for)|"
    r"what (?:should|can|could) i do to (?:support|help|care for))|"
    r"medical advice|support advice)\b"
)


@dataclass(frozen=True)
class _BoundedClause:
    text: str
    is_question: bool


def _bounded_clauses(value: str) -> tuple[_BoundedClause, ...]:
    clauses: list[_BoundedClause] = []
    for match in _CLAUSE_PATTERN.finditer(value):
        text = match.group(1).strip()
        if not text:
            continue
        clauses.append(
            _BoundedClause(
                text=text,
                is_question=match.group(2) in {"?", "？"},
            )
        )
    return tuple(clauses)


def normalize_bounded_match_text(value: str) -> str:
    """Normalize compatibility/case forms without translating user content."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Cf"
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _third_party_private_state_request(value: str) -> bool:
    for clause in _bounded_clauses(value):
        if (
            _PHYSICAL_CAUSE_ZH.search(clause.text) is not None
            or _PHYSICAL_CAUSE_EN.search(clause.text) is not None
            or _THIRD_PARTY_SUPPORT_REQUEST.search(clause.text) is not None
        ):
            continue
        if _THIRD_DIAGNOSIS_REQUEST_ZH.search(clause.text) is not None:
            return True
        if _THIRD_DIAGNOSIS_DIRECT_ZH.search(clause.text) is not None:
            return True
        if any(
            pattern.search(clause.text) is not None
            for pattern in _THIRD_INTERACTION_DIRECT_ZH
        ):
            return True
        if any(
            pattern.search(clause.text) is not None
            for pattern in _THIRD_INTERACTION_REQUEST_ZH
        ):
            return True
        if any(
            pattern.search(clause.text) is not None
            for pattern in _THIRD_DIAGNOSIS_REQUEST_EN
        ):
            return True
        if any(
            pattern.search(clause.text) is not None
            for pattern in _THIRD_INTERACTION_REQUEST_EN
        ):
            return True
    return False


def _single_chat_diagnostic_request(value: str) -> bool:
    for clause in _bounded_clauses(value):
        if _SELF_DIAGNOSIS_REQUEST_ZH.search(clause.text) is not None:
            return True
        if _SELF_DIAGNOSIS_DIRECT_ZH.search(clause.text) is not None:
            return True
        if _SELF_DIAGNOSIS_HAVE_QUESTION_ZH.search(clause.text) is not None:
            return True
        if any(
            pattern.search(clause.text) is not None
            for pattern in _SELF_DIAGNOSIS_REQUEST_EN
        ):
            return True
    return False


def _personal_lifespan_conversion(value: str) -> bool:
    for clause in _bounded_clauses(value):
        if (
            _DENIED_PERSONAL_LIFESPAN_ZH.search(clause.text) is not None
            or _DENIED_PERSONAL_LIFESPAN_EN.search(clause.text) is not None
        ):
            continue
        if (
            _MENTAL_HEALTH_ZH.search(clause.text) is not None
            and any(
                pattern.search(clause.text) is not None
                for pattern in _PERSONAL_LIFESPAN_ZH
            )
        ):
            return True
        if (
            _MENTAL_HEALTH_EN.search(clause.text) is not None
            and any(
                pattern.search(clause.text) is not None
                for pattern in _PERSONAL_LIFESPAN_EN
            )
        ):
            return True
    return False


def _unavailable_cross_chat_context_request(value: str) -> bool:
    """Match only a request to use unavailable material from another chat."""

    has_other_chat_reference = (
        _OTHER_CHAT_REFERENCE_ZH.search(value) is not None
        or _OTHER_CHAT_REFERENCE_EN.search(value) is not None
    )
    if not has_other_chat_reference:
        return False
    if (
        _NEGATED_CROSS_CHAT_REQUEST_ZH.search(value) is not None
        or _NEGATED_CROSS_CHAT_REQUEST_EN.search(value) is not None
    ):
        return False
    supplied_conditionally = (
        _CROSS_CHAT_CONDITIONAL_SUPPLY_ZH.search(value) is not None
        or _CROSS_CHAT_CONDITIONAL_SUPPLY_EN.search(value) is not None
    )
    if supplied_conditionally:
        return False
    if (
        (
            _CROSS_CHAT_ALREADY_SUPPLIED_ZH.search(value) is not None
            or _CROSS_CHAT_ALREADY_SUPPLIED_EN.search(value) is not None
        )
        or _CROSS_CHAT_MIXED_TASK_ZH.search(value) is not None
        or _CROSS_CHAT_MIXED_TASK_EN.search(value) is not None
    ):
        return False

    explicit_basis_request = (
        _CROSS_CHAT_BASIS_REQUEST_ZH.search(value) is not None
        or _CROSS_CHAT_BASIS_REQUEST_EN.search(value) is not None
    )
    has_request_action = (
        _CROSS_CHAT_REQUEST_ACTION_ZH.search(value) is not None
        or _CROSS_CHAT_REQUEST_ACTION_EN.search(value) is not None
    )
    capability_with_result = (
        _CROSS_CHAT_CAPABILITY_WITH_RESULT_ZH.search(value) is not None
        or _CROSS_CHAT_CAPABILITY_WITH_RESULT_EN.search(value) is not None
    )
    capability_only = (
        _CROSS_CHAT_CAPABILITY_ONLY_ZH.search(value) is not None
        or _CROSS_CHAT_CAPABILITY_ONLY_EN.search(value) is not None
    )
    if capability_only and not capability_with_result and not explicit_basis_request:
        return False
    return explicit_basis_request or has_request_action or capability_with_result


def bounded_response_candidate(user_message: str) -> BoundedResponseCandidate | None:
    """Return one fixed candidate only for a high-confidence finite match."""

    normalized = normalize_bounded_match_text(user_message)
    clauses = _bounded_clauses(normalized)
    if (
        _NEGATED_BOUNDED_REQUEST.search(normalized) is not None
        or _QUOTED_OR_FICTION_FRAME.search(normalized) is not None
        or _META_CLASSIFIER_QUESTION.search(normalized) is not None
        or _EDUCATIONAL_OR_META_FRAME.search(normalized) is not None
        or _PAIRED_QUOTE_FRAME.search(normalized) is not None
        or _THIRD_PARTY_SUPPORT_REQUEST.search(normalized) is not None
        or sum(clause.is_question for clause in clauses) > 1
    ):
        return None
    matched_kinds: list[BoundedResponseKind] = []
    if _unavailable_cross_chat_context_request(normalized):
        matched_kinds.append("unavailable_cross_chat_context")
    if _personal_lifespan_conversion(normalized):
        matched_kinds.append("personal_lifespan_conversion")
    if _single_chat_diagnostic_request(normalized):
        matched_kinds.append("single_chat_diagnostic_request")
    if _third_party_private_state_request(normalized):
        matched_kinds.append("third_party_private_state")

    # A fixed single-boundary candidate must not silently choose one intent over
    # another. Mixed requests keep the user's full message on the ordinary path.
    if len(matched_kinds) != 1:
        return None
    kind = matched_kinds[0]
    uses_chinese = _HAN_PATTERN.search(user_message) is not None
    return BoundedResponseCandidate(
        kind=kind,
        response=_RESPONSES[(kind, uses_chinese)],
    )
