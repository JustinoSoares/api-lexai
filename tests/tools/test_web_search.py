from app.core.config import settings
from app.agent.tools.web_search import web_search_tool


def _result(title: str, url: str, body: str = "texto") -> dict:
    return {"title": title, "href": url, "snippet": body}


class _FakeDDGS:
    def __init__(self, items):
        self._items = items

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def text(self, query, max_results=5):
        return self._items


def test_web_search_success(monkeypatch):
    items = [
        {"title": "A", "href": "https://lex.ao/lei", "body": "texto"},
        {"title": "B", "href": "https://outro.com/x", "body": "outro"},
        {"title": "C", "href": "https://exemplo.org/y", "body": "texto"},
    ]
    monkeypatch.setattr("app.agent.tools.web_search.DDGS", lambda: _FakeDDGS(items))
    monkeypatch.setattr(
        "app.agent.tools.web_search._validated_whitelist", lambda: {"lex.ao"}
    )
    monkeypatch.setattr(settings, "web_search_enabled", True)

    out = web_search_tool("lei angola", max_results=3)

    assert len(out) == 3
    # o domínio da whitelist vem primeiro
    assert out[0]["href"] == "https://lex.ao/lei"


def test_web_search_honours_max_results(monkeypatch):
    items = [
        {"title": f"r{i}", "href": f"https://exemplo.org/{i}", "body": "t"}
        for i in range(9)
    ]
    monkeypatch.setattr("app.agent.tools.web_search.DDGS", lambda: _FakeDDGS(items))
    monkeypatch.setattr(
        "app.agent.tools.web_search._validated_whitelist", lambda: set()
    )
    monkeypatch.setattr(settings, "web_search_enabled", True)

    assert len(web_search_tool("x", max_results=2)) == 2


def test_web_search_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "web_search_enabled", False)
    assert web_search_tool("qualquer", max_results=5) == []


def test_web_search_no_results(monkeypatch):
    monkeypatch.setattr("app.agent.tools.web_search.DDGS", lambda: _FakeDDGS([]))
    monkeypatch.setattr(
        "app.agent.tools.web_search._validated_whitelist", lambda: set()
    )
    monkeypatch.setattr(settings, "web_search_enabled", True)

    assert web_search_tool("nada", max_results=5) == []