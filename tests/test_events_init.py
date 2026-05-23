"""Tests for callprofiler.events package initialization."""
import callprofiler.events


def test_package_imports():
    """Verify all public names are exportable."""
    assert hasattr(callprofiler.events, "DashboardEvent")
    assert hasattr(callprofiler.events, "emit_event_sync")
    assert hasattr(callprofiler.events, "get_client_count")
    assert hasattr(callprofiler.events, "subscribe")
    assert hasattr(callprofiler.events, "unsubscribe")


def test_all_exports():
    """Verify __all__ contains expected names."""
    expected = {
        "DashboardEvent",
        "emit_event_sync",
        "subscribe",
        "unsubscribe",
        "get_client_count",
    }
    actual = set(callprofiler.events.__all__)
    assert actual == expected
