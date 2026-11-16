export const DISTANCES = [150, 380, 620, 884];
export const DIAMETERS = [24, 48, 84, 120];
export const DIRECTIONS = ["left", "right"];
export const TRIAL_COUNT = 10;
export const CENTER_DIAMETER = 80;
export const EDGE_MARGIN = 16;
export const UI_LIMITS = [0.5, 2];

export const CONSENT_TEXT =
    'You are requested to participate in this study on target acquisition. ' +
    'The study should take between 5 to 10 minutes to complete. Participation ' +
    'is voluntary. You have the option to not respond to any questions. You may ' +
    'stop at any time. All information will remain anonymous. If you are willing ' +
    'to consent and continue then click the "I Consent" button. Else press "Esc" ' +
    'to exit.';

export const INSTRUCTIONS_TEXT =
    "Click the white circle in the middle to begin each task. A yellow circle " +
    "will appear. Your goal is to click the yellow circle as quickly as possible. " +
    "An error is a click when you miss the yellow circle. Select the white circle " +
    "again to start the next task. There are a total of 32 tasks in a trial. " +
    "There are a total of 10 trials. You may take a break between trials. However, there are no pause option once you start a trial.";

export const QUESTIONS = [
    { id: "name", prompt: "What is your name?", kind: "text", placeholder: "Enter your name", digitsOnly: false, maxLen: 60 },
    { id: "gender", prompt: "What is your gender?", kind: "choice", options: ["Male", "Female", "Other"], otherOption: "Other", otherKey: "gender_other", otherPlaceholder: "Please specify" },
    { id: "age", prompt: "How old are you?", kind: "text", placeholder: "Enter your age (18-100)", digitsOnly: true, maxLen: 3, minValue: 18, maxValue: 100 },
    { id: "handedness", prompt: "Are you left handed or right handed?", kind: "choice", options: ["Left handed", "Right Handed"] },
    { id: "computer_hours", prompt: "How many hours do you spend using a computer every day?", kind: "text", placeholder: "Enter hours per day (0-24)", digitsOnly: true, allowDecimal: true, maxLen: 5, minValue: 0, maxValue: 24 },
    { id: "input_device", prompt: "Are you using a mouse or a trackpad for this study?", kind: "choice", options: ["Mouse", "Trackpad", "Other"], otherOption: "Other", otherKey: "input_device_other", otherPlaceholder: "Please specify" },
    { id: "mouse_model", prompt: "What company or model is your mouse?", kind: "text", placeholder: "Example: Logitech MX Master", digitsOnly: false, maxLen: 80, requires: ["input_device", "Mouse"] },
    { id: "machine_company", prompt: "What company made the computer you are using?", kind: "text", placeholder: "Example: Dell, Apple, Lenovo", digitsOnly: false, maxLen: 80, requires: ["input_device", "Trackpad"] },
    { id: "disabilities", prompt: "Do you have any disabilities? Feel free to provide the disability if it is not listed in the options.", kind: "multi", options: ["Hearing Impairments", "Vision Impairments", "Cognitive Difficulties", "Mobility Difficulties", "No"], otherPlaceholder: "Type a disability not listed", noneOption: "No" },
];

export function indexOfDifficulty(distance, diameter) {
    return Math.log2(distance / diameter + 1);
}

export function allTargets() {
    const tasks = [];
    for (const direction of DIRECTIONS) {
        for (const distance of DISTANCES) {
            for (const diameter of DIAMETERS) {
                tasks.push([direction, distance, diameter]);
            }
        }
    }
    return tasks;
}

export function requiredHalfWidth() {
    return Math.max(...DISTANCES) + Math.max(...DIAMETERS) / 2 + EDGE_MARGIN;
}

export function requiredHalfHeight() {
    return Math.max(...DIAMETERS) / 2 + EDGE_MARGIN;
}

export function layoutScale(width, height) {
    return Math.min(1, width / (2 * requiredHalfWidth()), height / (2 * requiredHalfHeight()));
}

export function uiScale(width, height) {
    const factor = Math.min(width / 1920, height / 1080);
    return Math.max(UI_LIMITS[0], Math.min(UI_LIMITS[1], factor));
}

export function blankAnswers() {
    return {
        name: "",
        gender: null,
        gender_other: "",
        age: "",
        handedness: null,
        computer_hours: "",
        input_device: null,
        input_device_other: "",
        mouse_model: "",
        machine_company: "",
        disabilities: [],
        disabilities_other: "",
    };
}

export function questionVisible(question, answers) {
    if (!question.requires) return true;
    return answers[question.requires[0]] === question.requires[1];
}

export function visibleQuestions(answers) {
    return QUESTIONS.filter((question) => questionVisible(question, answers));
}

export function syncConditional(answers, skipped) {
    if (answers.input_device !== "Mouse") {
        answers.mouse_model = "";
        skipped.delete("mouse_model");
    }
    if (answers.input_device !== "Trackpad") {
        answers.machine_company = "";
        skipped.delete("machine_company");
    }
}

export function textInRange(question, value) {
    const text = (value || "").trim();
    if (!text) return false;
    if (question.minValue === undefined && question.maxValue === undefined) return true;
    const number = question.allowDecimal ? Number(text) : Number.parseInt(text, 10);
    if (Number.isNaN(number)) return false;
    if (question.minValue !== undefined && number < question.minValue) return false;
    if (question.maxValue !== undefined && number > question.maxValue) return false;
    return true;
}

export function validationMessage(question, answers) {
    if (question.kind !== "text") return "";
    const value = (answers[question.id] || "").trim();
    if (!value || textInRange(question, value)) return "";
    if (question.minValue !== undefined && question.maxValue !== undefined) {
        return `Please enter a value between ${question.minValue} and ${question.maxValue}`;
    }
    return "Please enter a valid value";
}

export function answerComplete(question, answers) {
    if (question.kind === "choice") {
        if (!question.options.includes(answers[question.id])) return false;
        if (question.otherOption && answers[question.id] === question.otherOption) {
            return Boolean((answers[question.otherKey] || "").trim());
        }
        return true;
    }
    if (question.kind === "text") return textInRange(question, answers[question.id]);
    if (question.kind === "multi") {
        return answers.disabilities.length > 0 || Boolean((answers.disabilities_other || "").trim());
    }
    return false;
}

export function clearAnswer(question, answers) {
    const blank = blankAnswers();
    if (question.kind === "multi") {
        answers.disabilities = [];
        answers.disabilities_other = "";
        return;
    }
    answers[question.id] = blank[question.id];
    if (question.otherKey) answers[question.otherKey] = "";
}

export function formatDisabilities(answers) {
    const parts = [...answers.disabilities].sort();
    const other = (answers.disabilities_other || "").trim();
    if (other) parts.push(other);
    return parts.join("; ");
}

export function conditionKey(direction, distance, diameter) {
    return `${direction}|${distance}|${diameter}`;
}
