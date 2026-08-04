"""Configuração dos testes E2E (rede + LLM real).

Estes testes só correm com `RUN_E2E=1` no ambiente; caso contrário são
automaticamente marcados como skip para não dependerem de rede/cota na
suíte unitária normal.
"""

import os

import pytest

_E2E_DIR = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(items):
    if os.environ.get("RUN_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="E2E desativado; corra com RUN_E2E=1")
    for item in items:
        path = os.path.abspath(str(item.fspath))
        if path.startswith(_E2E_DIR):
            item.add_marker(skip)