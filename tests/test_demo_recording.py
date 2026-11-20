"""Recording real model replies once, replaying them offline, and showing what the guardrails removed."""

import json
import os
import subprocess
import sys
from pathlib import Path

import demo
from demo.export_site import guardrail_changes
from src.llm.ollama_client import OllamaClient
from src.llm.reply_generator import ReplyGenerator

ROOT = Path(__file__).resolve().parent.parent
RAW = "That sounds stressful. Keep it all in one place. We're building Aila for this: https://joinaila.com/"


def test_record_then_replay(tmp_path, monkeypatch):
    recording = tmp_path / "recorded_replies.json"
    monkeypatch.setenv("AILA_DEMO_REPLIES", str(recording))
    monkeypatch.setattr(OllamaClient, "generate", lambda self, prompt, system=None, temperature=0.7, max_tokens=300: RAW)
    demo._install_recorder()

    demo._current_lead["url"] = "https://example.org/lead-1"
    try:
        assert OllamaClient(model="test-model").generate("prompt") == RAW
        saved = json.loads(recording.read_text(encoding="utf-8"))
        assert saved["replies"]["https://example.org/lead-1"] == {"model": "test-model", "raw": RAW}

        # Offline, the stand-in replays the recording for that lead and falls back to the placeholder otherwise.
        assert demo.DemoLLMClient().generate("any prompt") == RAW
        demo._current_lead["url"] = "https://example.org/not-recorded"
        assert demo.DemoLLMClient().generate("any prompt") == demo.DEMO_REPLY
    finally:
        demo._current_lead["url"] = None


def test_page_reports_what_the_sanitizer_removed():
    final = ReplyGenerator(ollama_client=demo.DemoLLMClient())._sanitize_reply(
        RAW, allow_aila_mention=True, allow_link=False
    )
    changes = guardrail_changes(RAW, final)
    assert len(changes) == 1 and "joinaila.com" in changes[0]
    assert guardrail_changes(RAW, RAW) == []


def test_reply_style_is_the_same_in_every_run():
    code = (
        "from demo import DemoLLMClient; from src.llm.reply_generator import ReplyGenerator; "
        "g = ReplyGenerator(ollama_client=DemoLLMClient()); "
        "print([g._choose_style_variant({'url': f'https://example.org/{i}'}) for i in range(8)])"
    )
    outputs = set()
    for seed in ("1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout.strip().splitlines()[-1])
    assert len(outputs) == 1
