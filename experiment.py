# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import klibs
from klibs import P
from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip
from klibs.KLUserInterface import any_key, key_pressed, smart_sleep
from klibs.KLUtilities import deg_to_px, pump, rotate_points
from klibs.KLEventInterface import TrialEventTicket as tet
from klibs.KLExceptions import TrialException
from klibs.KLTime import Stopwatch
from klibs.KLAudio import Tone

from random import randrange, choice

RED = [255, 0, 0, 255]
WHITE = [255, 255, 255, 255]
TL = "top_left"
TR = "top_right"
BL = "bottom_left"
BR = "bottom_right"


class line_discrimination_vigil(klibs.Experiment):

    def setup(self):

        if P.development_mode:
            P.practicing = True

        self.params = {
            "line_length": deg_to_px(0.5),
            "fixation_width": deg_to_px(0.5),
            "stroke_width": deg_to_px(0.1),
            "jitter_unit": deg_to_px(0.02),
            "jitter_bound": deg_to_px(0.06),
            # Multiplier; initial value, later modified based on performance
            "target_offset_mod": 5,  # TODO: start easy to give buffer for performance checks
            "flanker_gap": deg_to_px(0.15),
            "array_locs": [-2, -1, 0, 1, 2],
            # in ms
            "trial_timeout": 2000,
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

        self.error_tone = Tone(duration = 100, volume = 0.5)

        # used to monitor and log performance during practice
        self.performance_log = []

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

        # loop, creating new practice trials until performance at threshold
        if P.practicing:
            self.practice_trial_num = 1
            self.practice_performance = []
            self.difficulty_check_completed = False
            while P.practicing:
                # As this isn't a "real" block, FactorSet is not yet available
                # so trial factors need to be selected manually
                self.target_trial = choice([True, False])

                # -- trial start --
                self.trial_prep()
                self.evm.start_clock()

                try:
                    self.trial()
                except TrialException:
                    pass

                self.evm.stop_clock()
                # -- trial end --

                # assess task difficulty (only runs after every tenth trial)
                self.assess_task_difficulty()

                self.practice_trial_num += 1

                # if difficulty checks completed, end practice
                if self.difficulty_check_completed:
                    P.practicing = False
                    break

    def trial_prep(self):
        # get location and spawn array for trial
        self.array = self.make_array()

        # define time-series of events
        trial_events = []
        trial_events.append(["array_off", self.params["array_duration"]])
        trial_events.append(["trial_timeout", self.params["trial_timeout"]])

        for ev in trial_events:
            self.evm.register_ticket(tet(ev[0], ev[1]))

    def trial(self):  # type: ignore[override]

        resp, rt = None, None

        # present array immediately
        self.blit_array()
        array_visible = True

        reaction_timer = Stopwatch()
        while self.evm.before("trial_timeout"):
            if array_visible and self.evm.after("array_off"):
                fill()
                blit(self.fixation, registration=5, location=P.screen_c)
                flip()
                array_visible = False
            queue = pump()
            if key_pressed("space", queue=queue):
                resp = True
                rt = reaction_timer.elapsed()
                break

        # log response accuracy
        if self.target_trial and resp:
            correct = 1
        elif not self.target_trial and resp is None:
            correct = 1
        else:
            correct = 0

        # for posterity, log results of performance checks
        practice_performance = "NA"  # default value to avoid value errors
        if P.practicing:
            if correct == 0:
                self.error_tone.play()
                smart_sleep(1000)
            try:
                practice_performance = self.performance_log[-1]
            except IndexError:
                pass

        return {
            "practicing": P.practicing,
            "block_num": P.block_number,
            "trial_num": P.trial_number,
            "target_trial": self.target_trial,
            "target_jitter": (
                self.params["target_offset_mod"] if self.target_trial else "NA"
            ),
            "practice_performance": practice_performance,
            "rt": rt,
            "correct": correct,
        }

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def assess_task_difficulty(self):
        """Assesses and adjusts task difficulty during practice trials.

        Monitors participant performance every 10 trials after the first 20 trials.
        Task difficulty is adjusted based on performance thresholds until stability
        is achieved (two consecutive 'ideal' performance assessments).

        Raises:
            RuntimeError: If called outside of practice trials.
        """
        print("__assess_task_difficulty")
        if not P.practicing:
            raise RuntimeError(
                "Task difficulty assessment should only performed during practice."
            )

        adjustment = 0

        # after 20 trials, and every 10 trials following conduct performance check
        if self.practice_trial_num >= 20 and self.practice_trial_num % 10 == 0:
            # if P.development_mode:
            #     msg = (
            #         f"Assessing performance from trials {self.practice_trial_num - 10} to {self.practice_trial_num}",
            #     )
            #     print(msg)
            #     fill()
            #     message(
            #         text=msg,
            #         location=P.screen_c,
            #         registration=5,
            #         blit_txt=True,
            #     )
            #     flip()
            #     any_key()
            #     clear()

            self.performance_log.append(self.query_performance())

            adjustment = None

            # if sufficient data, check for performance stability
            if len(self.performance_log) > 1:
                if self.performance_log[-2] == "ideal":
                    if self.performance_log[-1] == "ideal":
                        self.difficulty_check_completed = True
                        return

            # if insufficient, or otherwise not ideal, adjust task difficulty
            adjustment = self.task_difficulty_adjustment(self.performance_log[-1])

            # if P.development_mode:
            #     fill()
            #
            #     msg = f"Performance found to be {self.performance_log[-1]}\nAdjusting offset by {adjustment}."
            #     print(msg)
            #     msg += "\n(any key)"
            #     message(text=msg, location=P.screen_c, registration=5, blit_txt=True)
            #
            #     flip()
            #     any_key()
            #     clear()

            self.params["target_offset_mod"] += adjustment

    def task_difficulty_adjustment(self, performance):
        """Determines the adjustment value for task difficulty based on performance.

        Args:
            performance: Performance category ('high', 'low', or 'ideal') supplied by __query_performance

        Returns:
            float: Adjustment value for target offset modifier
                  (0 for ideal, upstep for high, downstep for low; step values defined in _params)

        Raises:
            ValueError: If performance is not one of 'high', 'low', or 'ideal'
        """
        print("__task_difficulty_adjustment")
        if performance not in ["high", "low", "ideal"]:
            raise ValueError('performance must be one of: "high", "low", "ideal"')

        if performance == "ideal":
            return 0.0

        return P.difficulty_upstep if performance == "high" else P.difficulty_downstep  # type: ignore[attr-defined]

    # grabs and sums accuracy across last 20 trials
    def query_performance(self):
        """Queries and evaluates participant performance over assessment window.

        Retrieves accuracy data for recent trials and categorizes performance
        based on performance bounds (defined in _params).

        Returns:
            str: Performance category ('high', 'low', or 'ideal')

        Raises:
            RuntimeError: If number of responses doesn't match trial number
                        or if insufficient trials for assessment
        """

        try:
            acc = sum(self.practice_performance[-P.assessment_window :])  # type: ignore[attr-defined]
        except IndexError:
            raise RuntimeError("Insufficient trials for performance assessment.")

        if acc > P.performance_bounds[1]:  # type: ignore[attr-defined]
            return "high"
        elif acc < P.performance_bounds[0]:  # type: ignore[attr-defined]
            return "low"
        else:
            return "ideal"

    def blit_array(self):
        print("__blit_array")
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

        For target trials, the central line's jitter is increased by target_offset_mod
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
            flanker_jitter[2] = max_jitter * self.params["target_offset_mod"]

        # construct (x,y) coords for each line in array
        for i in range(5):
            sign = choice([-1, 1])
            x = array_center[0] + (
                self.params["array_locs"][i] * self.params["flanker_offset"]
            )
            y = array_center[1] + (flanker_jitter[i] * sign)
            locs.append((x, y))

        return locs
