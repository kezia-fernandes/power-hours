import json
from pathlib import Path

from powerhours.client import EnergyChartsClient, envelope_to_frame, is_open_licence

FIXTURE = Path(__file__).parent / "fixtures" / "price_envelope.json"


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def test_envelope_to_frame_parses_timestamps_and_drops_nulls():
    frame = envelope_to_frame(json.loads(FIXTURE.read_text()))
    assert list(frame.columns) == ["ts_utc", "series", "value"]
    assert len(frame) == 3  # the null value is dropped
    assert str(frame["ts_utc"].iloc[0]) == "2026-11-14 23:00:00+00:00"  # 00:00 Oslo = 23:00 UTC
    assert frame["value"].iloc[0] == 163.35


def test_empty_envelope_gives_empty_frame():
    assert envelope_to_frame({"data": []}).empty


def test_licence_detection():
    assert is_open_licence({"license": "CC BY 4.0 from Bundesnetzagentur | SMARD.de"})
    assert not is_open_licence(json.loads(FIXTURE.read_text()))
    assert not is_open_licence({})


def test_client_waits_between_requests_and_retries_on_429():
    sleeps = []
    now = [0.0]
    session = FakeSession(
        [
            FakeResponse(200, {"data": []}),
            FakeResponse(429, headers={"Retry-After": "10"}),
            FakeResponse(200, {"data": [1]}),
        ]
    )
    client = EnergyChartsClient(
        session=session, min_interval=30, sleep=sleeps.append, clock=lambda: now[0]
    )
    client.get("price", bzn="DE-LU")
    result = client.get("price", bzn="DE-LU", start=None)

    assert result == {"data": [1]}
    assert sleeps[0] == 30  # spacing before the second request
    assert 11 in sleeps  # Retry-After + 1 second
    assert session.calls[0][1] == {"bzn": "DE-LU"}  # None parameters are not sent


def test_404_means_no_data_yet():
    client = EnergyChartsClient(session=FakeSession([FakeResponse(404)]))
    assert client.get("price_next_day")["data"] == []
