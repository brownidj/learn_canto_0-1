def pytest_configure(config):
    config.addinivalue_line("markers", "ui: tests that require a Qt GUI environment")
    config.addinivalue_line("markers", "pure: tests that are pure (no Qt / no external side effects)")