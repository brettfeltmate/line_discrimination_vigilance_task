# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

from typing import Any, override

import klibs
from klibs import P
from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip
from klibs.KLUserInterface import any_key
from klibs.KLUtilities import deg_to_px
from klibs.KLEventInterface import TrialEventTicket as tet
from klibs.KLResponseListener import KeypressListener
from klibs.KLTrialFactory import TrialException
from klibs.KLDatabase import DatabaseManager

from random import randrange, choice

WHITE = [255, 255, 255, 255]
TL = 'top_left'
TR = 'top_right'
BL = 'bottom_left'
BR = 'bottom_right'


class line_discrimination_vigil(klibs.Experiment):
    @override
    def setup(self) -> None:
        self.params = {
            'line_length': deg_to_px(0.5),
            'fixation_width': deg_to_px(0.5),
            'stroke_width': deg_to_px(0.1),
            'jitter_unit': deg_to_px(0.1),
            'jitter_bound': deg_to_px(0.5),
            # Multiplier; initial value, later modified based on performance
            'target_offset_mod': 2.1,
            'flanker_gap': deg_to_px(0.15),
            'array_locs': [-2, -1, 0, 1, 2],
            # in ms
            'inter_trial_interval': 2000,
            'array_duration': 250,
            'response_window': 1000,
        }

        self.params['flanker_offset'] = (
            self.params['line_length'] + self.params['flanker_gap']
        )   # center-to-center distance between flankers

        v_offset = P.screen_c[1] // 2
        h_offset = P.screen_c[0] // 2
        # possible locations for arrays to be centred on
        self.array_anchors = {
            TL: (P.screen_c[0] - h_offset, P.screen_c[1] - v_offset),
            TR: (P.screen_c[0] + h_offset, P.screen_c[1] - v_offset),
            BL: (P.screen_c[0] - h_offset, P.screen_c[1] + v_offset),
            BR: (P.screen_c[0] + h_offset, P.screen_c[1] + v_offset),
        }

        self.line = kld.Line(
            length=self.params['line_length'],
            thickness=self.params['stroke_width'],
            color=WHITE,
            rotation=90,
        )

        self.fixation = kld.FixationCross(
            size=self.params['fixation_width'],
            thickness=self.params['stroke_width'],
            fill=WHITE,
        )

        # listen for spacebar presses
        self.key_listener = KeypressListener(
            {
                'keymap': {' ': 'present'},
                'timeout': self.params['response_window'],
                'loop_callback': self.listener_callback
                if hasattr(self, 'listener_callback')
                else None,
            }
        )

        # possibly unneeded
        self.dm = DatabaseManager(
            path='./ExpAssets/line_discrimination_vigil.db'
        )

        # practice block true length conditionally determined from performance
        if P.run_practice_blocks:
            self.insert_practice_block(block_nums=[1], trial_counts=[1])

        # used to monitor and log performance during practice
        self.performance_log = []

    @override
    def block(self) -> None:
        msg = 'Hit space for targets.\nAny key to start block.'
        if P.practicing:
            msg += '\n\n(practice)'

        fill()

        # TODO: instructions
        message(
            message=msg,
            registration=5,
            location=P.screen_c,
            blit_txt=True,
        )
        flip()

        any_key()

        # loop, creating new practice trials until performance at threshold
        if P.practicing:
            self.difficulty_check_completed = False
            while P.practicing:
                # need to manually enforce 50/50 split of target trials for practice
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

                # assess task difficulty every 10 trials
                self.__assess_task_difficulty()

                # if difficulty checks completed, end practice
                if self.difficulty_check_completed:
                    P.practicing = False
                    break

    @override
    def trial_prep(self) -> None:
        # get location and spawn array for trial
        self.array_center = self.array_anchors[self.array_location]
        self.array = self.__make_array()

        # define time-series of events
        trial_events = []
        trial_events.append(['remove_array', self.params['array_duration']])
        trial_events.append(
            [
                'response_timeout',
                trial_events[-1][1] + self.params['response_window'],
            ]
        )
        trial_events.append(['end_trial', self.params['inter_trial_interval']])

        for ev in trial_events:
            self.evm.register_ticket(tet(ev[0], ev[1]))

    @override
    def trial(self) -> dict[str, Any]:

        # present array immediately
        self.__blit_array()

        # listen for responses
        # handles removal of array
        resp, rt = self.key_listener.collect()

        # log response accuracy
        if self.target_trial and resp:
            correct = 1
        elif not self.target_trial and resp is None:
            correct = 1
        else:
            correct = 0

        # for posterity, log results of performance checks
        practice_performance = 'NA'  # default value to avoid value errors
        if P.practicing:
            try:
                practice_performance = self.performance_log[-1]
            except IndexError:
                pass

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'target_trial': self.target_trial,
            'array_location': self.array_location,
            'target_jitter': self.params['jitter_mod']
            if self.target_trial
            else 'NA',
            'practice_performance': practice_performance,
            'rt': rt,
            'correct': correct,
        }

    @override
    def trial_clean_up(self) -> None:
        pass

    @override
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
        if not P.practicing:
            raise RuntimeError(
                'Task difficulty assessment should only performed during practice.'
            )

        adjustment = 0

        # after 20 trials, and every 10 trials following conduct performance check
        if P.trial_number >= 20 and P.trial_number % 10 == 0:
            self.performance_log.append(self.__query_performance())

            adjustment = None

            # if sufficient data, check for performance stability
            if len(self.performance_log) > 1:
                if self.performance_log[-2] == 'ideal':
                    if self.performance_log[-1] == 'ideal':
                        self.difficulty_check_completed = True
                        return

            # if insufficient, or otherwise not ideal, adjust task difficulty
            adjustment = self.__task_difficulty_adjustment(
                self.performance_log[-1]
            )

            self.params['target_offset_mod'] += adjustment

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
        if performance not in ['high', 'low', 'ideal']:
            raise ValueError('performance must be one of: "high", "low", "ideal"')

        if performance == 'ideal':
            return 0.0

        return P.difficulty_upstep if performance == 'high' else P.difficulty_downstep

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
        responses = self.database.select(
            table='trials',
            columns='correct',
            where={
                'practicing': P.practicing,
                'participant_id': P.participant_id,
            },
        )

        if len(responses) != P.trial_number:
            raise RuntimeError(
                f'Expected {P.trial_number} responses for performance check, got {len(responses)}.'
            )

        if len(responses) < P.assessment_window:
            raise RuntimeError(
                f'Query expected to return 20 responses at minimum, got {len(responses)}'
            )

        acc = sum(responses[-P.assessment_window :])

        if acc > P.performance_bounds[1]:
            return 'high'
        elif acc < P.performance_bounds[0]:
            return 'low'
        else:
            return 'ideal'

    def __blit_array(self) -> None:
        fill()
        blit(self.fixation, registration=5, location=P.screen_c)

        if self.evm.before('array_off'):
            for loc in self.array:
                blit(self.line, registration=5, location=loc)

        flip()

    def __make_array(self) -> list[tuple[int, int]]:
        locs = []

        # randomly sample jitter values
        flanker_jitter = [
            randrange(
                -self.params['jitter_bound'],
                self.params['jitter_bound'],
                self.params['jitter_unit'],
            )
        ]

        if self.target_trial:
            # to be discriminable at all, targets' jitter must exceed that of any flankers
            max_jitter = max(flanker_jitter)
            flanker_jitter[2] = max_jitter * self.params['target_offset_mod']

        # construct (x,y) coords for each line in array
        for i in range(5):
            x = self.array_center[0] + (
                self.params['array_locs'][i] * self.params['flanker_offset']
            )
            y = self.array_center[1] + flanker_jitter[i]
            locs.append((x, y))

        return locs
