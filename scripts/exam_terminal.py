"""Terminal CLF-C02 exam. One question at a time, same mix and wrong pool as the dashboard.

Launch from the repo root with clf02-exam.bat, or run:
    python scripts/exam_terminal.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "clf02-practice"


def load_pool(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def shuffle(items: list, rnd) -> list:
    copy = list(items)
    for index in range(len(copy) - 1, 0, -1):
        swap = int(rnd() * (index + 1))
        copy[index], copy[swap] = copy[swap], copy[index]
    return copy


def build_exam(questions: list[dict], meta: dict, rnd=None) -> list[dict]:
    roll = rnd or random.random
    by_domain: dict[str, list[dict]] = {domain["id"]: [] for domain in meta["domains"]}
    for question in questions:
        if question["domain"] in by_domain:
            by_domain[question["domain"]].append(question)
    picked: list[dict] = []
    used: set[str] = set()
    shortages = []
    for domain in meta["domains"]:
        chosen = []
        for question in shuffle(by_domain[domain["id"]], roll):
            if question["stemKey"] in used:
                continue
            used.add(question["stemKey"])
            chosen.append(question)
            if len(chosen) == domain["examCount"]:
                break
        if len(chosen) < domain["examCount"]:
            shortages.append(f"{domain['name']} ({len(chosen)} of {domain['examCount']})")
        picked.extend(chosen)
    if shortages:
        raise RuntimeError("Not enough questions to fill the domain mix: " + ", ".join(shortages))
    return shuffle(picked, roll)


def build_wrong_exam(questions: list[dict], wrong: list[dict], limit: int, rnd=None) -> list[dict]:
    roll = rnd or random.random
    by_id = {question["id"]: question for question in questions}
    available = []
    seen: set[str] = set()
    for entry in wrong:
        question = by_id.get(entry.get("id"))
        if not question or question["stemKey"] in seen:
            continue
        seen.add(question["stemKey"])
        available.append(question)
    return shuffle(available, roll)[:limit]


def is_correct(selected: list[str], answers: list[str]) -> bool:
    if len(selected) != len(answers):
        return False
    return set(selected) == set(answers)


def record_result(pool: list[dict], question_id: str, selected: list[str], correct: bool, now: str | None = None) -> list[dict]:
    rest = [item for item in pool if item.get("id") != question_id]
    if correct:
        return rest
    previous = next((item for item in pool if item.get("id") == question_id), None)
    entry = {
        "id": question_id,
        "selected": list(selected),
        "missedAt": now or datetime.now(timezone.utc).isoformat(),
        "timesMissed": (previous.get("timesMissed", 0) if previous else 0) + 1,
    }
    return [entry, *rest]


def score_exam(questions: list[dict], responses: dict) -> dict:
    correct = 0
    checked = 0
    by_domain: dict[str, dict] = {}
    for question in questions:
        bucket = by_domain.setdefault(question["domain"], {"correct": 0, "total": 0})
        bucket["total"] += 1
        response = responses.get(question["id"])
        if response and response.get("checked"):
            checked += 1
            if response.get("correct"):
                correct += 1
                bucket["correct"] += 1
    return {
        "correct": correct,
        "checked": checked,
        "unanswered": len(questions) - checked,
        "total": len(questions),
        "byDomain": by_domain,
    }


def passed(correct: int, total: int, pass_mark: float) -> bool:
    return total > 0 and correct / total >= pass_mark


def parse_entry(text: str, letters: set[str]) -> tuple[str, list[str] | str]:
    raw = text.strip()
    if not raw:
        return ("empty", "")
    command = raw.lower()
    # B and E are choices. A one-letter command is navigation only when it is not a choice.
    if command in {"n", "next", "p", "prev", "previous", "end", "q", "quit", "menu"} or re.fullmatch(
        r"g(?:oto)?\s+\d+", command
    ):
        if len(command) == 1 and command.upper() in letters:
            return ("answer", [command.upper()])
        return ("command", command)
    compact = re.sub(r"[\s,;/]+", "", raw).upper()
    if compact and all(character in letters for character in compact):
        selected: list[str] = []
        for character in compact:
            if character not in selected:
                selected.append(character)
        return ("answer", selected)
    return ("invalid", raw)


def enable_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


def paint(text: str, code: str, color: bool) -> str:
    if not color:
        return text
    return f"\033[{code}m{text}\033[0m"


class ExamApp:
    def __init__(self, pool: dict, data_dir: Path, seed: int | None, color: bool):
        self.pool = pool
        self.meta = pool["meta"]
        self.by_id = {question["id"]: question for question in pool["questions"]}
        self.data_dir = data_dir
        self.seed = seed
        self.color = color
        self.width = min(88, max(60, shutil_width()))
        self.wrong = self._load_json("wrong-pool.json", [])
        self.session = self._load_json("session.json", None)
        self.wrong = [item for item in self.wrong if item.get("id") in self.by_id]
        if not self._session_ok(self.session):
            self.session = None
        self._rng = random.Random(seed) if seed is not None else random.Random()

    def roll(self) -> float:
        return self._rng.random()

    def run(self) -> int:
        self._save_wrong()
        while True:
            self._clear()
            self._print_home()
            choice = input("Choose: ").strip().lower()
            if choice in {"1", "s", "start"}:
                self._start("exam")
            elif choice in {"2", "c", "continue"} and self.session and not self.session.get("finished"):
                self._play()
            elif choice in {"3", "w", "wrong"}:
                self._wrong_menu()
            elif choice in {"q", "quit", "exit"}:
                return 0
            else:
                hint = "Enter 1, 2, 3, or q." if self.session and not self.session.get("finished") else "Enter 1, 3, or q."
                self._say(hint)
                self._pause()

    def _start(self, mode: str) -> None:
        if mode == "exam" and self.session and not self.session.get("finished"):
            if not self._confirm("An exam is in progress. Discard it and start a new one?"):
                return
        if mode == "wrong":
            questions = build_wrong_exam(self.pool["questions"], self.wrong, self.meta["examSize"], self.roll)
            if not questions:
                self._say("The wrong pool is empty.")
                self._pause()
                return
        else:
            try:
                questions = build_exam(self.pool["questions"], self.meta, self.roll)
            except RuntimeError as error:
                self._say(str(error))
                self._pause()
                return
        minutes = self.meta["minutes"] if mode == "exam" else None
        self.session = {
            "mode": mode,
            "ids": [question["id"] for question in questions],
            "index": 0,
            "responses": {},
            "endsAt": (datetime.now(timezone.utc).timestamp() + minutes * 60) if minutes else None,
            "finished": False,
        }
        self._save_session()
        self._play()

    def _play(self) -> None:
        while self.session and not self.session.get("finished"):
            question = self._current()
            response = self._response(question["id"])
            self._clear()
            self._print_question(question, response)
            entry = input("Answer: ")
            kind, value = parse_entry(entry, {choice["letter"] for choice in question["choices"]})
            if kind == "empty":
                if response["checked"]:
                    self._move(1)
                else:
                    self._say("Type the choice letters, for example B or BE.")
                    self._pause()
                continue
            if kind == "invalid":
                self._say("Use choice letters, or n, p, end, or q.")
                self._pause()
                continue
            if kind == "answer":
                if response["checked"]:
                    self._say("This question is already checked. Press Enter for the next one.")
                    self._pause()
                    continue
                self._check(question, value)
                continue
            command = str(value)
            if command in {"n", "next"}:
                self._move(1)
            elif command in {"p", "prev", "previous"}:
                self._move(-1)
            elif command.startswith("g"):
                number = int(command.split()[-1])
                self.session["index"] = max(0, min(len(self.session["ids"]) - 1, number - 1))
                self._save_session()
            elif command == "end":
                if self._finish(False):
                    return
            elif command in {"q", "quit", "menu"}:
                self._save_session()
                self._say("Exam saved. Start the program again and choose Continue.")
                self._pause()
                return

    def _check(self, question: dict, selected: list[str]) -> None:
        response = self._response(question["id"])
        response["selected"] = selected
        response["checked"] = True
        response["correct"] = is_correct(selected, question["answers"])
        before = any(item.get("id") == question["id"] for item in self.wrong)
        self.wrong = record_result(self.wrong, question["id"], selected, response["correct"])
        self._save_wrong()
        if response["correct"]:
            response["poolNote"] = "Removed from the wrong pool." if before else ""
        else:
            response["poolNote"] = "Saved to the wrong pool."
        self._save_session()

    def _finish(self, force: bool) -> bool:
        questions = self._questions()
        score = score_exam(questions, self.session["responses"])
        if not force and score["unanswered"]:
            count = score["unanswered"]
            noun = "question is" if count == 1 else "questions are"
            if not self._confirm(
                f"{count} {noun} still unanswered. They count as incorrect and are not added to the wrong pool. Finish anyway?"
            ):
                return False
        self.session["finished"] = True
        self.session["score"] = score
        self._clear()
        self._print_results(questions, score)
        self.session = None
        self._save_session()
        self._pause("Press Enter to return to the menu.")
        return True

    def _wrong_menu(self) -> None:
        while True:
            self._clear()
            print(paint("Wrong pool", "1", self.color))
            print()
            if not self.wrong:
                print("No missed questions yet. A wrong answer is saved here when you check it.")
                print()
                print("b  Back")
                if input("Choose: ").strip().lower() in {"b", "q", ""}:
                    return
                continue
            print(f"{len(self.wrong)} missed question{'s' if len(self.wrong) != 1 else ''}.")
            print("A question leaves the pool when you answer it correctly later.")
            print()
            print("1  Practice these questions")
            print("2  Review one at a time")
            print("3  Clear the pool")
            print("b  Back")
            choice = input("Choose: ").strip().lower()
            if choice in {"1", "p", "practice"}:
                self._start("wrong")
            elif choice in {"2", "r", "review"}:
                self._review_wrong()
            elif choice in {"3", "c", "clear"}:
                if self._confirm(f"Remove all {len(self.wrong)} questions from the wrong pool?"):
                    self.wrong = []
                    self._save_wrong()
            elif choice in {"b", "q", ""}:
                return

    def _review_wrong(self) -> None:
        index = 0
        while self.wrong:
            entry = self.wrong[index % len(self.wrong)]
            question = self.by_id.get(entry["id"])
            if not question:
                self.wrong.pop(index % len(self.wrong))
                self._save_wrong()
                continue
            index = index % len(self.wrong)
            self._clear()
            print(paint(f"Wrong pool {index + 1} of {len(self.wrong)}", "1", self.color))
            print(self._domain_name(question["domain"]))
            print()
            print(self._wrap(question["stem"]))
            print()
            yours = ", ".join(entry.get("selected") or []) or "none"
            print(f"Your answer: {yours}")
            print(f"Correct:     {', '.join(question['answers'])}")
            if question.get("explanation"):
                print()
                print(self._wrap(question["explanation"]))
            print()
            print("n next   p previous   d remove   b back")
            command = input("Choose: ").strip().lower()
            if command in {"b", "q", ""}:
                return
            if command == "n":
                index += 1
            elif command == "p":
                index -= 1
            elif command == "d":
                self.wrong = [item for item in self.wrong if item.get("id") != question["id"]]
                self._save_wrong()
                if not self.wrong:
                    return

    def _print_home(self) -> None:
        meta = self.meta
        print(paint("CLF-C02 exam", "1", self.color))
        print()
        mix = ", ".join(f"{domain['examCount']} {domain['name']}" for domain in meta["domains"])
        weights = " / ".join(str(round(domain["weight"] * 100)) + "%" for domain in meta["domains"])
        print(self._wrap(
            f"{meta['unique']} questions from {meta['sourceFiles']} practice sets. "
            f"Each exam draws {meta['examSize']}: {mix}. "
            f"That follows the CLF-C02 weights as closely as {meta['examSize']} questions allow ({weights})."
        ))
        print()
        print(f"Pass mark {meta['officialPass']} ({round(meta['passMark'] * 100)}%). Time {meta['minutes']} minutes.")
        print()
        for domain in meta["domains"]:
            print(f"  {domain['name']:<24} {domain['poolCount']:>4} in the pool   {domain['examCount']:>2} on the exam")
        print()
        print(f"Wrong pool: {len(self.wrong)}")
        print(f"Saved in {self.data_dir}")
        print()
        print("1  Start a new exam")
        if self.session and not self.session.get("finished"):
            done = sum(1 for item in self.session["responses"].values() if item.get("checked"))
            print(f"2  Continue the saved exam ({done} of {len(self.session['ids'])} checked)")
        print("3  Wrong pool")
        print("q  Quit")

    def _print_question(self, question: dict, response: dict) -> None:
        total = len(self.session["ids"])
        number = self.session["index"] + 1
        score = score_exam(self._questions(), self.session["responses"])
        mode = "Wrong-pool practice" if self.session["mode"] == "wrong" else "Exam"
        print(paint(f"{mode}  ·  Question {number} of {total}", "1", self.color))
        print(f"{self._domain_name(question['domain'])}  ·  {score['correct']} correct  ·  {self._clock()}")
        if self.session.get("endsAt") and self.session["endsAt"] <= datetime.now(timezone.utc).timestamp():
            print(paint("Time is up. You can still check the remaining answers.", "33", self.color))
        print()
        print(self._wrap(question["stem"]))
        print()
        for choice in question["choices"]:
            selected = choice["letter"] in response["selected"]
            is_answer = choice["letter"] in question["answers"]
            mark = ""
            code = ""
            if response["checked"] and is_answer and selected:
                mark, code = "correct", "32"
            elif response["checked"] and is_answer:
                mark, code = "correct answer", "32"
            elif response["checked"] and selected:
                mark, code = "your choice", "31"
            elif selected:
                mark, code = "selected", "36"
            line = self._wrap_choice(choice["letter"], choice["text"], mark)
            print(paint(line, code, self.color) if code else line)
        print()
        if response["checked"]:
            label = "Correct" if response["correct"] else "Wrong"
            code = "32" if response["correct"] else "31"
            note = f" The answer is {', '.join(question['answers'])}."
            extra = f" {response['poolNote']}" if response.get("poolNote") else ""
            print(paint(label + "." + note + extra, code, self.color))
            if question.get("explanation"):
                print()
                print(self._wrap(question["explanation"]))
            print()
            print("Enter next question   p previous   end finish   q save and quit")
        else:
            print("Type one or more letters, then Enter. Example: B   or   BE")
            print("n next   p previous   g 12 go to question   end finish   q save and quit")
        print(f"Practice exam {question['exam']}, question {question['number']}")

    def _print_results(self, questions: list[dict], score: dict) -> None:
        mode = "Wrong-pool practice" if self.session["mode"] == "wrong" else "Exam result"
        percent = round(1000 * score["correct"] / score["total"]) / 10 if score["total"] else 0
        print(paint(mode, "1", self.color))
        print()
        print(paint(f"{score['correct']} / {score['total']}", "1", self.color))
        verdict = ""
        if self.session["mode"] == "exam":
            if passed(score["correct"], score["total"], self.meta["passMark"]):
                verdict = " That meets the 70% pass mark."
            else:
                verdict = " That is under the 70% pass mark."
        print(f"{percent}%." + verdict)
        if score["unanswered"]:
            print(
                f"{score['unanswered']} unanswered, counted as incorrect. "
                "Unanswered questions were not added to the wrong pool."
            )
        print()
        print("By domain")
        for domain in self.meta["domains"]:
            stat = score["byDomain"].get(domain["id"])
            if not stat:
                continue
            print(f"  {domain['name']:<24} {stat['correct']} / {stat['total']}")
        print()
        print(f"Wrong pool: {len(self.wrong)}")

    def _clock(self) -> str:
        if not self.session.get("endsAt"):
            return "no timer"
        remaining = max(0, int(self.session["endsAt"] - datetime.now(timezone.utc).timestamp()))
        return f"{remaining // 60}:{remaining % 60:02d} left"

    def _current(self) -> dict:
        return self.by_id[self.session["ids"][self.session["index"]]]

    def _questions(self) -> list[dict]:
        return [self.by_id[item_id] for item_id in self.session["ids"]]

    def _response(self, question_id: str) -> dict:
        responses = self.session["responses"]
        if question_id not in responses:
            responses[question_id] = {"selected": [], "checked": False, "correct": False, "poolNote": ""}
        return responses[question_id]

    def _move(self, step: int) -> None:
        last = len(self.session["ids"]) - 1
        if step > 0 and self.session["index"] >= last:
            self._finish(False)
            return
        self.session["index"] = max(0, min(last, self.session["index"] + step))
        self._save_session()

    def _domain_name(self, domain_id: str) -> str:
        for domain in self.meta["domains"]:
            if domain["id"] == domain_id:
                return domain["name"]
        return domain_id

    def _wrap(self, text: str) -> str:
        blocks = []
        for paragraph in str(text).splitlines() or [""]:
            blocks.append(textwrap.fill(paragraph, width=self.width) if paragraph.strip() else "")
        return "\n".join(blocks)

    def _wrap_choice(self, letter: str, text: str, mark: str) -> str:
        prefix = f"  {letter}  "
        wrapped = textwrap.fill(
            text,
            width=self.width,
            initial_indent=prefix,
            subsequent_indent=" " * len(prefix),
        )
        if not mark:
            return wrapped
        return wrapped + f"   [{mark}]"

    def _confirm(self, message: str) -> bool:
        print(self._wrap(message))
        return input("Confirm [y/N]: ").strip().lower() in {"y", "yes"}

    def _say(self, message: str) -> None:
        print(self._wrap(message))

    def _pause(self, message: str = "Press Enter to continue.") -> None:
        try:
            input(message + " ")
        except EOFError:
            return

    def _clear(self) -> None:
        if not sys.stdout.isatty():
            print("\n" + ("-" * min(self.width, 60)))
            return
        os.system("cls" if os.name == "nt" else "clear")

    def _session_ok(self, session) -> bool:
        if not isinstance(session, dict) or not session.get("ids"):
            return False
        return all(item_id in self.by_id for item_id in session["ids"])

    def _load_json(self, name: str, fallback):
        path = self.data_dir / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    def _save_wrong(self) -> None:
        self._write_json("wrong-pool.json", self.wrong)

    def _save_session(self) -> None:
        if self.session is None:
            path = self.data_dir / "session.json"
            if path.exists():
                path.unlink()
            return
        self._write_json("session.json", self.session)

    def _write_json(self, name: str, payload) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def shutil_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def configure_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLF-C02 terminal exam, one question at a time.")
    parser.add_argument("--pool", type=Path, help="Question pool JSON. Defaults to the built-in pool.")
    parser.add_argument("--data-dir", type=Path, help="Folder for the wrong pool and the saved exam.")
    parser.add_argument("--seed", type=int, help="Repeat the same draw. Used for tests.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    pool_path = args.pool or (resource_root() / "assets" / "data" / "questions.json")
    if not pool_path.is_file():
        print(f"Question pool not found: {pool_path}", file=sys.stderr)
        return 1
    app = ExamApp(
        load_pool(pool_path),
        args.data_dir or default_data_dir(),
        args.seed,
        enable_color(),
    )
    try:
        return app.run()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
