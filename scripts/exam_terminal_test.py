"""Checks for the terminal exam: domain mix, scoring, and a scripted sitting."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import exam_terminal as exam  # noqa: E402

POOL = json.loads((ROOT / "assets" / "data" / "questions.json").read_text(encoding="utf-8"))
EXPECTED = {
    "cloud-concepts": 8,
    "security-compliance": 9,
    "technology-services": 11,
    "billing-support": 4,
}


def rng(seed: int):
    source = __import__("random").Random(seed)

    def roll() -> float:
        return source.random()

    return roll


def test_engine() -> None:
    drawn = exam.build_exam(POOL["questions"], POOL["meta"], rng(7))
    again = exam.build_exam(POOL["questions"], POOL["meta"], rng(7))
    assert [item["id"] for item in drawn] == [item["id"] for item in again]
    assert len(drawn) == 32
    assert len({item["stemKey"] for item in drawn}) == 32
    counts: dict[str, int] = {}
    for question in drawn:
        counts[question["domain"]] = counts.get(question["domain"], 0) + 1
    assert counts == EXPECTED
    assert exam.is_correct(["E", "B"], ["B", "E"])
    assert not exam.is_correct(["B"], ["B", "E"])
    pool = exam.record_result([], "q1", ["A"], False, "2026-10-09T00:00:00+00:00")
    pool = exam.record_result(pool, "q1", ["C"], False, "2026-10-09T01:00:00+00:00")
    assert pool[0]["timesMissed"] == 2
    assert pool[0]["selected"] == ["C"]
    assert exam.record_result(pool, "q1", ["B"], True) == []
    assert exam.passed(22, 32, 0.7) is False
    assert exam.passed(23, 32, 0.7) is True
    assert exam.parse_entry("b, e", {"A", "B", "E"}) == ("answer", ["B", "E"])
    assert exam.parse_entry("b", {"A", "B", "E"}) == ("answer", ["B"])
    assert exam.parse_entry("e", {"A", "B", "E"}) == ("answer", ["E"])
    assert exam.parse_entry("end", {"A", "B", "E"}) == ("command", "end")
    assert exam.parse_entry("n", {"A"}) == ("command", "n")
    assert exam.parse_entry("q", {"A", "B"}) == ("command", "q")
    assert exam.parse_entry("g 12", {"A"}) == ("command", "g 12")
    assert exam.parse_entry("goto 3", {"A"}) == ("command", "goto 3")


def test_scripted_session() -> None:
    drawn = exam.build_exam(POOL["questions"], POOL["meta"], rng(7))
    first = drawn[0]
    wrong = next(choice["letter"] for choice in first["choices"] if choice["letter"] not in first["answers"])
    script = "\n".join(["1", wrong, "end", "y", "", "3", "2", "b", "b", "q", ""]) + "\n"
    with tempfile.TemporaryDirectory() as folder:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "exam_terminal.py"), "--seed", "7", "--data-dir", folder],
            input=script,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            cwd=ROOT,
        )
        output = completed.stdout + completed.stderr
        assert completed.returncode == 0, output
        assert "Wrong." in output
        assert "Saved to the wrong pool." in output
        assert "0 / 32" in output
        assert "under the 70% pass mark" in output
        saved = json.loads((Path(folder) / "wrong-pool.json").read_text(encoding="utf-8"))
        assert saved[0]["id"] == first["id"]
        assert saved[0]["selected"] == [wrong]
        assert "Your answer:" in output


if __name__ == "__main__":
    test_engine()
    test_scripted_session()
    print("exam terminal tests passed")
