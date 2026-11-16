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
import system_info
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
        self.ui = config.ui_scale(self.width, self.height)
        self.font = pygame.font.SysFont("segoeui", self.u(36))
        self.small_font = pygame.font.SysFont("segoeui", self.u(24))
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
        self.skipped = set()
        self.survey_back_count = 0
        self.text_focus = None
        self._hit_rects = {}
        self.scale = config.layout_scale(self.width, self.height)
        self.system_info = system_info.collect(self.width, self.height, self.scale)
        self.session_info_saved = False

    def u(self, value):
        """Scale a 1920x1080 UI measurement to this screen."""
        return max(1, int(round(value * self.ui)))

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
        self.skipped = set()
        self.survey_back_count = 0
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
        offset = distance * self.scale
        if direction == "left":
            return (x - offset, y)
        return (x + offset, y)

    def center_radius(self):
        return config.CENTER_DIAMETER * self.scale / 2

    def add_sample(self, point):
        if self.last_point is None:
            self.last_point = point
            return
        if point != self.last_point:
            self.path_length += _distance(self.last_point, point)
            self.last_point = point

    def save_current(self, click_point):
        direction, distance, diameter = self.current
        radius = diameter * self.scale / 2
        center = self.target_center(direction, distance)
        self.add_sample(click_point)
        offset = _distance(click_point, center)
        hit = offset <= radius
        error_distance = 0.0 if hit else offset - radius
        target_number = self.database.target_count(self.session_number, self.trial_number) + 1
        # path/error are stored in design units (drawn px / scale) and as drawn px.
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
                "path_length_px": self.path_length / self.scale,
                "hit": 1 if hit else 0,
                "error_distance_px": error_distance / self.scale,
                "scale": self.scale,
                "path_length_raw_px": self.path_length,
                "error_distance_raw_px": error_distance,
            },
        )
        if not self.session_info_saved:
            self.database.save_session_info(self.session_number, self.system_info)
            self.session_info_saved = True
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

    def visible_questions(self):
        return survey.visible_questions(self.answers)

    def current_question(self):
        visible = self.visible_questions()
        if self.question_index >= len(visible):
            self.question_index = max(0, len(visible) - 1)
        return visible[self.question_index]

    def save_survey_and_continue(self):
        survey.sync_conditional_answers(self.answers, self.skipped)
        visible_ids = {question["id"] for question in self.visible_questions()}
        payload = {
            "name": self.answers["name"],
            "gender": self.answers["gender"],
            "gender_other": self.answers["gender_other"] if self.answers["gender"] == "Other" else "",
            "age": self.answers["age"],
            "handedness": self.answers["handedness"],
            "computer_hours": self.answers["computer_hours"],
            "input_device": self.answers["input_device"],
            "input_device_other": (
                self.answers["input_device_other"] if self.answers["input_device"] == "Other" else ""
            ),
            "mouse_model": (
                self.answers["mouse_model"] if self.answers["input_device"] == "Mouse" else ""
            ),
            "machine_company": (
                self.answers["machine_company"] if self.answers["input_device"] == "Trackpad" else ""
            ),
            "disabilities": survey.format_disabilities(self.answers),
            "skipped_questions": ", ".join(
                question_id
                for question_id in (q["id"] for q in survey.QUESTIONS)
                if question_id in self.skipped and question_id in visible_ids
            ),
            "survey_back_count": self.survey_back_count,
        }
        self.database.save_demographics(self.session_number, payload)
        self.state = "instructions"

    def focus_current_question(self):
        question = self.current_question()
        self.text_focus = question["id"] if question["kind"] == "text" else None

    def advance_question(self):
        survey.sync_conditional_answers(self.answers, self.skipped)
        visible = self.visible_questions()
        if self.question_index + 1 < len(visible):
            self.question_index += 1
            self.focus_current_question()
        else:
            self.save_survey_and_continue()

    def skip_question(self):
        question = self.current_question()
        survey.clear_answer(question, self.answers)
        self.skipped.add(question["id"])
        self.advance_question()

    def go_back_question(self):
        if self.question_index <= 0:
            return
        self.survey_back_count += 1
        self.question_index -= 1
        survey.sync_conditional_answers(self.answers, self.skipped)
        visible = self.visible_questions()
        if self.question_index >= len(visible):
            self.question_index = len(visible) - 1
        self.focus_current_question()

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
        line_height = font.get_height() + self.u(line_gap)
        for index, line in enumerate(lines):
            self.draw_text(line, y + index * line_height, font, color)
        return len(lines) * line_height

    def wrapped_height(self, text, font=None, max_width=None, line_gap=8):
        font = self.font if font is None else font
        max_width = max_width or int(self.width * 0.7)
        lines = survey.wrap_text(font, text, max_width)
        return len(lines) * (font.get_height() + self.u(line_gap))

    def button(self, text, center, size=(320, 70), selected=False, key=None):
        """Size is given at 1920x1080 and scaled to this screen."""
        rect = pygame.Rect(0, 0, self.u(size[0]), self.u(size[1]))
        rect.center = center
        fill = (70, 120, 70) if selected else config.BUTTON_COLOR
        pygame.draw.rect(self.screen, fill, rect, border_radius=self.u(10))
        if selected:
            pygame.draw.rect(
                self.screen, (180, 255, 180), rect, width=self.u(3), border_radius=self.u(10)
            )
        label = self.font.render(text, True, config.BUTTON_TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        if key is not None:
            self._hit_rects[key] = rect
        return rect

    def bottom_right_button(self, text, size=(280, 70), key="action"):
        margin = self.u(48)
        rect = pygame.Rect(0, 0, self.u(size[0]), self.u(size[1]))
        rect.bottomright = (self.width - margin, self.height - margin)
        pygame.draw.rect(self.screen, config.BUTTON_COLOR, rect, border_radius=self.u(10))
        label = self.font.render(text, True, config.BUTTON_TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        self._hit_rects[key] = rect
        return rect

    def text_field(self, value, center, size=(460, 64), placeholder="", key="field"):
        rect = pygame.Rect(0, 0, self.u(size[0]), self.u(size[1]))
        rect.center = center
        pygame.draw.rect(self.screen, config.FIELD_COLOR, rect, border_radius=self.u(8))
        border = config.BUTTON_COLOR if self.text_focus == key else config.FIELD_BORDER
        pygame.draw.rect(self.screen, border, rect, width=self.u(2), border_radius=self.u(8))
        shown = value if value else placeholder
        color = config.TEXT_COLOR if value else config.MUTED_TEXT
        label = self.small_font.render(shown, True, color)
        self.screen.blit(label, label.get_rect(midleft=(rect.left + self.u(18), rect.centery)))
        self._hit_rects[key] = rect
        return rect

    def draw_consent(self):
        u = self.u
        max_width = int(self.width * 0.68)
        title_h = self.font.get_height()
        body_h = self.wrapped_height(
            survey.CONSENT_TEXT, self.small_font, max_width=max_width, line_gap=12
        )
        hint_h = self.small_font.get_height()
        block_h = title_h + u(28) + body_h + u(28) + hint_h
        top = self.center[1] - block_h // 2
        self.draw_text(survey.CONSENT_TITLE, top + title_h // 2)
        self.draw_wrapped(
            survey.CONSENT_TEXT,
            top + title_h + u(28),
            self.small_font,
            config.TEXT_COLOR,
            max_width=max_width,
            line_gap=12,
        )
        self.draw_text(
            'Press Esc to exit without recording this participant.',
            top + title_h + u(28) + body_h + u(28) + hint_h // 2,
            self.small_font,
            config.MUTED_TEXT,
        )
        self.bottom_right_button("I Consent", size=(280, 70), key="consent")

    def draw_survey(self):
        u = self.u
        visible = self.visible_questions()
        question = self.current_question()
        max_width = int(self.width * 0.68)
        progress = f"Question {self.question_index + 1} of {len(visible)}"
        prompt_h = self.wrapped_height(question["prompt"], self.font, max_width=max_width, line_gap=10)

        option_count = len(question.get("options", ()))
        show_gender_other = (
            question["kind"] == "choice"
            and question.get("other_option")
            and self.answers.get(question["id"]) == question.get("other_option")
        )
        if question["kind"] == "choice":
            options_h = option_count * u(78)
            field_h = u(88) if show_gender_other else 0
        elif question["kind"] == "text":
            options_h = 0
            field_h = u(80)
        else:
            options_h = option_count * u(70)
            field_h = u(88)

        block_h = u(36) + prompt_h + u(36) + options_h + field_h
        top = max(u(48), self.center[1] - block_h // 2)
        self.draw_text(progress, top + u(12), self.small_font, config.MUTED_TEXT)
        prompt_top = top + u(44)
        self.draw_wrapped(
            question["prompt"],
            prompt_top,
            self.font,
            config.TEXT_COLOR,
            max_width=max_width,
            line_gap=10,
        )
        y = prompt_top + prompt_h + u(36)

        if question["kind"] == "choice":
            for option in question["options"]:
                selected = self.answers[question["id"]] == option
                self.button(
                    option,
                    (self.center[0], y + u(28)),
                    size=(440, 60),
                    selected=selected,
                    key=f"opt:{option}",
                )
                y += u(78)
            if show_gender_other:
                other_key = question.get("other_key", "gender_other")
                self.text_field(
                    self.answers[other_key],
                    (self.center[0], y + u(34)),
                    size=(440, 58),
                    placeholder=question.get("other_placeholder", "Please specify"),
                    key=other_key,
                )
                self.text_focus = other_key
        elif question["kind"] == "text":
            field_key = question["id"]
            self.text_field(
                self.answers[field_key],
                (self.center[0], y + u(32)),
                placeholder=question.get("placeholder", ""),
                key=field_key,
            )
            self.text_focus = field_key
        elif question["kind"] == "multi":
            for option in question["options"]:
                selected = option in self.answers["disabilities"]
                self.button(
                    option,
                    (self.center[0], y + u(26)),
                    size=(520, 56),
                    selected=selected,
                    key=f"opt:{option}",
                )
                y += u(70)
            self.text_field(
                self.answers["disabilities_other"],
                (self.center[0], y + u(34)),
                size=(520, 58),
                placeholder=question.get("other_placeholder", ""),
                key="disabilities_other",
            )

        next_size = (220, 70)
        if survey.answer_is_complete(question, self.answers):
            self.bottom_right_button("Next", size=next_size, key="next")
        else:
            message = survey.validation_message(question, self.answers)
            if message:
                hint = self.small_font.render(message, True, config.MUTED_TEXT)
                hint_rect = hint.get_rect(
                    midbottom=(self.width // 2, self.height - u(48) - u(80))
                )
                self.screen.blit(hint, hint_rect)
        # Skip stays left of Next; Back is bottom-left.
        skip = pygame.Rect(0, 0, u(180), u(70))
        skip.bottomright = (
            self.width - u(48) - u(next_size[0]) - u(24),
            self.height - u(48),
        )
        pygame.draw.rect(self.screen, config.FIELD_BORDER, skip, width=u(2), border_radius=u(10))
        label = self.font.render("Skip", True, config.TEXT_COLOR)
        self.screen.blit(label, label.get_rect(center=skip.center))
        self._hit_rects["skip"] = skip

        if self.question_index > 0:
            back = pygame.Rect(0, 0, u(180), u(70))
            back.bottomleft = (u(48), self.height - u(48))
            pygame.draw.rect(self.screen, config.FIELD_BORDER, back, width=u(2), border_radius=u(10))
            back_label = self.font.render("Back", True, config.TEXT_COLOR)
            self.screen.blit(back_label, back_label.get_rect(center=back.center))
            self._hit_rects["back"] = back

    def draw_instructions(self):
        u = self.u
        max_width = int(self.width * 0.68)
        title_h = self.font.get_height()
        body_h = self.wrapped_height(
            survey.INSTRUCTIONS_TEXT, self.small_font, max_width=max_width, line_gap=12
        )
        block_h = title_h + u(28) + body_h
        top = self.center[1] - block_h // 2
        self.draw_text(survey.INSTRUCTIONS_TITLE, top + title_h // 2)
        self.draw_wrapped(
            survey.INSTRUCTIONS_TEXT,
            top + title_h + u(28),
            self.small_font,
            config.TEXT_COLOR,
            max_width=max_width,
            line_gap=12,
        )
        self.bottom_right_button("Begin Trial", size=(300, 70), key="begin")

    def draw(self):
        u = self.u
        cx, cy = self.center
        self.screen.fill(config.BACKGROUND)
        self._hit_rects = {}
        if self.state == "mode":
            self.draw_text("What kind of session is this?", cy - u(150))
            self.draw_wrapped(
                "If you are told to participate in this project, make sure to click Participant.",
                cy - u(100),
                self.small_font,
                config.MUTED_TEXT,
                max_width=int(self.width * 0.7),
            )
            self.button("Participant", (cx, cy - u(10)), key="participant")
            self.button("Test", (cx, cy + u(90)), key="test")
        elif self.state == "resume":
            label = self.label()
            self.draw_text(f"{label} {self.unfinished_number} is unfinished.", cy - u(110))
            self.draw_text(
                "Continue that session, or start the next number.",
                cy - u(60),
                self.small_font,
                config.MUTED_TEXT,
            )
            self.button(
                f"Continue {label} {self.unfinished_number}",
                (cx, cy + u(10)),
                size=(420, 70),
                key="continue",
            )
            self.button(
                f"Start {label} {self.database.next_session_number()}",
                (cx, cy + u(110)),
                size=(420, 70),
                key="new",
            )
        elif self.state == "consent":
            self.draw_consent()
        elif self.state == "survey":
            self.draw_survey()
        elif self.state == "instructions":
            self.draw_instructions()
        elif self.state == "ready":
            label = self.label()
            self.draw_text(f"You are {label} {self.session_number}", cy - u(80))
            if self.database.target_count(self.session_number):
                self.draw_text(
                    f"Continuing from Trial {self.trial_number} of {config.TRIAL_COUNT}",
                    cy - u(20),
                    self.small_font,
                    config.MUTED_TEXT,
                )
            else:
                self.draw_text(
                    f"This session will run {config.TRIAL_COUNT} trials.",
                    cy - u(20),
                    self.small_font,
                    config.MUTED_TEXT,
                )
            self.button("Start", (cx, cy + u(70)), key="start")
        elif self.state == "next":
            label = self.label()
            self.draw_text(f"{label} {self.session_number}", u(48), self.small_font, config.MUTED_TEXT)
            done = self.database.target_count(self.session_number, self.trial_number)
            self.draw_text(f"Trial {self.trial_number} of {config.TRIAL_COUNT}", cy - u(40))
            if done:
                self.draw_text("Continuing this trial", cy + u(10), self.small_font)
            self.button("Next", (cx, cy + u(80)), size=(220, 70), key="next_trial")
        elif self.state == "center":
            self.draw_text("Click the white circle", u(48), self.small_font)
            pygame.draw.circle(
                self.screen,
                config.CENTER_COLOR,
                self.center,
                self.center_radius(),
            )
        elif self.state == "move":
            self.draw_text("Click the yellow circle", u(48), self.small_font)
            pygame.draw.circle(
                self.screen,
                config.CENTER_COLOR,
                self.center,
                self.center_radius(),
            )
            direction, distance, diameter = self.current
            pygame.draw.circle(
                self.screen,
                config.TARGET_COLOR,
                self.target_center(direction, distance),
                diameter * self.scale / 2,
            )
        elif self.state == "done":
            label = self.label()
            self.draw_text(f"{label} {self.session_number} finished all 10 trials.", cy - u(40))
            self.draw_text("Results were saved. Press Esc to close.", cy + u(30), self.small_font)
        pygame.display.flip()

    def on_survey_click(self, point):
        question = self.current_question()
        for key, rect in self._hit_rects.items():
            if not rect.collidepoint(point):
                continue
            if key == "next":
                if not survey.answer_is_complete(question, self.answers):
                    return
                self.skipped.discard(question["id"])
                self.advance_question()
                return
            if key == "skip":
                self.skip_question()
                return
            if key == "back":
                self.go_back_question()
                return
            if key.startswith("opt:"):
                option = key[4:]
                if question["kind"] == "choice":
                    self.answers[question["id"]] = option
                    other_option = question.get("other_option")
                    other_key = question.get("other_key")
                    if other_key and option != other_option:
                        self.answers[other_key] = ""
                        self.text_focus = None
                    elif other_key and option == other_option:
                        self.text_focus = other_key
                    if question["id"] == "input_device":
                        survey.sync_conditional_answers(self.answers, self.skipped)
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
            if key in self.answers:
                self.text_focus = key
                return

    def clicked(self, key, point):
        rect = self._hit_rects.get(key)
        return rect is not None and rect.collidepoint(point)

    def on_click(self, point):
        if self.state == "mode":
            if self.clicked("participant", point):
                self.choose_mode(config.MODE_PARTICIPANT)
            elif self.clicked("test", point):
                self.choose_mode(config.MODE_TEST)
            return
        if self.state == "resume":
            if self.clicked("continue", point):
                self.continue_session(self.unfinished_number)
            elif self.clicked("new", point):
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
            if self.clicked("start", point):
                self.state = "next"
            return
        if self.state == "next":
            if self.clicked("next_trial", point):
                self.start_trial_targets()
            return
        if self.state == "center":
            if _distance(point, self.center) <= self.center_radius():
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
        if self.text_focus.endswith("_other"):
            field = self.text_focus
            if event.key == pygame.K_BACKSPACE:
                self.answers[field] = self.answers[field][:-1]
            elif event.unicode and event.unicode.isprintable():
                if len(self.answers[field]) < 80:
                    self.answers[field] += event.unicode
                    if field == "disabilities_other":
                        self.answers["disabilities"].discard("No")
            return

        question = self.current_question()
        field = self.text_focus
        if field not in self.answers or not isinstance(self.answers[field], str):
            return
        max_len = question.get("max_len", 3) if question["id"] == field else 3
        digits_only = bool(question.get("digits_only")) if question["id"] == field else True
        allow_decimal = bool(question.get("allow_decimal")) if question["id"] == field else False
        if event.key == pygame.K_BACKSPACE:
            self.answers[field] = self.answers[field][:-1]
        elif event.unicode and event.unicode.isprintable():
            char = event.unicode
            if digits_only:
                if char == "." and allow_decimal:
                    if "." in self.answers[field]:
                        return
                elif not char.isdigit():
                    return
            if len(self.answers[field]) < max_len:
                self.answers[field] += char


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
