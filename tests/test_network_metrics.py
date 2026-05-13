import socket
import time

from network import protocol
from network import network_handler as nw


class FakeSocket:
    def __init__(self, packets=None):
        self.sent = []
        self.packets = list(packets or [])

    def settimeout(self, _timeout):
        pass

    def sendto(self, payload, addr):
        self.sent.append((payload, addr))
        return len(payload)

    def recvfrom(self, _buf_size):
        if not self.packets:
            raise socket.timeout()
        return self.packets.pop(0), ("127.0.0.1", 5555)

    def close(self):
        pass


def test_network_metrics_track_sent_and_received_throughput():
    net = nw.Network("127.0.0.1", 5555)
    net.client = FakeSocket([protocol.pack_heartbeat_ack(protocol.STATE_IN_GAME, 2, 3, ping_seq=0)])
    try:
        assert net._sendto(b"abcd") is True
        event = net.receive_one()
        snapshot = net.metrics_snapshot()
    finally:
        net.close()

    assert isinstance(event, nw.HeartbeatAckEvent)
    assert snapshot.outbound_kib_per_sec > 0
    assert snapshot.inbound_kib_per_sec > 0
    assert snapshot.outbound_avg_kib_per_sec > 0
    assert snapshot.inbound_avg_kib_per_sec > 0
    assert snapshot.outbound_max_kib_per_sec >= snapshot.outbound_min_kib_per_sec
    assert snapshot.inbound_max_kib_per_sec >= snapshot.inbound_min_kib_per_sec
    assert snapshot.outbound_packets_per_sec == 1
    assert snapshot.inbound_packets_per_sec == 1
    assert snapshot.outbound_packet_tags_per_sec == {"abcd": 1}
    assert snapshot.inbound_packet_tags_per_sec == {"HBAK": 1}


def test_network_metrics_compute_heartbeat_ping_ms():
    net = nw.Network("127.0.0.1", 5555)
    net.client = FakeSocket([protocol.pack_heartbeat_ack(protocol.STATE_IN_GAME, 2, 3, ping_seq=1)])
    try:
        with net._metrics_lock:
            net._pending_ping[1] = time.monotonic() - 0.025
            net._heartbeat_sent = 1
        event = net.receive_one()
        snapshot = net.metrics_snapshot()
    finally:
        net.close()

    assert isinstance(event, nw.HeartbeatAckEvent)
    assert snapshot.ping_ms is not None
    assert snapshot.ping_avg_ms is not None
    assert snapshot.ping_min_ms is not None
    assert snapshot.ping_max_ms is not None
    assert snapshot.ping_ms >= 20
    assert snapshot.ping_min_ms <= snapshot.ping_avg_ms <= snapshot.ping_max_ms
