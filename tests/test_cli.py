from __future__ import annotations

import json

import pytest
from conftest import FakeDecider

from agent_factory import cli


def test_triage_only_asks_system_one_and_spends_no_system_two_tokens(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    decider = FakeDecider(intent="bugfix", confidence=0.93, actionable=0.8)
    monkeypatch.setattr(cli, "make_decider", lambda settings: decider)
    monkeypatch.setattr(cli, "run", lambda *a, **k: pytest.fail("System 2 must not run in --triage-only"))

    assert cli.main(["the login page returns 500 after the last deploy", "--triage-only", "--json"]) == 0
    verdict = json.loads(capsys.readouterr().out)["triage"]
    assert verdict == {"intent": "bugfix", "intent_confidence": 0.93, "actionable": 0.8, "confident": True}
    assert [kind for kind, _ in decider.calls] == ["choose", "yes_no"]
