from types import SimpleNamespace

import pygame

from states.results import RESULTS_MIN_VISIBLE_SECONDS, ResultsState


class DummyMachine:
    def __init__(self):
        self.changes = []

    def change(self, state_name: str, **kwargs):
        self.changes.append((state_name, kwargs))


def make_results_state():
    machine = DummyMachine()
    context = SimpleNamespace(
        countdown_remaining=3.0,
        return_state_after_results="host_lobby",
    )
    state = ResultsState(machine, context)
    state.enter()
    return state, machine


def test_results_ignores_dismiss_input_until_minimum_visible_time():
    state, machine = make_results_state()

    state.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    state.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1))

    assert machine.changes == []

    state.update(RESULTS_MIN_VISIBLE_SECONDS - 0.01)
    state.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert machine.changes == []

    state.update(0.02)
    state.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert machine.changes == [("host_lobby", {})]


def test_results_still_auto_hides():
    state, machine = make_results_state()

    state.update(5.0)

    assert machine.changes == [("host_lobby", {})]
