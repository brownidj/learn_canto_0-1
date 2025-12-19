def pytest_configure(config):
    config.addinivalue_line("markers", "ui: tests that require a Qt GUI environment")