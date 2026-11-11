"""Fullscreen pointing task for participants and separate test runs."""

import math
import os
import random
from time import perf_counter

# Use the monitor's real pixel size on Windows (needed for 2560x1600 and similar).
os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

import pygame

import config
import survey
from analysis import build_results
from database import Database


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _open_fullscreen():
    """Open fullscreen using the current display's pixel size."""
    pygame.display.init()
    info = pygame.display.Info()
    width = info.current_w or 1920
    height = info.current_h or 1080
    screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    return screen, screen.get_size()


class FittsApp:
    def __init__(self):
        self.database = None
        self.mode = None
        self.paths = None
        self.saved_any = False
        pygame.init()
        self.screen, (self.width, self.height) = _open_fullscreen()
        pygame.display.set_caption("Fitts Law")
        pygame.mouse.set_visible(True)
        self.center = (self.width // 2, self.height // 2)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 36)
        self.small_font = pygame.font.SysFont("segoeui", 24)
        self.state = "mode"
        self.participant = ""
        self.session_number = None
        self.unfinished_number = None
        self.trial_number = 1
        self.queue = []
        self.current = None
        self.path_length = 0.0
        self.last_point = None
        self.started_at = None
        self.running = True
        self.question_index = 0
        self.answers = survey.blank_answers()
        self.text_focus = None
        self._hit_rects = {}
        if not config.screen_can_show_targets(self.width, self.height):
            self.state = "too_small"

    def close(self):
        if self.database is not None:
            self.database.close()
            self.database = None
        pygame.quit()

    def label(self):
        return config.mode_label(self.mode)

    def reset_survey(self):
        self.question_index = 0
        self.answers = survey.blank_answers()
        self.text_focus = None

    def remaining_targets(self):
        done = self.database.completed_conditions(self.session_number, self.trial_number)
        done_normalized = {
            (direction, int(distance), int(diameter))
            for direction, distance, diameter in done
        }
        remaining = [
            task
            for task in config.all_targets()
            if (task[0], int(task[1]), int(task[2])) not in done_normalized
        ]
        random.shuffle(remaining)
        return remaining

    def target_center(self, direction, distance):
        x, y = self.center
        if direction == "left":
            return (x - distance, y)
        return (x + distance, y)

    def add_sample(self, point):
        if self.last_point is None:
            self.last_point = point
            return
        if point != self.last_point:
            self.path_length += _distance(self.last_point, point)
            self.last_point = point

    def save_current(self, click_point):
        direction, distance, diameter = self.current
        radius = diameter / 2
        center = self.target_center(direction, distance)
        self.add_sample(click_point)
        offset = _distance(click_point, center)
        hit = offset <= radius
        error_distance = 0.0 if hit else offset - radius
        target_number = self.database.target_count(self.session_number, self.trial_number) + 1
        self.database.insert_target(
            self.session_number,
            {
                "trial_number": self.trial_number,
                "target_number": target_number,
                "direction": direction,
                "distance_px": distance,
                "diameter_px": diameter,
                "id_bits": config.index_of_difficulty(distance, diameter),
                "mt_ms": (perf_counter() - self.started_at) * 1000,
                "path_length_px": self.path_length,
                "hit": 1 if hit else 0,
                "error_distance_px": error_distance,
            },
        )
        self.saved_any = True
        self.current = None
        self.finish_queue_or_trial()

    def choose_mode(self, mode):
        self.mode = mode
        self.paths = config.paths_for(mode)
        self.database = Database(self.paths["db"], mode)
        self.unfinished_number = self.database.latest_unfinished()
        if self.unfinished_number is not None:
            self.state = "resume"
        else:
            self.start_new_session()

    def start_new_session(self):
        self.session_number = self.database.next_session_number()
        self.participant = str(self.session_number)
        self.trial_number = 1
        if self.mode == config.MODE_PARTICIPANT:
            self.reset_survey()
            self.state = "consent"
        else:
            # Trial table is created only when the first target is saved.
            self.state = "ready"

    def continue_session(self, number):
        self.session_number = number
        self.participant = str(number)
        trial_number = self.database.next_trial_number(self.session_number)
        if trial_number is None:
            self.start_new_session()
            return
        self.trial_number = trial_number
        if self.mode == config.MODE_PARTICIPANT and self.database.target_count(number) == 0:
            if self.database.has_demographics(number):
                self.state = "instructions"
            else:
                self.reset_survey()
                self.database.ensure_session(number)
                self.state = "survey"
            return
        self.state = "ready"

    def abort_without_record(self):
        """Leave with no participant row kept (consent/survey decline)."""
        if self.database is not None and self.session_number is not None:
            if self.state in ("consent", "survey"):
                self.database.delete_session(self.session_number)
        self.running = False

    def start_trial_targets(self):
        self.queue = self.remaining_targets()
        if not self.queue:
            self.advance_trial()
            return
        self.state = "center"

    def advance_trial(self):
        if self.trial_number >= config.TRIAL_COUNT:
            self.state = "done"
            return
        self.trial_number += 1
        self.state = "next"

    def finish_queue_or_trial(self):
        if self.queue:
            self.state = "center"
        else:
            self.advance_trial()

    def current_question(self):
        return survey.QUESTIONS[self.question_index]

    def save_survey_and_continue(self):
        payload = {
            "gender": self.answers["gender"],
            "age": self.answers["age"],
            "handedness": self.answers["handedness"],
            "computer_hours": self.answers["computer_hours"],
            "disabilities": survey.format_disabilities(self.answers),
        }
        self.database.save_demographics(self.session_number, payload)
        self.state = "instructions"

    def draw_text(self, text, y, font=None, color=config.TEXT_COLOR):
        font = self.font if font is None else font
        image = font.render(text, True, color)
        rect = image.get_rect(center=(self.center[0], y))
        self.screen.blit(image, rect)
        return rect

    def draw_wrapped(self, text, y, font=None, color=config.TEXT_COLOR, max_width=None, line_gap=8):
        font = self.font if font is None else font
        max_width = max_width or int(self.width * 0.7)
        lines = survey.wrap_text(font, text, max_width)
        line_height = font.get_height() + line_gap
        for index, line in enumerate(lines):
            self.draw_text(line, y + index * line_height, font, color)
        return len(lines) * line_height

    def wrapped_height(self, text, font=None, max_width=None, line_gap=8):
        font = self.font if font is None else font
        max_width = max_width or int(self.width * 0.7)
        lines = survey.wrap_text(font, text, max_width)
        return len(lines) * (font.get_height() + line_gap)

    def button(self, text, center, size=(320, 70), selected=False):
        rect = pygame.Rect(0, 0, size[0], size[1])
        rect.center = center
        fill = (70, 120, 70) if selected else config.BUTTON_COLOR
        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        if selected:
            pygame.draw.rect(self.screen, (180, 255, 180), rect, width=3, border_radius=10)
        label = self.font.render(text, True, config.BUTTON_TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        return rect

    def bottom_right_button(self, text, size=(280, 70), key="action"):
        margin = 48
        rect = pygame.Rect(0, 0, size[0], size[1])
        rect.bottomright = (self.width - margin, self.height - margin)
        pygame.draw.rect(self.screen, config.BUTTON_COLOR, rect, border_radius=10)
        label = self.font.render(text, True, config.BUTTON_TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        self._hit_rects[key] = rect
        return rect

    def text_field(self, value, center, size=(460, 64), placeholder="", key="field"):
        rect = pygame.Rect(0, 0, size[0], size[1])
        rect.center = center
        pygame.draw.rect(self.screen, config.FIELD_COLOR, rect, border_radius=8)
        border = config.BUTTON_COLOR if self.text_focus == key else config.FIELD_BORDER
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
        shown = value if value else placeholder
        color = config.TEXT_COLOR if value else config.MUTED_TEXT
        label = self.small_font.render(shown, True, color)
        self.screen.blit(label, label.get_rect(midleft=(rect.left + 18, rect.centery)))
        self._hit_rects[key] = rect
        return rect

    def draw_consent(self):
        self._hit_rects = {}
        max_width = int(self.width * 0.68)
        title_h = self.font.get_height()
        body_h = self.wrapped_height(
            survey.CONSENT_TEXT, self.small_font, max_width=max_width, line_gap=12
        )
        hint_h = self.small_font.get_height()
        block_h = title_h + 28 + body_h + 28 + hint_h
        top = self.center[1] - block_h // 2
        self.draw_text(survey.CONSENT_TITLE, top + title_h // 2)
        self.draw_wrapped(
            survey.CONSENT_TEXT,
            top + title_h + 28,
            self.small_font,
            config.TEXT_COLOR,
            max_width=max_width,
            line_gap=12,
        )
        self.draw_text(
            'Press Esc to exit without recording this participant.',
            top + title_h + 28 + body_h + 28 + hint_h // 2,
            self.small_font,
            config.MUTED_TEXT,
        )
        self.bottom_right_button("I Consent", size=(280, 70), key="consent")

    def draw_survey(self):
        self._hit_rects = {}
        question = self.current_question()
        max_width = int(self.width * 0.68)
        progress = f"Question {self.question_index + 1} of {len(survey.QUESTIONS)}"
        prompt_h = self.wrapped_height(question["prompt"], self.font, max_width=max_width, line_gap=10)

        option_count = len(question.get("options", ()))
        if question["kind"] == "choice":
            options_h = option_count * 78
            field_h = 0
        elif question["kind"] == "text":
            options_h = 0
            field_h = 80
        else:
            options_h = option_count * 70
            field_h = 88

        block_h = 36 + prompt_h + 36 + options_h + field_h
        top = max(48, self.center[1] - block_h // 2)
        self.draw_text(progress, top + 12, self.small_font, config.MUTED_TEXT)
        prompt_top = top + 44
        self.draw_wrapped(
            question["prompt"],
            prompt_top,
            self.font,
            config.TEXT_COLOR,
            max_width=max_width,
            line_gap=10,
        )
        y = prompt_top + prompt_h + 36

        if question["kind"] == "choice":
            for option in question["options"]:
                selected = self.answers[question["id"]] == option
                self._hit_rects[f"opt:{option}"] = self.button(
                    option,
                    (self.center[0], y + 28),
                    size=(440, 60),
                    selected=selected,
                )
                y += 78
        elif question["kind"] == "text":
            field_key = question["id"]
            self.text_field(
                self.answers[field_key],
                (self.center[0], y + 32),
                placeholder=question.get("placeholder", ""),
                key=field_key,
            )
            self.text_focus = field_key
        elif question["kind"] == "multi":
            for option in question["options"]:
                selected = option in self.answers["disabilities"]
                self._hit_rects[f"opt:{option}"] = self.button(
                    option,
                    (self.center[0], y + 26),
                    size=(520, 56),
                    selected=selected,
                )
                y += 70
            self.text_field(
                self.answers["disabilities_other"],
                (self.center[0], y + 34),
                size=(520, 58),
                placeholder=question.get("other_placeholder", ""),
                key="disabilities_other",
            )

        if survey.answer_is_complete(question, self.answers):
            self.bottom_right_button("Next", size=(220, 70), key="next")
        else:
            hint = self.small_font.render("Answer required to continue", True, config.MUTED_TEXT)
            hint_rect = hint.get_rect(bottomright=(self.width - 48, self.height - 48))
            self.screen.blit(hint, hint_rect)

    def draw_instructions(self):
        self._hit_rects = {}
        max_width = int(self.width * 0.68)
        title_h = self.font.get_height()
        body_h = self.wrapped_height(
            survey.INSTRUCTIONS_TEXT, self.small_font, max_width=max_width, line_gap=12
        )
        block_h = title_h + 28 + body_h
        top = self.center[1] - block_h // 2
        self.draw_text(survey.INSTRUCTIONS_TITLE, top + title_h // 2)
        self.draw_wrapped(
            survey.INSTRUCTIONS_TEXT,
            top + title_h + 28,
            self.small_font,
            config.TEXT_COLOR,
            max_width=max_width,
            line_gap=12,
        )
        self.bottom_right_button("Begin Trial", size=(300, 70), key="begin")

    def draw(self):
        self.screen.fill(config.BACKGROUND)
        if self.state == "too_small":
            need_w = int(config.required_half_width() * 2)
            need_h = int(config.required_half_height() * 2)
            self.draw_text(
                f"This display is {self.width}x{self.height} px.",
                self.center[1] - 50,
            )
            self.draw_text(
                f"Distances are fixed in pixels and need at least {need_w}x{need_h}.",
                self.center[1],
                self.small_font,
            )
            self.draw_text("Press Esc to close.", self.center[1] + 50, self.small_font)
        elif self.state == "mode":
            self.draw_text("What kind of session is this?", self.center[1] - 120)
            self.draw_text(
                "Participant and Test data are stored separately.",
                self.center[1] - 70,
                self.small_font,
                config.MUTED_TEXT,
            )
            self.button("Participant", (self.center[0], self.center[1] - 10))
            self.button("Test", (self.center[0], self.center[1] + 90))
        elif self.state == "resume":
            label = self.label()
            self.draw_text(f"{label} {self.unfinished_number} is unfinished.", self.center[1] - 110)
            self.draw_text(
                "Continue that session, or start the next number.",
                self.center[1] - 60,
                self.small_font,
                config.MUTED_TEXT,
            )
            self.button(
                f"Continue {label} {self.unfinished_number}",
                (self.center[0], self.center[1] + 10),
                size=(420, 70),
            )
            self.button(
                f"Start {label} {self.database.next_session_number()}",
                (self.center[0], self.center[1] + 110),
                size=(420, 70),
            )
        elif self.state == "consent":
            self.draw_consent()
        elif self.state == "survey":
            self.draw_survey()
        elif self.state == "instructions":
            self.draw_instructions()
        elif self.state == "ready":
            label = self.label()
            self.draw_text(f"You are {label} {self.session_number}", self.center[1] - 80)
            if self.database.target_count(self.session_number):
                self.draw_text(
                    f"Continuing from Trial {self.trial_number} of {config.TRIAL_COUNT}",
                    self.center[1] - 20,
                    self.small_font,
                    config.MUTED_TEXT,
                )
            else:
                self.draw_text(
                    f"This session will run {config.TRIAL_COUNT} trials.",
                    self.center[1] - 20,
                    self.small_font,
                    config.MUTED_TEXT,
                )
            self.button("Start", (self.center[0], self.center[1] + 70))
        elif self.state == "next":
            label = self.label()
            self.draw_text(f"{label} {self.session_number}", 48, self.small_font, config.MUTED_TEXT)
            done = self.database.target_count(self.session_number, self.trial_number)
            self.draw_text(f"Trial {self.trial_number} of {config.TRIAL_COUNT}", self.center[1] - 40)
            if done:
                self.draw_text("Continuing this trial", self.center[1] + 10, self.small_font)
            self.button("Next", (self.center[0], self.center[1] + 80), size=(220, 70))
        elif self.state == "center":
            self.draw_text("Click the white circle", 48, self.small_font)
            pygame.draw.circle(
                self.screen,
                config.CENTER_COLOR,
                self.center,
                config.CENTER_DIAMETER // 2,
            )
        elif self.state == "move":
            self.draw_text("Click the yellow circle", 48, self.small_font)
            pygame.draw.circle(
                self.screen,
                config.CENTER_COLOR,
                self.center,
                config.CENTER_DIAMETER // 2,
            )
            direction, distance, diameter = self.current
            pygame.draw.circle(
                self.screen,
                config.TARGET_COLOR,
                self.target_center(direction, distance),
                diameter // 2,
            )
        elif self.state == "done":
            label = self.label()
            self.draw_text(f"{label} {self.session_number} finished all 10 trials.", self.center[1] - 40)
            self.draw_text("Results were saved. Press Esc to close.", self.center[1] + 30, self.small_font)
        pygame.display.flip()

    def on_survey_click(self, point):
        question = self.current_question()
        for key, rect in self._hit_rects.items():
            if not rect.collidepoint(point):
                continue
            if key == "next":
                if not survey.answer_is_complete(question, self.answers):
                    return
                if self.question_index + 1 < len(survey.QUESTIONS):
                    self.question_index += 1
                    nxt = survey.QUESTIONS[self.question_index]
                    self.text_focus = nxt["id"] if nxt["kind"] == "text" else None
                else:
                    self.save_survey_and_continue()
                return
            if key.startswith("opt:"):
                option = key[4:]
                if question["kind"] == "choice":
                    self.answers[question["id"]] = option
                elif question["kind"] == "multi":
                    none_option = question.get("none_option")
                    selected = self.answers["disabilities"]
                    if option == none_option:
                        selected.clear()
                        selected.add(option)
                        self.answers["disabilities_other"] = ""
                    else:
                        selected.discard(none_option)
                        if option in selected:
                            selected.remove(option)
                        else:
                            selected.add(option)
                return
            if key in self.answers or key == "disabilities_other":
                self.text_focus = key
                return

    def on_click(self, point):
        if self.state == "mode":
            participant_btn = pygame.Rect(0, 0, 320, 70)
            participant_btn.center = (self.center[0], self.center[1] - 10)
            test_btn = pygame.Rect(0, 0, 320, 70)
            test_btn.center = (self.center[0], self.center[1] + 90)
            if participant_btn.collidepoint(point):
                self.choose_mode(config.MODE_PARTICIPANT)
            elif test_btn.collidepoint(point):
                self.choose_mode(config.MODE_TEST)
            return
        if self.state == "resume":
            continue_btn = pygame.Rect(0, 0, 420, 70)
            continue_btn.center = (self.center[0], self.center[1] + 10)
            new_btn = pygame.Rect(0, 0, 420, 70)
            new_btn.center = (self.center[0], self.center[1] + 110)
            if continue_btn.collidepoint(point):
                self.continue_session(self.unfinished_number)
            elif new_btn.collidepoint(point):
                self.start_new_session()
            return
        if self.state == "consent":
            consent = self._hit_rects.get("consent")
            if consent and consent.collidepoint(point):
                self.database.ensure_session(self.session_number)
                self.reset_survey()
                self.state = "survey"
            return
        if self.state == "survey":
            self.on_survey_click(point)
            return
        if self.state == "instructions":
            begin = self._hit_rects.get("begin")
            if begin and begin.collidepoint(point):
                self.database.ensure_session(self.session_number)
                self.state = "next"
            return
        if self.state == "ready":
            start_btn = pygame.Rect(0, 0, 320, 70)
            start_btn.center = (self.center[0], self.center[1] + 70)
            if start_btn.collidepoint(point):
                self.state = "next"
            return
        if self.state == "next":
            next_btn = pygame.Rect(0, 0, 220, 70)
            next_btn.center = (self.center[0], self.center[1] + 80)
            if next_btn.collidepoint(point):
                self.start_trial_targets()
            return
        if self.state == "center":
            if _distance(point, self.center) <= config.CENTER_DIAMETER / 2:
                self.current = self.queue.pop(0)
                self.path_length = 0.0
                self.last_point = point
                self.started_at = perf_counter()
                self.state = "move"
            return
        if self.state == "move":
            self.save_current(point)

    def on_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.state in ("consent", "survey"):
                self.abort_without_record()
            else:
                self.running = False
            return
        if self.state != "survey" or self.text_focus is None:
            return
        if self.text_focus == "disabilities_other":
            if event.key == pygame.K_BACKSPACE:
                self.answers["disabilities_other"] = self.answers["disabilities_other"][:-1]
            elif event.unicode and event.unicode.isprintable():
                if len(self.answers["disabilities_other"]) < 80:
                    self.answers["disabilities_other"] += event.unicode
                    self.answers["disabilities"].discard("No")
            return

        question = self.current_question()
        field = self.text_focus
        if field not in self.answers or not isinstance(self.answers[field], str):
            return
        max_len = question.get("max_len", 3) if question["id"] == field else 3
        if event.key == pygame.K_BACKSPACE:
            self.answers[field] = self.answers[field][:-1]
        elif event.unicode and event.unicode.isdigit():
            if len(self.answers[field]) < max_len:
                self.answers[field] += event.unicode


    def loop(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.on_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.on_click(event.pos)
            if self.state == "move":
                self.add_sample(pygame.mouse.get_pos())
            self.draw()
            self.clock.tick(120)
        return self.saved_any, self.mode


def run():
    app = FittsApp()
    mode = None
    try:
        saved_any, mode = app.loop()
        if app.database is not None:
            app.database.purge_empty_sessions()
    finally:
        app.close()
    # Always rebuild Excel from the database so the sheet never keeps stale runs.
    if mode is not None:
        try:
            build_results(mode)
        except PermissionError:
            pass
