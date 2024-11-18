# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

from typing import Any

import klibs
from klibs import P
from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip, clear
from klibs.KLUserInterface import any_key, key_pressed
from klibs.KLUtilities import deg_to_px, pump
from klibs.KLEventInterface import TrialEventTicket as tet
from klibs.KLExceptions import TrialException
from klibs.KLTime import Stopwatch

from random import randrange, choice

RED = [255, 0, 0, 255]
WHITE = [255, 255, 255, 255]
TL = "top_left"
TR = "top_right"
BL = "bottom_left"
BR = "bottom_right"


class line_discrimination_vigil(klibs.Experiment):

    def setup(self) -> None:

        if P.development_mode:
            P.practicing = True

        self.params = {
            "line_length": deg_to_px(0.5),
            "fixation_width": deg_to_px(0.5),
            "stroke_width": deg_to_px(0.1),
            "jitter_unit": deg_to_px(0.02),
            "jitter_bound": deg_to_px(0.06),
            # Multiplier; initial value, later modified based on performance
            "target_offset_mod": 5,  # TODO: start easy to give buffer for performance checks?
            "flanker_gap": deg_to_px(0.15),
            "array_locs": [-2, -1, 0, 1, 2],
            # in ms
            "inter_trial_interval": 2000,
            "array_duration": 200,
            "response_window": 1000,
        }

        self.params["flanker_offset"] = (
            self.params["line_length"] + self.params["flanker_gap"]
        )  # center-to-center distance between flankers

        v_offset = P.screen_c[1] // 3
        h_offset = P.screen_c[0] // 3
        # possible locations for arrays to be centred on
        self.array_anchors = {
            TL: (P.screen_c[0] - h_offset, P.screen_c[1] - v_offset),
            TR: (P.screen_c[0] + h_offset, P.screen_c[1] - v_offset),
            BL: (P.screen_c[0] - h_offset, P.screen_c[1] + v_offset),
            BR: (P.screen_c[0] + h_offset, P.screen_c[1] + v_offset),
        }

        self.fixation = kld.FixationCross(
            size=self.params["fixation_width"],
            thickness=self.params["stroke_width"],
            fill=WHITE,
        )

        # practice block true length conditionally determined from performance
        if P.run_practice_blocks:
            self.insert_practice_block(block_nums=[1], trial_counts=[1])

        # used to monitor and log performance during practice
        self.performance_log = []

    def block(self) -> None:
        msg = "Hit space for targets.\nAny key to start block."
        if P.practicing:
            msg += "\n\n(practice)"

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
                self.array_location = choice([TL, TR, BL, BR])

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
                self.__assess_task_difficulty()

                self.practice_trial_num += 1

                # if difficulty checks completed, end practice
                if self.difficulty_check_completed:
                    P.practicing = False
                    break

    def trial_prep(self) -> None:
        # get location and spawn array for trial
        self.array_center = self.array_anchors[self.array_location]
        self.array = self.__make_array()

        # define time-series of events
        trial_events = []
        trial_events.append(["array_off", self.params["array_duration"]])
        trial_events.append(
            [
                "response_timeout",
                trial_events[-1][1] + self.params["response_window"],
            ]
        )
        trial_events.append(["end_trial", self.params["inter_trial_interval"]])

        for ev in trial_events:
            self.evm.register_ticket(tet(ev[0], ev[1]))

    def trial(self) -> dict[str, Any]:

        resp, rt = None, None

        # present array immediately
        self.__blit_array()

        reaction_timer = Stopwatch()
        while self.evm.before("response_timeout"):
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
            try:
                practice_performance = self.performance_log[-1]
            except IndexError:
                pass

        return {
            "practicing": P.practicing,
            "block_num": P.block_number,
            "trial_num": P.trial_number,
            "target_trial": self.target_trial,
            "array_location": self.array_location,
            "target_jitter": (
                self.params["target_offset_mod"] if self.target_trial else "NA"
            ),
            "practice_performance": practice_performance,
            "rt": rt,
            "correct": correct,
        }

    def trial_clean_up(self) -> None:
        pass

    def clean_up(self) -> None:
        pass

    def __assess_task_difficulty(self) -> None:
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
            if P.development_mode:
                msg = (
                    f"Assessing performance from trials {self.practice_trial_num - 10} to {self.practice_trial_num}",
                )
                print(msg)
                fill()
                message(
                    text=msg,
                    location=P.screen_c,
                    registration=5,
                    blit_txt=True,
                )
                flip()

                any_key()

                clear()

            self.performance_log.append(self.__query_performance())

            adjustment = None

            # if sufficient data, check for performance stability
            if len(self.performance_log) > 1:
                if self.performance_log[-2] == "ideal":
                    if self.performance_log[-1] == "ideal":
                        self.difficulty_check_completed = True
                        return

            # if insufficient, or otherwise not ideal, adjust task difficulty
            adjustment = self.__task_difficulty_adjustment(self.performance_log[-1])

            if P.development_mode:
                fill()

                msg = f"Performance found to be {self.performance_log[-1]}\nAdjusting offset by {adjustment}."
                print(msg)
                msg += "\n(any key)"
                message(text=msg, location=P.screen_c, registration=5, blit_txt=True)

                flip()

                any_key()

                clear()

            self.params["target_offset_mod"] += adjustment

    def __task_difficulty_adjustment(self, performance: str) -> float:
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

        return P.difficulty_upstep if performance == "high" else P.difficulty_downstep

    # grabs and sums accuracy across last 20 trials
    def __query_performance(self) -> str:
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
            acc = sum(self.practice_performance[-P.assessment_window :])
        except IndexError:
            raise RuntimeError("Insufficient trials for performance assessment.")

        if acc > P.performance_bounds[1]:
            return "high"
        elif acc < P.performance_bounds[0]:
            return "low"
        else:
            return "ideal"

    def __blit_array(self) -> None:
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

    def __make_array(self) -> list[tuple[int, int]]:
        print("__make_array")
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
            x = self.array_center[0] + (
                self.params["array_locs"][i] * self.params["flanker_offset"]
            )
            y = self.array_center[1] + (flanker_jitter[i] * sign)
            locs.append((x, y))

        return locs
