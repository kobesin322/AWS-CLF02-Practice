/* CLF-C02 exam assembly and scoring. No DOM. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ExamEngine = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  function planFromMeta(meta) {
    return {
      examSize: meta.examSize,
      passMark: meta.passMark,
      minutes: meta.minutes,
      domains: meta.domains.map(function (domain) {
        return {
          id: domain.id,
          name: domain.name,
          weight: domain.weight,
          examCount: domain.examCount,
          poolCount: domain.poolCount,
        };
      }),
    };
  }

  function shuffle(items, random) {
    var copy = items.slice();
    for (var i = copy.length - 1; i > 0; i -= 1) {
      var j = Math.floor(random() * (i + 1));
      var swap = copy[i];
      copy[i] = copy[j];
      copy[j] = swap;
    }
    return copy;
  }

  function buildExam(questions, meta, random) {
    var rng = random || Math.random;
    var plan = planFromMeta(meta);
    var byDomain = {};
    plan.domains.forEach(function (domain) {
      byDomain[domain.id] = [];
    });
    questions.forEach(function (question) {
      if (byDomain[question.domain]) byDomain[question.domain].push(question);
    });

    var picked = [];
    var usedStems = {};
    var shortages = [];
    plan.domains.forEach(function (domain) {
      var pool = shuffle(byDomain[domain.id], rng);
      var chosen = [];
      for (var i = 0; i < pool.length && chosen.length < domain.examCount; i += 1) {
        var question = pool[i];
        if (usedStems[question.stemKey]) continue;
        usedStems[question.stemKey] = true;
        chosen.push(question);
      }
      if (chosen.length < domain.examCount) {
        shortages.push({
          id: domain.id,
          name: domain.name,
          need: domain.examCount,
          have: chosen.length,
        });
      }
      picked = picked.concat(chosen);
    });

    if (shortages.length) {
      var error = new Error("Not enough questions to fill the domain mix.");
      error.shortages = shortages;
      throw error;
    }
    return shuffle(picked, rng);
  }

  function buildWrongPoolExam(questions, wrongEntries, limit, random) {
    var rng = random || Math.random;
    var byId = {};
    questions.forEach(function (question) {
      byId[question.id] = question;
    });
    var available = [];
    var seen = {};
    wrongEntries.forEach(function (entry) {
      var question = byId[entry.id];
      if (!question || seen[question.stemKey]) return;
      seen[question.stemKey] = true;
      available.push(question);
    });
    var shuffled = shuffle(available, rng);
    if (typeof limit === "number") return shuffled.slice(0, limit);
    return shuffled;
  }

  function isCorrect(selected, answers) {
    if (!selected || selected.length !== answers.length) return false;
    var want = {};
    answers.forEach(function (letter) {
      want[letter] = true;
    });
    for (var i = 0; i < selected.length; i += 1) {
      if (!want[selected[i]]) return false;
    }
    return true;
  }

  function recordResult(pool, questionId, selected, correct, now) {
    var rest = pool.filter(function (item) {
      return item.id !== questionId;
    });
    if (correct) return rest;
    var previous = null;
    for (var i = 0; i < pool.length; i += 1) {
      if (pool[i].id === questionId) previous = pool[i];
    }
    return [
      {
        id: questionId,
        selected: selected.slice(),
        missedAt: now || new Date().toISOString(),
        timesMissed: previous ? previous.timesMissed + 1 : 1,
      },
    ].concat(rest);
  }

  function scoreExam(questions, responses) {
    var correct = 0;
    var checked = 0;
    var byDomain = {};
    questions.forEach(function (question) {
      if (!byDomain[question.domain]) {
        byDomain[question.domain] = { correct: 0, total: 0 };
      }
      byDomain[question.domain].total += 1;
      var response = responses[question.id];
      if (response && response.checked) {
        checked += 1;
        if (response.correct) {
          correct += 1;
          byDomain[question.domain].correct += 1;
        }
      }
    });
    return {
      correct: correct,
      checked: checked,
      unanswered: questions.length - checked,
      total: questions.length,
      byDomain: byDomain,
    };
  }

  function passed(correct, total, passMark) {
    return total > 0 && correct / total >= passMark;
  }

  function domainCounts(questions) {
    var counts = {};
    questions.forEach(function (question) {
      counts[question.domain] = (counts[question.domain] || 0) + 1;
    });
    return counts;
  }

  return {
    planFromMeta: planFromMeta,
    shuffle: shuffle,
    buildExam: buildExam,
    buildWrongPoolExam: buildWrongPoolExam,
    isCorrect: isCorrect,
    recordResult: recordResult,
    scoreExam: scoreExam,
    passed: passed,
    domainCounts: domainCounts,
  };
});
