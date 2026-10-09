const assert = require("assert");
const fs = require("fs");
const path = require("path");
const engine = require("../assets/js/exam-engine.js");

const payload = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "assets", "data", "questions.json"), "utf8")
);
const questions = payload.questions;
const meta = payload.meta;

function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function findStem(part) {
  const hits = questions.filter((question) => question.stem.toLowerCase().includes(part.toLowerCase()));
  assert.ok(hits.length > 0, "missing stem: " + part);
  return hits[0];
}

const expected = {
  "cloud-concepts": 8,
  "security-compliance": 9,
  "technology-services": 11,
  "billing-support": 4,
};

assert.strictEqual(meta.examSize, 32);
assert.strictEqual(meta.passMark, 0.7);
assert.strictEqual(meta.minutes, 44);
assert.strictEqual(
  meta.domains.reduce((sum, domain) => sum + domain.examCount, 0),
  32
);
meta.domains.forEach((domain) => {
  assert.strictEqual(domain.examCount, expected[domain.id], domain.id);
  assert.ok(domain.poolCount >= domain.examCount, domain.id + " pool");
});

const letters = new Set();
questions.forEach((question) => {
  assert.ok(question.id && question.stem && question.stemKey);
  assert.ok(question.choices.length >= 2);
  assert.ok(question.answers.length >= 1);
  const choiceLetters = new Set(question.choices.map((choice) => choice.letter));
  question.answers.forEach((letter) => {
    assert.ok(choiceLetters.has(letter), question.id + " answer " + letter);
    letters.add(letter);
  });
  assert.ok(expected[question.domain], question.domain);
});

assert.strictEqual(findStem("example of horizontal scaling").domain, "cloud-concepts");
assert.strictEqual(findStem("principle of elasticity").domain, "cloud-concepts");
assert.strictEqual(findStem("Shared Responsibility Model").domain, "security-compliance");
assert.strictEqual(findStem("advantage of consolidated billing").domain, "billing-support");
assert.strictEqual(findStem("valid ways for a customer to interact").domain, "technology-services");
assert.strictEqual(findStem("most cost-effective service to store").domain, "technology-services");
assert.strictEqual(findStem("billed for Linux-based").domain, "billing-support");
assert.strictEqual(findStem("AWS Cloud Computing models").domain, "cloud-concepts");
assert.strictEqual(findStem("security groups that allow unrestricted access").domain, "security-compliance");
assert.strictEqual(findStem("create a billing alarm").domain, "billing-support");
assert.strictEqual(findStem("eliminate human error").domain, "technology-services");
assert.strictEqual(findStem("user responsible for when running").domain, "security-compliance");
assert.ok(findStem("visiting the URL").stem.includes("http://status.aws.amazon.com"));

const first = engine.buildExam(questions, meta, mulberry32(7));
const second = engine.buildExam(questions, meta, mulberry32(7));
assert.strictEqual(first.length, 32);
assert.deepStrictEqual(
  first.map((question) => question.id),
  second.map((question) => question.id)
);
const counts = engine.domainCounts(first);
assert.deepStrictEqual(counts, expected);
const stems = new Set(first.map((question) => question.stemKey));
assert.strictEqual(stems.size, 32);

assert.strictEqual(engine.isCorrect(["B"], ["B"]), true);
assert.strictEqual(engine.isCorrect(["E", "B"], ["B", "E"]), true);
assert.strictEqual(engine.isCorrect(["B"], ["B", "E"]), false);
assert.strictEqual(engine.isCorrect(["A", "B"], ["B", "E"]), false);
assert.strictEqual(engine.isCorrect([], ["A"]), false);

let pool = [];
pool = engine.recordResult(pool, "q1", ["A"], false, "2026-10-09T00:00:00.000Z");
assert.strictEqual(pool.length, 1);
assert.strictEqual(pool[0].timesMissed, 1);
pool = engine.recordResult(pool, "q1", ["C"], false, "2026-10-09T01:00:00.000Z");
assert.strictEqual(pool.length, 1);
assert.strictEqual(pool[0].timesMissed, 2);
assert.deepStrictEqual(pool[0].selected, ["C"]);
pool = engine.recordResult(pool, "q1", ["B"], true, "2026-10-09T02:00:00.000Z");
assert.deepStrictEqual(pool, []);

const wrongExam = engine.buildWrongPoolExam(
  questions,
  [{ id: questions[0].id }, { id: "missing" }, { id: questions[0].id }],
  32,
  mulberry32(1)
);
assert.strictEqual(wrongExam.length, 1);
assert.strictEqual(wrongExam[0].id, questions[0].id);

const responses = {};
first.forEach((question, index) => {
  responses[question.id] = { checked: true, correct: index < 23 };
});
const score = engine.scoreExam(first, responses);
assert.strictEqual(score.correct, 23);
assert.strictEqual(score.unanswered, 0);
assert.strictEqual(engine.passed(22, 32, 0.7), false);
assert.strictEqual(engine.passed(23, 32, 0.7), true);

console.log("exam-engine tests passed (" + questions.length + " questions)");
