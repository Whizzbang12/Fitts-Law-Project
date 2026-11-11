"""Consent, demographics questions, and task instructions for participants."""

CONSENT_TITLE = "Consent"

CONSENT_TEXT = (
    'You are requested to participate in this study on target acquisition. '
    'The study should take between 5 to 10 minutes to complete. Participation '
    'is voluntary. You have the option to not respond to any questions. You may '
    'stop at any time. All information will remain anonymous. If you are willing '
    'to consent and continue then click the "I Consent" button. Else press "Esc" '
    'to exit.'
)

INSTRUCTIONS_TITLE = "Instructions"

INSTRUCTIONS_TEXT = (
    "Click the white circle in the middle to begin each task. A yellow circle "
    "will appear. Your goal is to click the yellow circle as quickly as possible. "
    "An error is a click when you miss the yellow circle. Select the white circle "
    "again to start the next task. There are a total of 32 tasks in a trial. "
    "There are a total of 10 trials."
)

# question kinds: choice (single), text, multi (with optional other field)
QUESTIONS = (
    {
        "id": "gender",
        "prompt": "What is your gender?",
        "kind": "choice",
        "options": ("Male", "Female", "Other"),
    },
    {
        "id": "age",
        "prompt": "How old are you?",
        "kind": "text",
        "placeholder": "Enter your age",
        "digits_only": True,
        "max_len": 3,
    },
    {
        "id": "handedness",
        "prompt": "Are you left handed or right handed?",
        "kind": "choice",
        "options": ("Left handed", "Right Handed"),
    },
    {
        "id": "computer_hours",
        "prompt": "How many hours do you spend using a computer every day?",
        "kind": "text",
        "placeholder": "Enter hours per day",
        "digits_only": True,
        "max_len": 3,
    },
    {
        "id": "disabilities",
        "prompt": "Do you have any disabilities? Feel free to provide the disability if it is not listed in the options.",
        "kind": "multi",
        "options": (
            "Hearing Impairments",
            "Vision Impairments",
            "Cognitive Difficulties",
            "Mobility Difficulties",
            "No",
        ),
        "other_placeholder": "Type a disability not listed",
        "none_option": "No",
    },
)


def wrap_text(font, text, max_width):
    """Split text into lines that fit within max_width pixels."""
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def blank_answers():
    return {
        "gender": None,
        "age": "",
        "handedness": None,
        "computer_hours": "",
        "disabilities": set(),
        "disabilities_other": "",
    }


def answer_is_complete(question, answers):
    kind = question["kind"]
    if kind == "choice":
        return answers.get(question["id"]) in question["options"]
    if kind == "text":
        value = (answers.get(question["id"]) or "").strip()
        return bool(value)
    if kind == "multi":
        selected = answers.get("disabilities") or set()
        other = (answers.get("disabilities_other") or "").strip()
        return bool(selected) or bool(other)
    return False


def format_disabilities(answers):
    selected = sorted(answers.get("disabilities") or set())
    other = (answers.get("disabilities_other") or "").strip()
    parts = list(selected)
    if other:
        parts.append(other)
    return "; ".join(parts) if parts else ""
