import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { SUPABASE_ANON_KEY, SUPABASE_URL } from "./supabase-config.js";
import * as study from "./study.js";

const screen = document.querySelector("#screen");
const canvas = document.querySelector("#task");
const ctx = canvas.getContext("2d");
const STORAGE_KEY = "fitts-web-session";

const configured = SUPABASE_URL.startsWith("https://") && !SUPABASE_URL.includes("YOUR_PROJECT") && !SUPABASE_ANON_KEY.includes("YOUR_ANON");
const supabase = configured ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

const state = {
    screen: "mode",
    mode: null,
    sessionNumber: null,
    token: null,
    trialNumber: 1,
    doneKeys: [],
    queue: [],
    current: null,
    path: 0,
    lastPoint: null,
    startedAt: 0,
    questionIndex: 0,
    answers: study.blankAnswers(),
    skipped: new Set(),
    backCount: 0,
    demographicsSaved: false,
    infoSaved: false,
    saving: false,
    error: "",
    buttons: [],
};

function persist() {
    if (!state.token) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
        mode: state.mode,
        sessionNumber: state.sessionNumber,
        token: state.token,
        trialNumber: state.trialNumber,
        doneKeys: state.doneKeys,
        questionIndex: state.questionIndex,
        answers: state.answers,
        skipped: [...state.skipped],
        backCount: state.backCount,
        demographicsSaved: state.demographicsSaved,
        infoSaved: state.infoSaved,
        screen: state.screen === "move" || state.screen === "center" || state.screen === "saving" ? "next" : state.screen,
    }));
}

function restore() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function applyUiScale() {
    document.documentElement.style.setProperty("--ui", String(study.uiScale(window.innerWidth, window.innerHeight)));
}

function systemInfo(scale) {
    const ua = navigator.userAgent;
    let osName = "Unknown";
    let osRelease = "";
    if (/Windows NT ([\d.]+)/.test(ua)) {
        osName = "Windows";
        osRelease = /Windows NT 10/.test(ua) ? "11 or 10" : RegExp.$1;
    } else if (/Mac OS X ([\d_]+)/.test(ua)) {
        osName = "MacOS";
        osRelease = RegExp.$1.replaceAll("_", ".");
    } else if (/Android ([\d.]+)/.test(ua)) {
        osName = "Android";
        osRelease = RegExp.$1;
    } else if (/Linux/.test(ua)) {
        osName = "Linux";
    }
    const data = navigator.userAgentData;
    return {
        os_name: data?.platform || osName,
        os_release: osRelease,
        os_version: ua,
        machine: navigator.platform || "",
        screen_width: window.innerWidth,
        screen_height: window.innerHeight,
        scale,
    };
}

async function call(fn, args) {
    const { error } = await supabase.rpc(fn, args);
    if (error) throw new Error(error.message);
}

async function claim(mode) {
    const { data, error } = await supabase.rpc("claim_session", { p_mode: mode });
    if (error) throw new Error(error.message);
    const row = Array.isArray(data) ? data[0] : data;
    return { sessionNumber: row.session_number, token: row.token };
}

function visible() {
    return study.visibleQuestions(state.answers);
}

function currentQuestion() {
    const questions = visible();
    if (state.questionIndex >= questions.length) state.questionIndex = questions.length - 1;
    return questions[Math.max(0, state.questionIndex)];
}

function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(window.innerWidth * dpr);
    canvas.height = Math.floor(window.innerHeight * dpr);
    canvas.style.width = `${window.innerWidth}px`;
    canvas.style.height = `${window.innerHeight}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function layout() {
    return {
        width: window.innerWidth,
        height: window.innerHeight,
        scale: study.layoutScale(window.innerWidth, window.innerHeight),
        center: [window.innerWidth / 2, window.innerHeight / 2],
    };
}

function targetCenter(direction, distance, view) {
    const offset = distance * view.scale;
    return direction === "left"
        ? [view.center[0] - offset, view.center[1]]
        : [view.center[0] + offset, view.center[1]];
}

function remaining() {
    const done = new Set(state.doneKeys);
    const tasks = study.allTargets().filter(([direction, distance, diameter]) => !done.has(study.conditionKey(direction, distance, diameter)));
    for (let i = tasks.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [tasks[i], tasks[j]] = [tasks[j], tasks[i]];
    }
    return tasks;
}

function renderMenu(html) {
    document.body.classList.remove("task");
    screen.innerHTML = html;
}

function button(id, label, extraClass = "") {
    return `<button id="${id}" class="${extraClass}" type="button">${label}</button>`;
}

function drawMenus() {
    applyUiScale();
    const saved = restore();
    if (state.screen === "mode") {
        const resume = saved && saved.screen !== "done"
            ? `<div class="choices">${button("continue", `Continue ${saved.mode === "test" ? "Test" : "Participant"} ${saved.sessionNumber}`)}${button("fresh", "Start a new session")}</div>`
            : `<div class="choices">${button("participant", "Participant")}${button("test", "Test")}</div>`;
        renderMenu(`
            <h1>What kind of session is this?</h1>
            <p class="muted">If you are told to participate in this project, make sure to click Participant.</p>
            ${resume}
            <p id="error" class="muted">${state.error}</p>
        `);
        return;
    }
    if (state.screen === "consent") {
        renderMenu(`
            <h1>Consent</h1>
            <p>${study.CONSENT_TEXT}</p>
            <p class="muted">Press Esc to exit without recording this participant.</p>
            <div class="dock">${button("consent", "I Consent")}</div>
            <p id="error">${state.error}</p>
        `);
        return;
    }
    if (state.screen === "survey") {
        const questions = visible();
        const question = currentQuestion();
        const complete = study.answerComplete(question, state.answers);
        const hint = study.validationMessage(question, state.answers);
        let body = "";
        if (question.kind === "choice" || question.kind === "multi") {
            const selected = question.kind === "multi" ? state.answers.disabilities : [state.answers[question.id]];
            body = `<div class="choices">${question.options.map((option) => button(`opt-${option}`, option, selected.includes(option) ? "choice selected" : "choice")).join("")}</div>`;
            if (question.kind === "choice" && state.answers[question.id] === question.otherOption) {
                body += `<input id="field" type="text" value="${escapeAttr(state.answers[question.otherKey] || "")}" placeholder="${question.otherPlaceholder}">`;
            }
            if (question.kind === "multi") {
                body += `<input id="field" type="text" value="${escapeAttr(state.answers.disabilities_other || "")}" placeholder="${question.otherPlaceholder}">`;
            }
        } else {
            body = `<input id="field" type="text" value="${escapeAttr(state.answers[question.id] || "")}" placeholder="${question.placeholder || ""}">`;
        }
        renderMenu(`
            <p class="muted">Question ${state.questionIndex + 1} of ${questions.length}</p>
            <p class="prompt">${question.prompt}</p>
            ${body}
            <p id="error" class="muted">${hint || state.error}</p>
            ${state.questionIndex > 0 ? button("back", "Back") : ""}
            <div class="dock">
                ${button("skip", "Skip", "secondary")}
                ${complete ? button("next", "Next") : ""}
            </div>
        `);
        const field = document.querySelector("#field");
        if (field) {
            field.focus();
            field.setSelectionRange(field.value.length, field.value.length);
            field.addEventListener("input", () => onField(question, field.value));
        }
        return;
    }
    if (state.screen === "instructions") {
        renderMenu(`
            <h1>Instructions</h1>
            <p>${study.INSTRUCTIONS_TEXT}</p>
            <div class="dock">${button("begin", "Begin Trial")}</div>
        `);
        return;
    }
    if (state.screen === "ready" || state.screen === "next") {
        const label = state.mode === "test" ? "Test" : "Participant";
        const action = state.screen === "ready" ? "start" : "next-trial";
        const text = state.screen === "ready" ? "Start" : "Next";
        renderMenu(`
            <h1>${label} ${state.sessionNumber}</h1>
            <p>Trial ${state.trialNumber} of ${study.TRIAL_COUNT}</p>
            <div class="dock">${button(action, text)}</div>
            <p id="error">${state.error}</p>
        `);
        return;
    }
    if (state.screen === "done") {
        const label = state.mode === "test" ? "Test" : "Participant";
        renderMenu(`<h1>${label} ${state.sessionNumber} finished all 10 trials.</h1><p class="muted">Results were saved. You can close this page.</p>`);
    }
}

function escapeAttr(value) {
    return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;");
}

function onField(question, value) {
    if (question.kind === "multi") {
        state.answers.disabilities_other = value;
        state.answers.disabilities = state.answers.disabilities.filter((item) => item !== "No");
    } else if (question.otherKey && state.answers[question.id] === question.otherOption) {
        state.answers[question.otherKey] = value;
    } else if (question.kind === "text") {
        if (question.digitsOnly) {
            value = question.allowDecimal ? value.replace(/[^0-9.]/g, "").replace(/(\..*)\./g, "$1") : value.replace(/\D/g, "");
        }
        state.answers[question.id] = value.slice(0, question.maxLen || 80);
    }
    persist();
    drawMenus();
}

function drawTask() {
    document.body.classList.add("task");
    resizeCanvas();
    const view = layout();
    ctx.clearRect(0, 0, view.width, view.height);
    ctx.fillStyle = "#121212";
    ctx.fillRect(0, 0, view.width, view.height);
    ctx.fillStyle = "#ffffff";
    ctx.font = `${Math.max(16, Math.round(24 * study.uiScale(view.width, view.height)))}px Segoe UI`;
    ctx.textAlign = "center";
    const showingTarget = state.screen === "move" || state.screen === "saving";
    ctx.fillText(showingTarget ? "Click the yellow circle" : "Click the white circle", view.center[0], 48);
    ctx.beginPath();
    ctx.arc(view.center[0], view.center[1], (study.CENTER_DIAMETER * view.scale) / 2, 0, Math.PI * 2);
    ctx.fill();
    if (showingTarget && state.current) {
        const [direction, distance, diameter] = state.current;
        const [x, y] = targetCenter(direction, distance, view);
        ctx.fillStyle = "#ffc107";
        ctx.beginPath();
        ctx.arc(x, y, (diameter * view.scale) / 2, 0, Math.PI * 2);
        ctx.fill();
    }
    if (state.error) {
        ctx.fillStyle = "#ffb4b4";
        ctx.fillText(state.error, view.center[0], view.height - 40);
    }
}

function show() {
    if (state.screen === "center" || state.screen === "move" || state.screen === "saving") drawTask();
    else drawMenus();
}

async function choose(mode) {
    state.error = "";
    try {
        const claimed = await claim(mode);
        state.mode = mode;
        state.sessionNumber = claimed.sessionNumber;
        state.token = claimed.token;
        state.trialNumber = 1;
        state.doneKeys = [];
        state.answers = study.blankAnswers();
        state.skipped = new Set();
        state.questionIndex = 0;
        state.backCount = 0;
        state.demographicsSaved = false;
        state.infoSaved = false;
        state.screen = mode === "participant" ? "consent" : "ready";
        persist();
        show();
    } catch (error) {
        state.error = error.message;
        show();
    }
}

function continueSaved(saved) {
    Object.assign(state, {
        mode: saved.mode,
        sessionNumber: saved.sessionNumber,
        token: saved.token,
        trialNumber: saved.trialNumber,
        doneKeys: saved.doneKeys || [],
        questionIndex: saved.questionIndex || 0,
        answers: { ...study.blankAnswers(), ...(saved.answers || {}) },
        skipped: new Set(saved.skipped || []),
        backCount: saved.backCount || 0,
        demographicsSaved: Boolean(saved.demographicsSaved),
        infoSaved: Boolean(saved.infoSaved),
        screen: saved.screen || "ready",
        error: "",
    });
    show();
}

async function abandon() {
    if (!state.token || state.demographicsSaved || state.doneKeys.length) return;
    const body = JSON.stringify({ p_mode: state.mode, p_session: state.sessionNumber, p_token: state.token });
    localStorage.removeItem(STORAGE_KEY);
    try {
        await fetch(`${SUPABASE_URL}/rest/v1/rpc/abandon_session`, {
            method: "POST",
            headers: {
                apikey: SUPABASE_ANON_KEY,
                Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
                "Content-Type": "application/json",
            },
            body,
            keepalive: true,
        });
    } catch {
        /* leaving the page */
    }
    state.token = null;
}

async function saveSurvey() {
    study.syncConditional(state.answers, state.skipped);
    const visibleIds = new Set(visible().map((question) => question.id));
    const skipped = study.QUESTIONS.map((question) => question.id).filter((id) => state.skipped.has(id) && visibleIds.has(id));
    const blank = (value) => {
        const text = value === null || value === undefined ? "" : String(value).trim();
        return text || null;
    };
    await call("save_demographics", {
        p_session: state.sessionNumber,
        p_token: state.token,
        p_name: blank(state.answers.name),
        p_gender: blank(state.answers.gender),
        p_gender_other: blank(state.answers.gender === "Other" ? state.answers.gender_other : ""),
        p_age: blank(state.answers.age),
        p_handedness: blank(state.answers.handedness),
        p_computer_hours: blank(state.answers.computer_hours),
        p_input_device: blank(state.answers.input_device),
        p_input_device_other: blank(state.answers.input_device === "Other" ? state.answers.input_device_other : ""),
        p_mouse_model: blank(state.answers.input_device === "Mouse" ? state.answers.mouse_model : ""),
        p_machine_company: blank(state.answers.input_device === "Trackpad" ? state.answers.machine_company : ""),
        p_disabilities: blank(study.formatDisabilities(state.answers)),
        p_skipped: blank(skipped.join(", ")),
        p_back_count: state.backCount,
    });
    state.demographicsSaved = true;
    state.screen = "instructions";
    persist();
}

async function saveTarget(click) {
    const view = layout();
    const [direction, distance, diameter] = state.current;
    const center = targetCenter(direction, distance, view);
    const offset = Math.hypot(click[0] - center[0], click[1] - center[1]);
    const radius = (diameter * view.scale) / 2;
    const hit = offset <= radius;
    const error = hit ? 0 : offset - radius;
    if (state.doneKeys.length >= 32) return;
    const targetNumber = state.doneKeys.length + 1;
    await call("insert_trial", {
        p_mode: state.mode,
        p_session: state.sessionNumber,
        p_token: state.token,
        p_trial: state.trialNumber,
        p_target: targetNumber,
        p_direction: direction,
        p_distance: distance,
        p_diameter: diameter,
        p_id: study.indexOfDifficulty(distance, diameter),
        p_mt: performance.now() - state.startedAt,
        p_path: state.path / view.scale,
        p_hit: hit ? 1 : 0,
        p_error: error / view.scale,
        p_scale: view.scale,
        p_path_raw: state.path,
        p_error_raw: error,
    });
    if (!state.infoSaved) {
        const info = systemInfo(view.scale);
        await call("save_session_info", {
            p_mode: state.mode,
            p_session: state.sessionNumber,
            p_token: state.token,
            p_os_name: info.os_name,
            p_os_release: info.os_release,
            p_os_version: info.os_version,
            p_machine: info.machine,
            p_width: info.screen_width,
            p_height: info.screen_height,
            p_scale: info.scale,
        });
        state.infoSaved = true;
    }
    state.doneKeys.push(study.conditionKey(direction, distance, diameter));
    state.current = null;
    if (state.queue.length) {
        state.screen = "center";
    } else if (state.trialNumber >= study.TRIAL_COUNT) {
        state.screen = "done";
        localStorage.removeItem(STORAGE_KEY);
    } else {
        state.trialNumber += 1;
        state.doneKeys = [];
        state.screen = "next";
    }
    persist();
}

screen.addEventListener("click", async (event) => {
    const id = event.target.id;
    if (!id) return;
    state.error = "";
    if (id === "participant" || id === "test") {
        await document.documentElement.requestFullscreen?.().catch(() => {});
        await choose(id === "test" ? "test" : "participant");
        return;
    }
    if (id === "continue") {
        continueSaved(restore());
        return;
    }
    if (id === "fresh") {
        localStorage.removeItem(STORAGE_KEY);
        show();
        return;
    }
    if (id === "consent") {
        state.screen = "survey";
        show();
        return;
    }
    if (id === "skip") {
        const question = currentQuestion();
        study.clearAnswer(question, state.answers);
        state.skipped.add(question.id);
        advance();
        return;
    }
    if (id === "back") {
        if (state.questionIndex > 0) {
            state.backCount += 1;
            state.questionIndex -= 1;
            study.syncConditional(state.answers, state.skipped);
        }
        persist();
        show();
        return;
    }
    if (id === "next") {
        const question = currentQuestion();
        if (!study.answerComplete(question, state.answers)) return;
        state.skipped.delete(question.id);
        advance();
        return;
    }
    if (id.startsWith("opt-")) {
        const option = id.slice(4);
        const question = currentQuestion();
        if (question.kind === "choice") {
            state.answers[question.id] = option;
            if (question.otherKey && option !== question.otherOption) state.answers[question.otherKey] = "";
            if (question.id === "input_device") study.syncConditional(state.answers, state.skipped);
        } else {
            const selected = new Set(state.answers.disabilities);
            if (option === question.noneOption) {
                state.answers.disabilities = selected.has(option) ? [] : [option];
                if (state.answers.disabilities.length) state.answers.disabilities_other = "";
            } else {
                selected.delete(question.noneOption);
                if (selected.has(option)) selected.delete(option);
                else selected.add(option);
                state.answers.disabilities = [...selected];
            }
        }
        persist();
        show();
        return;
    }
    if (id === "begin" || id === "start") {
        state.screen = "next";
        persist();
        show();
        return;
    }
    if (id === "next-trial") {
        state.queue = remaining();
        state.screen = state.queue.length ? "center" : "done";
        persist();
        show();
    }
});

function advance() {
    study.syncConditional(state.answers, state.skipped);
    if (state.questionIndex + 1 < visible().length) {
        state.questionIndex += 1;
        persist();
        show();
        return;
    }
    saveSurvey().then(show).catch((error) => {
        state.error = error.message;
        show();
    });
}

canvas.addEventListener("mousemove", (event) => {
    if (state.screen !== "move" || !state.lastPoint) return;
    const point = [event.offsetX, event.offsetY];
    state.path += Math.hypot(point[0] - state.lastPoint[0], point[1] - state.lastPoint[1]);
    state.lastPoint = point;
});

canvas.addEventListener("click", async (event) => {
    if (state.saving || state.doneKeys.length >= 32) return;
    const view = layout();
    const point = [event.offsetX, event.offsetY];
    const centerDistance = Math.hypot(point[0] - view.center[0], point[1] - view.center[1]);
    if (state.screen === "center" && centerDistance <= (study.CENTER_DIAMETER * view.scale) / 2) {
        if (!state.queue.length) return;
        state.current = state.queue.shift();
        state.path = 0;
        state.lastPoint = point;
        state.startedAt = performance.now();
        state.screen = "move";
        show();
        return;
    }
    // One click per yellow circle. A click on the white circle is a miss.
    if (state.screen === "move" && state.current) {
        state.saving = true;
        state.screen = "saving";
        state.error = "";
        try {
            await saveTarget(point);
        } catch (error) {
            state.error = error.message;
            state.screen = "move";
        } finally {
            state.saving = false;
        }
        show();
    }
});

window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (state.screen === "consent" || state.screen === "survey") {
        abandon().finally(() => {
            state.screen = "mode";
            state.mode = null;
            show();
        });
    }
});

window.addEventListener("pagehide", () => {
    if (!state.token || state.demographicsSaved || state.doneKeys.length) return;
    abandon();
});

window.addEventListener("resize", () => {
    applyUiScale();
    if (state.screen === "center" || state.screen === "move") drawTask();
});

if (!configured) {
    screen.innerHTML = "<h1>Setup needed</h1><p>Put your Supabase URL and anon key in web/supabase-config.js, and run supabase/schema.sql in the Supabase SQL editor.</p>";
} else {
    applyUiScale();
    show();
}
