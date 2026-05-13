from types import SimpleNamespace
import time

from app.state_machine import AppContext, ReconnectTicket
from network import protocol


def _dummy_context(tmp_path):
    profile_session = SimpleNamespace(profile_dir=tmp_path)
    ctx = SimpleNamespace(
        profile_session=profile_session,
        reconnect_ticket=None,
        network=None,
        is_host=False,
        local_player_alive=True,
        current_match_id=0,
        last_results_match_id=0,
    )
    ctx._reconnect_ticket_path = lambda: AppContext._reconnect_ticket_path(ctx)
    return ctx


def test_reconnect_ticket_persist_and_load_round_trip(tmp_path):
    now = int(time.time())
    writer = _dummy_context(tmp_path)
    writer.reconnect_ticket = ReconnectTicket(
        addr="127.0.0.1",
        port=5555,
        room_name="RoomOne",
        player_id=3,
        session_token=123456,
        player_name="Alpha",
        is_host=False,
        match_id=7,
        countdown_id=4,
        created_at_unix=now,
        expires_at_unix=now + 3600,
    )

    AppContext._persist_reconnect_ticket(writer, reason="unit_test")

    reader = _dummy_context(tmp_path)
    AppContext._load_persisted_reconnect_ticket(reader)

    assert reader.reconnect_ticket is not None
    assert reader.reconnect_ticket.addr == "127.0.0.1"
    assert reader.reconnect_ticket.player_id == 3
    assert reader.reconnect_ticket.match_id == 7
    assert reader.reconnect_ticket.countdown_id == 4


def test_expired_reconnect_ticket_is_removed_on_load(tmp_path):
    ctx = _dummy_context(tmp_path)
    ctx.reconnect_ticket = ReconnectTicket(
        addr="127.0.0.1",
        port=5555,
        room_name="RoomOne",
        player_id=3,
        session_token=123456,
        player_name="Alpha",
        is_host=False,
        expires_at_unix=1,
    )
    AppContext._persist_reconnect_ticket(ctx, reason="expired_seed")

    loader = _dummy_context(tmp_path)
    AppContext._load_persisted_reconnect_ticket(loader)

    assert loader.reconnect_ticket is None
    assert not loader._reconnect_ticket_path().exists()


def test_should_preserve_reconnect_on_shutdown_only_for_alive_non_host_match():
    network = SimpleNamespace(client_state=protocol.CLIENT_STATE_IN_GAME, current_match_id=5)
    ctx = SimpleNamespace(
        network=network,
        is_host=False,
        local_player_alive=True,
        current_match_id=5,
        last_results_match_id=4,
    )

    assert AppContext._should_preserve_reconnect_on_shutdown(ctx) is True

    ctx.local_player_alive = False
    assert AppContext._should_preserve_reconnect_on_shutdown(ctx) is False
