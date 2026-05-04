from unittest.mock import patch

from network.discovery import LobbyBrowser, PresenceEntry, RoomEntry, beacon_to_room_entry, presence_to_entry
from network import protocol


def test_beacon_to_room_entry_rejects_wrong_proto():
    pkt = protocol.pack_beacon(
        99,
        cur_players=1,
        max_players=5,
        room_state=protocol.STATE_LOBBY,
        game_port=5555,
        room_name="Old",
    )
    assert beacon_to_room_entry(pkt, ("192.168.1.5", 5555)) is None


def test_beacon_to_room_entry_accepts_current_proto():
    pkt = protocol.pack_beacon(
        protocol.PROTO_VERSION,
        cur_players=2,
        max_players=5,
        room_state=protocol.STATE_IN_GAME,
        game_port=6000,
        room_name="FightRoom",
    )
    entry = beacon_to_room_entry(pkt, ("10.0.0.2", 6000))
    assert entry is not None
    assert entry.addr == "10.0.0.2"
    assert entry.game_port == 6000
    assert entry.room_name == "FightRoom"
    assert entry.current_players == 2
    assert entry.state == protocol.STATE_IN_GAME


def test_presence_to_entry_accepts_current_proto():
    pkt = protocol.pack_presence(
        protocol.PROTO_VERSION,
        instance_id=42,
        status=protocol.PRESENCE_STATUS_ONLINE,
        player_name="Alpha",
    )
    entry = presence_to_entry(pkt, ("10.0.0.9", 5556))

    assert entry is not None
    assert entry.addr == "10.0.0.9"
    assert entry.instance_id == 42
    assert entry.player_name == "Alpha"
    assert entry.status == protocol.PRESENCE_STATUS_ONLINE


def test_snapshot_evicts_stale_rooms():
    browser = LobbyBrowser(discovery_port=58330, ttl=3.0)
    key = ("203.0.113.10", 5555)
    with browser._lock:
        browser._rooms[key] = RoomEntry(
            addr="203.0.113.10",
            game_port=5555,
            room_name="Stale",
            current_players=1,
            max_players=5,
            state=0,
            last_seen=100.0,
        )

    with patch("network.discovery.time.monotonic", return_value=105.0):
        rooms = browser.snapshot()

    assert rooms == []
    browser.stop()


def test_presence_snapshot_evicts_stale_entries():
    browser = LobbyBrowser(discovery_port=58332, ttl=3.0)
    key = ("203.0.113.12", 77)
    with browser._lock:
        browser._presence[key] = PresenceEntry(
            addr="203.0.113.12",
            instance_id=77,
            player_name="Stale",
            status=protocol.PRESENCE_STATUS_ONLINE,
            last_seen=100.0,
        )

    with patch("network.discovery.time.monotonic", return_value=105.0):
        entries = browser.presence_snapshot()

    assert entries == []
    browser.stop()
