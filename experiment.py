# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

from typing import Any, override

import klibs
from klibs import P
from klibs.KLCommunication import message
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip
from klibs.KLUserInterface import any_key, key_pressed, ui_request
from klibs.KLUtilities import deg_to_px, pump
from klibs.KLEventInterface import TrialEventTicket as tet
from klibs.KLResponseListener import KeypressListener
from klibs.KLTrialFactory import TrialException, TrialFactory
from klibs.KLDatabase import DatabaseManager

from random import choice, randrange

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
                keymap: {' ': 'present'},
                timeout: self.params['response_window'],
                loop_callback: self.listener_callback
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

        # TODO: better naming
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
            self.performance_at_threshold = False
            while P.practicing:
                self.target_trial = random.choice([True, False])

                self.trial_prep()
                self.evm.start_clock()

                try:
                    self.trial()
                except TrialException:
                    pass

                self.evm.stop_clock()
                self.trial_clean_up()

                if self.performance_at_threshold:
                    P.practicing = False

    @override
    def trial_prep(self) -> None:
        # get location and spawn array for trial
        self.array_center = self.array_anchors[self.array_location]
        self.array = self.make_array()

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
        self.blit_array()

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

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'target_trial': self.target_trial,
            'array_location': self.array_location,
            'target_jitter': self.params['jitter_mod']
            if self.target_trial
            else 'NA',
            'rt': rt,
            'correct': correct,
        }

    @override
    def trial_clean_up(self) -> None:
        # after 20 trials, and every 10 trials following, check
        # performance over last 20 trials, adapting task difficultly as needed.
        if P.practicing and P.trial_number >= 20 and P.trial_number % 10 == 0:
            self.performance_log.append(self.performance_check())

            if self.performance_log[-1] == 'same':
                # will fail during initial performance check
                try:
                    if self.performance_log[-2] == 'same':
                        self.performance_at_threshold = True
                        return
                except IndexError:
                    self.adapt_difficulty(self.performance_log[-1])

            self.adapt_difficulty(make=self.performance_log[-1])

    @override
    def clean_up(self) -> None:
        pass

    def adapt_difficulty(self, make: str) -> None:
        if make is None:
            raise ValueError(
                'make must be one of: "harder", "easier", or "same"'
            )

        if make == 'harder':
            adjustment = -0.1
        elif make == 'easier':
            adjustment = 0.1
        else:
            adjustment = 0

        self.params['target_offset_mod'] += adjustment

    # grabs and sums accuracy across last 20 trials
    def performance_check(self) -> bool:
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

        if len(responses) < 20:
            raise RuntimeError(
                f'Query expected to return 20 responses at minimum, got {len(responses)}'
            )

        acc = sum(responses[-20:])

        if acc > 17:
            return 'harder'
        elif acc <= 15:
            return 'easier'
        else:
            return 'same'

    def blit_array(self) -> None:
        fill()
        blit(self.fixation, registration=5, location=P.screen_c)

        if self.evm.before('array_off'):
            for loc in self.array:
                blit(self.line, registration=5, location=loc)

        flip()

    def make_array(self) -> list[tuple[int, int]]:
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
