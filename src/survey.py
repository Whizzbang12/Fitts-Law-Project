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
    "There are a total of 10 trials. You may take a break between trials. However, there are no pause option once you start a trial."
)

# question kinds: choice (single), text, multi (with optional other field)
QUESTIONS = (
    {
        "id": "name",
        "prompt": "What is your name?",
        "kind": "text",
        "placeholder": "Enter your name",
        "digits_only": False,
        "max_len": 60,
    },
    {
        "id": "gender",
        "prompt": "What is your gender?",
        "kind": "choice",
        "options": ("Male", "Female", "Other"),
        "other_option": "Other",
        "other_key": "gender_other",
        "other_placeholder": "Please specify",
    },
    {
        "id": "age",
        "prompt": "How old are you?",
        "kind": "text",
        "placeholder": "Enter your age (18-100)",
        "digits_only": True,
        "max_len": 3,
        "min_value": 18,
        "max_value": 100,
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
        "placeholder": "Enter hours per day (0-24)",
        "digits_only": True,
        "allow_decimal": True,
        "max_len": 5,
        "min_value": 0,
        "max_value": 24,
    },
    {
        "id": "input_device",
        "prompt": "Are you using a mouse or a trackpad for this study?",
        "kind": "choice",
        "options": ("Mouse", "Trackpad", "Other"),
        "other_option": "Other",
        "other_key": "input_device_other",
        "other_placeholder": "Please specify",
    },
    {
        "id": "mouse_model",
        "prompt": "What company or model is your mouse?",
        "kind": "text",
        "placeholder": "Example: Logitech MX Master",
        "digits_only": False,
        "max_len": 80,
        "requires": ("input_device", "Mouse"),
    },
    {
        "id": "machine_company",
        "prompt": "What company made the computer you are using?",
        "kind": "text",
        "placeholder": "Example: Dell, Apple, Lenovo",
        "digits_only": False,
        "max_len": 80,
        "requires": ("input_device", "Trackpad"),
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
        "name": "",
        "gender": None,
        "gender_other": "",
        "age": "",
        "handedness": None,
        "computer_hours": "",
        "input_device": None,
        "input_device_other": "",
        "mouse_model": "",
        "machine_company": "",
        "disabilities": set(),
        "disabilities_other": "",
    }


def question_is_visible(question, answers):
    requires = question.get("requires")
    if not requires:
        return True
    field, value = requires
    return answers.get(field) == value


def visible_questions(answers):
    """Questions shown for the current answers (e.g. mouse type only after Mouse)."""
    return [question for question in QUESTIONS if question_is_visible(question, answers)]


def sync_conditional_answers(answers, skipped):
    """Clear follow-ups that no longer apply."""
    device = answers.get("input_device")
    if device != "Mouse":
        answers["mouse_model"] = ""
        skipped.discard("mouse_model")
    if device != "Trackpad":
        answers["machine_company"] = ""
        skipped.discard("machine_company")


def text_in_range(question, value):
    """True when a typed answer is present and within any min/max limits."""
    text = (value or "").strip()
    if not text:
        return False
    if "min_value" not in question and "max_value" not in question:
        return True
    try:
        number = float(text) if question.get("allow_decimal") else int(text)
    except ValueError:
        return False
    if "min_value" in question and number < question["min_value"]:
        return False
    if "max_value" in question and number > question["max_value"]:
        return False
    return True


def validation_message(question, answers):
    """Hint shown when the typed value is present but out of range."""
    if question["kind"] != "text":
        return None
    value = (answers.get(question["id"]) or "").strip()
    if not value:
        return None
    if text_in_range(question, value):
        return None
    low = question.get("min_value")
    high = question.get("max_value")
    if low is not None and high is not None:
        return f"Please enter a value between {low} and {high}"
    return "Please enter a valid value"


def answer_is_complete(question, answers):
    kind = question["kind"]
    if kind == "choice":
        selected = answers.get(question["id"])
        if selected not in question["options"]:
            return False
        other_option = question.get("other_option")
        if other_option and selected == other_option:
            other_key = question.get("other_key", "gender_other")
            return bool((answers.get(other_key) or "").strip())
        return True
    if kind == "text":
        return text_in_range(question, answers.get(question["id"]))
    if kind == "multi":
        selected = answers.get("disabilities") or set()
        other = (answers.get("disabilities_other") or "").strip()
        return bool(selected) or bool(other)
    return False


def clear_answer(question, answers):
    """Reset a question's answer when the participant skips it."""
    blank = blank_answers()
    if question["kind"] == "multi":
        answers["disabilities"] = set()
        answers["disabilities_other"] = ""
        return
    answers[question["id"]] = blank[question["id"]]
    other_key = question.get("other_key")
    if other_key:
        answers[other_key] = ""


def format_disabilities(answers):
    selected = sorted(answers.get("disabilities") or set())
    other = (answers.get("disabilities_other") or "").strip()
    parts = list(selected)
    if other:
        parts.append(other)
    return "; ".join(parts) if parts else ""
