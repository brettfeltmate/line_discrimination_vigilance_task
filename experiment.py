# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"
import os
import klibs
from csv import DictWriter

from klibs import P
from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip
from klibs.KLUserInterface import any_key, key_pressed, smart_sleep, ui_request
from klibs.KLUtilities import deg_to_px, pump, rotate_points
from klibs.KLAudio import Tone

from random import randrange, choice

from rich.console import Console

RED = [255, 0, 0, 255]
WHITE = [255, 255, 255, 255]
TL = "top_left"
TR = "top_right"
BL = "bottom_left"
BR = "bottom_right"


class line_discrimination_vigil(klibs.Experiment):

    def setup(self):

        if P.run_practice_blocks:
            if not os.path.exists("ExpAssets/Data/practice"):
                os.mkdir("ExpAssets/Data/practice")

        self.console = Console()

        if P.development_mode:
            P.practicing = True

        self.params = {
            "line_length": deg_to_px(0.5),
            "fixation_width": deg_to_px(0.5),
            "stroke_width": deg_to_px(0.1),
            "jitter_unit": deg_to_px(0.05),
            "jitter_bound": deg_to_px(0.06),
            # Multiplier; initial value, later modified based on performance
            "target_mod": 5,  # TODO: start easy to give buffer for performance checks
            "flanker_gap": deg_to_px(0.15),
            "array_locs": [-2, -1, 0, 1, 2],
            # in ms
            "array_on": 500,
            "trial_done": 2000,
            "array_duration": 200,
            "array_offset": P.screen_c[1] // 2,  # type: ignore[operator]
        }

        self.params["flanker_offset"] = (
            self.params["line_length"] + self.params["flanker_gap"]
        )  # center-to-center distance between flankers

        self.fixation = kld.FixationCross(
            size=self.params["fixation_width"],
            thickness=self.params["stroke_width"],
            fill=WHITE,
        )

        # practice block true length conditionally determined from performance
        if P.run_practice_blocks:
            self.insert_practice_block(block_nums=[1], trial_counts=[1])

        self.error_tone = Tone(duration=100, volume=0.5)

        # used to monitor and log performance during practice
        self.performance_log = []

        self.console.log(self.params, log_locals=True)

    def block(self):
        msg = "When a target is presented, press the spacebar, otherwise press nothing.\nPress any key to start block."
        if P.practicing:
            msg += "\n\nThis is a practice block. If you make an error, a tone will sound to indicate so."

        fill()

        # TODO: proper instructions
        message(
            text=msg,
            registration=5,
            location=P.screen_c,
            blit_txt=True,
        )
        flip()

        any_key()

        if P.practicing:

            fname = "ExpAssets/Data/practice/P" + str(P.participant_id) + ".csv"

            col_names = [
                "practicing",
                "target_probability",
                "block_num",
                "trial_num",
                "target_trial",
                "target_jitter",
                "practice_performance",
                "responded",
                "rt",
                "correct",
            ]

            with open(fname, "w") as file:
                writer = DictWriter(file, col_names)
                writer.writeheader()

            self.practice_trial_num = 1
            self.practice_performance = []
            self.difficulty_check_completed = False

            while P.practicing:
                self.target_trial = choice([True, False])

                # -- trial start --
                self.trial_prep()
                self.evm.start_clock()

                trial = self.trial()
                trial["trial_num"] = self.practice_trial_num

                self.evm.stop_clock()
                # -- trial end --

                # assess task difficulty (starting after 20 trials, and subsequently rechecked every 10 trials)
                self.practice_performance.append(int(trial["correct"]))
                self.assess_task_difficulty()

                with open(fname, "a") as file:
                    writer = DictWriter(file, col_names)
                    writer.writerow(trial)

                # if difficulty checks completed, end practice
                if self.difficulty_check_completed:
                    P.practicing = False
                    break

                self.practice_trial_num += 1

    def trial_prep(self):
        # get location and spawn array for trial
        self.array = self.make_array()

        # define time-series of events
        self.evm.add_event("array_on", self.params["array_on"])
        self.evm.add_event("array_off", self.params["array_duration"], after="array_on")
        self.evm.add_event("trial_done", self.params["trial_done"])

    def trial(self):  # type: ignore[override]

        resp, rt = False, None

        while self.evm.before("array_on"):
            q = pump(True)
            _ = ui_request(queue=q)

        self.blit_array()

        array_visible = True
        array_onset_realtime = self.evm.trial_time_ms

        while self.evm.before("trial_done"):
            if array_visible and self.evm.after("array_off"):
                fill()
                blit(self.fixation, registration=5, location=P.screen_c)
                flip()

                array_visible = False

            q = pump(True)

            if key_pressed("space", queue=q) and not resp:
                rt, resp = self.evm.trial_time_ms - array_onset_realtime, True

                if not self.target_trial and P.practicing:
                    self.error_tone.play()

        if P.practicing:
            if self.target_trial and not resp:
                self.error_tone.play()
                smart_sleep(200)

        trial_data = {
            "practicing": P.practicing,
            "target_probability": P.condition,
            "block_num": P.block_number,
            "trial_num": P.trial_number,
            "target_trial": self.target_trial,
            "target_jitter": (self.params["target_mod"] if self.target_trial else "NA"),
            "responded": resp,
            "rt": rt,
            "correct": self.target_trial == resp,
        }

        return trial_data

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def assess_task_difficulty(self):
        adjustment = 0

        # after 20 trials, and every 10 trials following conduct performance check
        if self.practice_trial_num >= 20 and self.practice_trial_num % 10 == 0:

            self.performance_log.append(self.query_performance())

            # if sufficient data, check for performance stability
            if len(self.performance_log) > 1:
                if self.performance_log[-2:] == ["ideal", "ideal"]:
                    self.difficulty_check_completed = True
                    return

            perf = self.performance_log[-1]

            # if insufficient, or otherwise not ideal, adjust task difficulty
            if perf == "ideal":
                adjustment = 0.0
            elif perf == "low":
                adjustment = P.difficulty_downstep  # type: ignore[attr-defined]
            else:
                adjustment = P.difficulty_upstep  # type: ignore[attr-defined]

            self.params["target_mod"] += adjustment

            self.console.log(self.performance_log, log_locals=True)

    # grabs and sums accuracy across last 20 trials
    def query_performance(self):
        acc = sum(self.practice_performance[-P.assessment_window :]) / P.assessment_window  # type: ignore[attr-defined]
        self.console.log(self.practice_performance, log_locals=True)

        if acc > P.performance_bounds[1]:  # type: ignore[attr-defined]
            return "high"
        elif acc < P.performance_bounds[0]:  # type: ignore[attr-defined]
            return "low"
        else:
            return "ideal"

    def blit_array(self):
        fill()
        blit(self.fixation, registration=5, location=P.screen_c)

        if P.development_mode and self.target_trial:
            self.line = kld.Line(
                length=self.params["line_length"],
                thickness=self.params["stroke_width"],
                color=RED,
                rotation=90,
            )
        else:
            self.line = kld.Line(
                length=self.params["line_length"],
                thickness=self.params["stroke_width"],
                color=WHITE,
                rotation=90,
            )

        if self.evm.before("array_off"):
            for loc in self.array:
                blit(self.line, registration=5, location=loc)

        flip()

    def make_array(self):
        """Creates an array of line positions for the visual discrimination task.

        Generates a rotated array of 5 lines, where each line's position is determined by:
        1. A base array location rotated around screen center
        2. Horizontal spacing defined by flanker_offset parameter
        3. Random vertical jitter unique to each line

        For target trials, the central line's jitter is increased by target_mod
        to make it more discriminable from flanking lines.

        Returns:
            list[tuple[int, int]]: List of (x,y) coordinates for each line in the array,
                                  ordered from leftmost to rightmost position.
        """
        array_origin = [P.screen_c[0], P.screen_c[1] - self.params["array_offset"]]
        rotation = randrange(0, 359)

        array_center = rotate_points(
            points=[array_origin], origin=P.screen_c, angle=rotation
        )[0]

        locs = []

        # randomly sample jitter values
        flanker_jitter = [
            randrange(
                0,
                self.params["jitter_bound"],
                self.params["jitter_unit"],
            )
            for _ in range(5)
        ]

        if self.target_trial:
            # to be discriminable at all, targets' jitter must exceed that of any flankers
            max_jitter = max(flanker_jitter)

            # max_jitter = max([abs(jit) for jit in flanker_jitter])
            flanker_jitter[2] = max_jitter * self.params["target_mod"]

        # construct (x,y) coords for each line in array
        for i in range(5):
            sign = choice([-1, 1])
            x = array_center[0] + (
                self.params["array_locs"][i] * self.params["flanker_offset"]
            )
            y = array_center[1] + (flanker_jitter[i] * sign)
            locs.append((x, y))

        return locs
