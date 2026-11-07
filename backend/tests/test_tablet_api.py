"""Boundary checks on the existing sales API's tablet endpoints."""

import pytest

from tests.test_api import client as client


@pytest.mark.parametrize("endpoint", ["/tablet", "/tablet/outlook"])
def test_missing_kstation_cohort_returns_clear_unavailable(client, endpoint):
    response = client.get(endpoint, params={"date": "2026-10-29"})
    assert response.status_code == 503
    assert "K-Station" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", ["/tablet", "/tablet/outlook"])
@pytest.mark.parametrize("params", [{"date": "bad"}, {"date": "2026-10-29", "source": "unknown"}])
def test_invalid_tablet_request_is_rejected(client, endpoint, params):
    assert client.get(endpoint, params=params).status_code == 400
