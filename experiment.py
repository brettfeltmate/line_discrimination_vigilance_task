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
from klibs.KLTime import Stopwatch
from klibs.KLEventInterface import TrialEventTicket as ET

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
            'jitter_bound': 5,
            'target_offset': 11,  # NOTE: initial value; procedurally redetermined via performance checks
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

    @override
    def block(self) -> None:
        fill()

        # TODO: instructions
        message(
            'Hit space for targets.\nAny key to start block.',
            registration=5,
            location=P.screen_c,
            blit_txt=True,
        )
        flip()

        any_key()

    @override
    def trial_prep(self) -> None:
        self.array_center = choice(list(self.array_anchors.values()))
        self.array = self.make_array()

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
            self.evm.register_ticket(ET(ev[0], ev[1]))

    @override
    def trial(self) -> dict[str, Any]:
        rt_clock = Stopwatch()
        rt = None

        fill()
        for loc in self.array:
            blit(self.line, registration=5, location=loc)
        flip()

        _ = pump()
        while self.evm.before('array_off'):
            _ = ui_request()
            if key_pressed('space'):
                rt = rt_clock.elapsed() / 1000
                break
        fill()
        flip()

        while self.evm.before('response_timeout'):
            _ = ui_request()
            if rt is None and key_pressed('space'):
                rt = rt_clock.elapsed()

        while self.evm.before('trial_end'):
            _ = ui_request()

        # TODO: log response accuracy
        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'target_trial': self.target_trial,
            'target_jitter': self.params['jitter_mod']
            if self.target_trial
            else 'NA',
            'rt': rt if rt is not None else 'NA',
        }

    @override
    def trial_clean_up(self) -> None:
        pass

    @override
    def clean_up(self) -> None:
        pass

    def make_array(self) -> list[tuple[int, int]]:
        locs = []

        # HACK: values hardcoded for now
        flanker_jitter = [
            randrange(
                -self.params['jitter_bound'], self.params['jitter_bound'], 0.02
            )
        ]

        # TODO: scaler addition
        if self.target_trial:
            flanker_jitter[2] *= self.params['jitter_mod']

        for i in range(5):
            x = self.array_center[0] + (
                self.params['array_locs'][i] * self.params['flanker_offset']
            )
            y = self.array_center[1] + flanker_jitter[i]
            locs.append((x, y))

        return locs
