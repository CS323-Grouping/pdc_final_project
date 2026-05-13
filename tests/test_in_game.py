import time
from types import SimpleNamespace

from network import protocol
from network import network_handler as nw
from states.in_game import InGameState


def test_reconcile_heartbeat_returns_to_lobby_when_server_state_is_lobby():
    switched = []
    statuses = []
    state = InGameState.__new__(InGameState)
    state._status_notice_cooldown = 0.0
    state._active_match_id = 3
    state.switch = lambda name: switched.append(name)
    state.context = SimpleNamespace(
        last_heartbeat_ack_monotonic=time.monotonic(),
        last_server_state=protocol.STATE_LOBBY,
        results_standings=[],
        is_host=False,
        current_match_id=3,
        set_status=lambda message, duration=0.0: statuses.append((message, duration)),
    )

    reconciled = InGameState._reconcile_heartbeat_authority(state, SimpleNamespace(current_match_id=3))

    assert reconciled is True
    assert switched == ["joined_lobby"]
    assert statuses


def test_observer_focus_no_target_sets_waiting_message():
    statuses = []
    state = InGameState.__new__(InGameState)
    state._status_notice_cooldown = 0.0
    state._spectate_player_id = None
    state._spectate_snap_pending = False
    state._placements_by_id = {}
    state._remote_positions = {}
    state._name_by_id = {}
    state._set_spectator_target = lambda *_args, **_kwargs: None
    state.context = SimpleNamespace(
        network=SimpleNamespace(id=1),
        last_server_state=protocol.STATE_IN_GAME,
        set_status=lambda message, duration=0.0: statuses.append((message, duration)),
    )
    state.hero = SimpleNamespace(pos=SimpleNamespace(x=11.0, y=22.0))

    focus = InGameState._observer_focus_position(state)

    assert focus == (11.0, 22.0)
    assert statuses


def test_roster_event_creates_new_in_game_remote_player():
    created = []
    state = InGameState.__new__(InGameState)
    state.context = SimpleNamespace(
        network=SimpleNamespace(id=2),
        roster=[],
        start_pos=(100.0, 100.0),
        drain_network_events=lambda: [
            nw.RosterEvent(entries=[(0, False, "Host"), (1, False, "Dev3"), (2, False, "Dev2")])
        ],
    )
    state._remote_positions = {}
    state._remote_players = {}
    state._platforms_reached_by_id = {}
    state._finished_player_ids = set()
    state._placements_by_id = {}
    state._name_by_id = {}
    state._spectate_player_id = None
    state._set_spectator_target = lambda *_args, **_kwargs: None
    state._spawn_position_for_player = lambda player_id, base_start: (base_start[0] + player_id, base_start[1])

    def create_remote(player_id, position):
        created.append((player_id, position))
        state._remote_players[player_id] = SimpleNamespace(position=position)
        return state._remote_players[player_id]

    state._get_remote_player = create_remote

    assert InGameState._drain_network(state) is False

    assert state.context.roster == [(0, False, "Host"), (1, False, "Dev3"), (2, False, "Dev2")]
    assert created == [(0, (100.0, 100.0)), (1, (101.0, 100.0))]


def test_pending_death_resends_until_confirmed():
    sent = []
    state = InGameState.__new__(InGameState)
    state._death_pending = True
    state._finish_pending = False
    state._death_resend_elapsed = 0.0
    state._finish_resend_elapsed = 0.0
    net = SimpleNamespace(id=2, current_match_id=7, send_dead=lambda: sent.append("dead"))

    InGameState._tick_pending_terminal_action(state, 0.1, net)
    InGameState._tick_pending_terminal_action(state, 0.25, net)

    assert sent == ["dead"]


def test_pending_goal_resends_until_confirmed():
    sent = []
    state = InGameState.__new__(InGameState)
    state._death_pending = False
    state._finish_pending = True
    state._death_resend_elapsed = 0.0
    state._finish_resend_elapsed = 0.0
    net = SimpleNamespace(id=1, current_match_id=9, send_goal=lambda: sent.append("goal"))

    InGameState._tick_pending_terminal_action(state, 0.2, net)
    InGameState._tick_pending_terminal_action(state, 0.15, net)

    assert sent == ["goal"]
