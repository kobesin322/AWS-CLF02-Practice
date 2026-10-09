/* Exam dashboard UI. Scoring rules live in exam-engine.js. */
(function () {
  var engine = window.ExamEngine;
  var WRONG_KEY = "clf02-wrong-pool-v1";
  var SESSION_KEY = "clf02-active-exam-v1";

  var ui = {
    data: null,
    byId: new Map(),
    wrong: [],
    session: null,
    screen: "loading",
    timerId: null,
    timeUpNoted: false,
    error: "",
  };

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    var app = document.getElementById("app");
    app.addEventListener("click", onClick);
    app.addEventListener("change", onChoiceChange);
    document.addEventListener("keydown", onKeydown);
    loadPool();
  }

  function loadPool() {
    render();
    fetch("/assets/data/questions.json")
      .then(function (response) {
        if (!response.ok) throw new Error("status " + response.status);
        return response.json();
      })
      .then(function (data) {
        ui.data = data;
        ui.byId = new Map(data.questions.map(function (question) {
          return [question.id, question];
        }));
        ui.wrong = loadWrong().filter(function (item) {
          return ui.byId.has(item.id);
        });
        saveWrong();
        ui.session = loadSession();
        ui.screen = "home";
        render();
      })
      .catch(function () {
        ui.screen = "error";
        ui.error = "The question pool did not load. Refresh the page and try again.";
        render();
      });
  }

  function onClick(event) {
    var target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    var action = target.getAttribute("data-action");
    if (action === "start") startExam("exam");
    else if (action === "continue") openSession();
    else if (action === "discard") discardSession();
    else if (action === "check") checkCurrent();
    else if (action === "next") move(1);
    else if (action === "prev") move(-1);
    else if (action === "goto") {
      ui.session.index = Number(target.getAttribute("data-index"));
      saveSession();
      render();
    } else if (action === "finish") finishExam(false);
    else if (action === "review") reviewExam();
    else if (action === "home") goHome();
    else if (action === "wrong") {
      ui.screen = "wrong";
      render();
    } else if (action === "practice-wrong") startExam("wrong");
    else if (action === "remove-wrong") removeWrong(target.getAttribute("data-id"));
    else if (action === "clear-wrong") clearWrong();
  }

  function onChoiceChange(event) {
    var input = event.target;
    if (!input.matches("input[name='choice']") || !ui.session) return;
    var question = currentQuestion();
    var response = ensureResponse(question.id);
    if (response.checked) return;
    if (input.type === "radio") {
      response.selected = [input.value];
    } else if (input.checked) {
      if (response.selected.indexOf(input.value) === -1) response.selected.push(input.value);
    } else {
      response.selected = response.selected.filter(function (letter) {
        return letter !== input.value;
      });
    }
    response.selected.sort();
    saveSession();
    var check = document.getElementById("check-answer");
    if (check) check.disabled = response.selected.length === 0;
  }

  function onKeydown(event) {
    if (!ui.session || ui.screen !== "exam") return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    var question = currentQuestion();
    if (!question) return;
    var response = ensureResponse(question.id);
    var letter = event.key.toUpperCase();
    if (/^[A-F]$/.test(letter) && question.choices.some(function (choice) { return choice.letter === letter; })) {
      if (response.checked) return;
      var input = document.querySelector("input[name='choice'][value='" + letter + "']");
      if (!input) return;
      if (input.type === "radio") {
        input.checked = true;
        response.selected = [letter];
      } else {
        input.checked = !input.checked;
        onChoiceChange({ target: input });
        return;
      }
      saveSession();
      var check = document.getElementById("check-answer");
      if (check) check.disabled = false;
      return;
    }
    var activateTarget = event.target && event.target.closest ? event.target.closest("button, a") : null;
    if (event.key === "Enter" && !activateTarget) {
      event.preventDefault();
      if (!response.checked && response.selected.length) checkCurrent();
      else if (response.checked) {
        if (ui.session.index < ui.session.ids.length - 1) move(1);
        else finishExam(false);
      }
    }
  }

  function startExam(mode) {
    if (ui.session && !ui.session.finished) {
      var discard = window.confirm("Discard the exam in progress and start a new one?");
      if (!discard) return;
    }
    ui.error = "";
    try {
      var questions;
      if (mode === "wrong") {
        questions = engine.buildWrongPoolExam(ui.data.questions, ui.wrong, ui.data.meta.examSize);
        if (!questions.length) return;
      } else {
        questions = engine.buildExam(ui.data.questions, ui.data.meta);
      }
      ui.session = {
        mode: mode,
        ids: questions.map(function (question) { return question.id; }),
        index: 0,
        responses: {},
        endsAt: mode === "exam" ? Date.now() + ui.data.meta.minutes * 60 * 1000 : null,
        finished: false,
        startedAt: new Date().toISOString(),
      };
      ui.timeUpNoted = false;
      saveSession();
      ui.screen = "exam";
      render();
    } catch (error) {
      ui.error = error.shortages
        ? "This exam needs more questions in " + error.shortages.map(function (item) {
          return item.name + " (" + item.have + " of " + item.need + ")";
        }).join(", ") + "."
        : "The exam could not be built.";
      ui.screen = "home";
      render();
    }
  }

  function openSession() {
    if (!ui.session) return;
    ui.screen = ui.session.finished ? "results" : "exam";
    render();
  }

  function discardSession() {
    ui.session = null;
    sessionStorage.removeItem(SESSION_KEY);
    stopTimer();
    ui.screen = "home";
    render();
  }

  function checkCurrent() {
    var question = currentQuestion();
    var response = ensureResponse(question.id);
    if (!response.selected.length || response.checked) return;
    response.checked = true;
    response.correct = engine.isCorrect(response.selected, question.answers);
    var before = ui.wrong.some(function (item) { return item.id === question.id; });
    ui.wrong = engine.recordResult(ui.wrong, question.id, response.selected, response.correct);
    saveWrong();
    response.poolNote = response.correct
      ? (before ? "Removed from the wrong pool." : "")
      : "Saved to the wrong pool.";
    saveSession();
    render();
    var result = document.getElementById("answer-result");
    if (result) result.focus();
  }

  function move(step) {
    ui.session.index = Math.max(0, Math.min(ui.session.ids.length - 1, ui.session.index + step));
    saveSession();
    render();
    var stem = document.getElementById("question-stem");
    if (stem) stem.focus();
  }

  function finishExam(force) {
    var questions = sessionQuestions();
    var score = engine.scoreExam(questions, ui.session.responses);
    if (!force && score.unanswered > 0) {
      var leave = window.confirm(
        score.unanswered + " question" + (score.unanswered === 1 ? " is" : "s are") +
        " still unanswered. Unanswered questions count as incorrect and are not added to the wrong pool. Finish anyway?"
      );
      if (!leave) return;
    }
    ui.session.finished = true;
    ui.session.score = score;
    saveSession();
    ui.screen = "results";
    stopTimer();
    render();
  }

  function reviewExam() {
    ui.session.index = 0;
    ui.screen = "exam";
    render();
  }

  function goHome() {
    stopTimer();
    ui.screen = "home";
    render();
  }

  function removeWrong(id) {
    ui.wrong = ui.wrong.filter(function (item) { return item.id !== id; });
    saveWrong();
    render();
  }

  function clearWrong() {
    if (!ui.wrong.length) return;
    if (!window.confirm("Remove all " + ui.wrong.length + " questions from the wrong pool?")) return;
    ui.wrong = [];
    saveWrong();
    render();
  }

  function currentQuestion() {
    return ui.byId.get(ui.session.ids[ui.session.index]);
  }

  function sessionQuestions() {
    return ui.session.ids.map(function (id) { return ui.byId.get(id); }).filter(Boolean);
  }

  function ensureResponse(id) {
    if (!ui.session.responses[id]) {
      ui.session.responses[id] = { selected: [], checked: false, correct: false, poolNote: "" };
    }
    return ui.session.responses[id];
  }

  function domainName(id) {
    var match = ui.data.meta.domains.filter(function (domain) { return domain.id === id; })[0];
    return match ? match.name : id;
  }

  function render() {
    stopTimer();
    var app = document.getElementById("app");
    if (ui.screen === "loading") {
      app.innerHTML = '<p class="panel" role="status">Loading question pools…</p>';
      return;
    }
    if (ui.screen === "error") {
      app.innerHTML = '<p class="panel banner wrong" role="alert">' + escapeHtml(ui.error) + "</p>";
      return;
    }
    if (ui.screen === "home") app.innerHTML = homeHtml();
    else if (ui.screen === "exam") {
      app.innerHTML = examHtml();
      startTimer();
    } else if (ui.screen === "results") app.innerHTML = resultsHtml();
    else if (ui.screen === "wrong") app.innerHTML = wrongHtml();
  }

  function homeHtml() {
    var meta = ui.data.meta;
    var mix = meta.domains.map(function (domain) {
      return domain.examCount + " " + domain.name;
    }).join(", ");
    var cards = meta.domains.map(function (domain) {
      var official = Math.round(domain.weight * 100);
      return (
        '<li class="pool ' + domain.id + '">' +
          "<h3>" + escapeHtml(domain.name) + "</h3>" +
          "<p><strong>" + domain.poolCount + "</strong> in the pool</p>" +
          "<p><strong>" + domain.examCount + "</strong> on each exam · " + official + "% of CLF-C02</p>" +
        "</li>"
      );
    }).join("");
    var sessionNote = "";
    if (ui.session && ui.session.ids && ui.session.ids.length) {
      var done = Object.keys(ui.session.responses).filter(function (id) {
        return ui.session.responses[id].checked;
      }).length;
      sessionNote =
        '<div class="notice"><p>' +
        (ui.session.finished
          ? "Your last " + (ui.session.mode === "wrong" ? "wrong-pool practice" : "exam") + " is saved in this tab."
          : "An exam is in progress in this tab (" + done + " of " + ui.session.ids.length + " checked).") +
        '</p><div class="actions">' +
        '<button class="btn btn-secondary" type="button" data-action="continue">' +
        (ui.session.finished ? "See that result" : "Continue") +
        '</button><button class="btn btn-secondary" type="button" data-action="discard">Discard</button></div></div>';
    }
    var error = ui.error ? '<p class="banner wrong" role="alert">' + escapeHtml(ui.error) + "</p>" : "";
    return (
      error + sessionNote +
      '<section class="panel"><h2>Question pools</h2>' +
      '<p class="lede">All ' + meta.unique + ' unique questions from ' + meta.sourceFiles +
      ' practice sets are split into the four CLF-C02 domains. A new exam draws ' + meta.examSize +
      ' at random: ' + escapeHtml(mix) + '. That is the closest whole-question mix to ' +
      meta.domains.map(function (domain) { return Math.round(domain.weight * 100) + "%"; }).join(" / ") +
      '.</p><ul class="pools">' + cards + "</ul>" +
      '<div class="actions"><button class="btn btn-primary" type="button" data-action="start">Start ' +
      meta.examSize + '-question exam</button>' +
      '<button class="btn btn-secondary" type="button" data-action="wrong">Wrong pool (' + ui.wrong.length +
      ")</button></div>" +
      '<p class="lede">The official exam is ' + meta.officialQuestions + ' questions in ' + meta.officialMinutes +
      ' minutes, with a pass mark of ' + meta.officialPass + '. This sitting uses ' + meta.minutes +
      ' minutes and the same 70% mark. Pick one or more choices, then click Check answer. A wrong answer is saved in the wrong pool on this browser.</p></section>'
    );
  }

  function examHtml() {
    var question = currentQuestion();
    var response = ensureResponse(question.id);
    var total = ui.session.ids.length;
    var multi = question.answers.length > 1;
    var inputType = multi ? "checkbox" : "radio";
    var choices = question.choices.map(function (choice) {
      var selected = response.selected.indexOf(choice.letter) !== -1;
      var isAnswer = question.answers.indexOf(choice.letter) !== -1;
      var klass = "choice";
      var mark = "";
      if (response.checked) {
        klass += " is-locked";
        if (isAnswer && selected) {
          klass += " is-correct";
          mark = '<span class="mark">Correct</span>';
        } else if (isAnswer) {
          klass += " is-missed";
          mark = '<span class="mark">Correct answer</span>';
        } else if (selected) {
          klass += " is-wrong";
          mark = '<span class="mark">Your choice</span>';
        }
      }
      return (
        '<label class="' + klass + '">' +
          '<input type="' + inputType + '" name="choice" value="' + choice.letter + '"' +
          (selected ? " checked" : "") + (response.checked ? " disabled" : "") + ">" +
          '<span class="letter">' + choice.letter + "</span>" +
          '<span class="text">' + rich(choice.text) + "</span>" + mark +
        "</label>"
      );
    }).join("");
    var result = "";
    if (response.checked) {
      result =
        '<div id="answer-result" class="banner ' + (response.correct ? "correct" : "wrong") +
        '" role="status" tabindex="-1"><strong>' + (response.correct ? "Correct" : "Wrong") + ".</strong> " +
        "The answer is " + question.answers.join(", ") + "." +
        (response.poolNote ? " " + escapeHtml(response.poolNote) : "") + "</div>";
    }
    var explanation = response.checked && question.explanation
      ? '<div class="explanation"><h3>Explanation</h3>' + rich(question.explanation) + "</div>"
      : "";
    var dots = ui.session.ids.map(function (id, index) {
      var item = ui.session.responses[id];
      var klass = "dot";
      var state = "not checked";
      if (item && item.checked) {
        klass += item.correct ? " is-correct" : " is-wrong";
        state = item.correct ? "correct" : "wrong";
      }
      return '<button type="button" class="' + klass + '" data-action="goto" data-index="' + index + '"' +
        (index === ui.session.index ? ' aria-current="true"' : "") +
        ' aria-label="Question ' + (index + 1) + ", " + state + '">' + (index + 1) + "</button>";
    }).join("");
    var score = engine.scoreExam(sessionQuestions(), ui.session.responses);
    var last = ui.session.index === total - 1;
    var nextLabel = last ? "See results" : "Next";
    var nextAction = last ? "finish" : "next";
    var time = timerHtml();
    var modeLabel = ui.session.mode === "wrong" ? "Wrong-pool practice" : "Exam";
    var timeUp = ui.session.endsAt && ui.session.endsAt <= Date.now()
      ? '<p class="banner neutral" role="status">Time is up. You can still check the remaining answers.</p>'
      : "";
    var endLabel = ui.session.mode === "wrong" ? "End practice" : "End exam";
    return (
      '<section class="panel" aria-labelledby="question-stem">' +
        '<div class="exam-bar"><div><p class="meta-line">' + modeLabel + " · Question " + (ui.session.index + 1) +
        " of " + total + " · " + score.correct + " correct</p>" +
        '<span class="pill ' + question.domain + '">' + escapeHtml(domainName(question.domain)) + "</span></div>" +
        time + "</div>" + timeUp +
        '<h2 id="question-stem" class="stem" tabindex="-1">' + rich(question.stem) + "</h2>" +
        '<fieldset class="choices"><legend class="sr-only">' +
        (multi ? "Select every correct choice" : "Select one choice") + "</legend>" + choices + "</fieldset>" +
        result + explanation +
        '<div class="actions">' +
          '<button class="btn btn-secondary" type="button" data-action="prev"' +
          (ui.session.index === 0 ? " disabled" : "") + ">Previous</button>" +
          '<button id="check-answer" class="btn btn-primary" type="button" data-action="check"' +
          (response.checked || !response.selected.length ? " disabled" : "") + ">Check answer</button>" +
          (response.checked
            ? '<button class="btn btn-primary" type="button" data-action="' + nextAction + '">' + nextLabel + "</button>"
            : "") +
          '<button class="btn btn-secondary" type="button" data-action="finish">' + endLabel + "</button>" +
        "</div>" +
        '<div class="dots" aria-label="Questions">' + dots + "</div>" +
        '<p class="meta-line">Practice exam ' + question.exam + ", question " + question.number +
        ". Keys A through " + question.choices[question.choices.length - 1].letter + " select a choice. Enter checks it.</p>" +
      "</section>"
    );
  }

  function resultsHtml() {
    var questions = sessionQuestions();
    var score = engine.scoreExam(questions, ui.session.responses);
    var passMark = ui.data.meta.passMark;
    var percent = score.total ? Math.round((1000 * score.correct) / score.total) / 10 : 0;
    var didPass = ui.session.mode === "exam" && engine.passed(score.correct, score.total, passMark);
    var verdict = "";
    if (ui.session.mode === "exam") {
      verdict = didPass
        ? " That meets the 70% pass mark."
        : " That is under the 70% pass mark.";
    }
    var rows = ui.data.meta.domains.map(function (domain) {
      var stat = score.byDomain[domain.id];
      if (!stat) return "";
      return "<li><span>" + escapeHtml(domain.name) + "</span><span>" + stat.correct + " / " + stat.total + "</span></li>";
    }).join("");
    var unanswered = score.unanswered
      ? "<p>" + score.unanswered + " unanswered, counted as incorrect. Unanswered questions were not added to the wrong pool.</p>"
      : "";
    return (
      '<section class="panel"><p class="meta-line">' +
      (ui.session.mode === "wrong" ? "Wrong-pool practice" : "Exam result") + "</p>" +
      '<p class="score-number">' + score.correct + " / " + score.total + "</p>" +
      "<p><strong>" + percent + "%</strong>" + verdict + "</p>" + unanswered +
      "<h2>By domain</h2><ul class=\"breakdown\">" + rows + "</ul>" +
      '<div class="actions">' +
      '<button class="btn btn-secondary" type="button" data-action="review">Review answers</button>' +
      '<button class="btn btn-primary" type="button" data-action="start">New 32-question exam</button>' +
      '<button class="btn btn-secondary" type="button" data-action="wrong">Wrong pool (' + ui.wrong.length + ")</button>" +
      '<button class="btn btn-secondary" type="button" data-action="home">Back</button></div></section>'
    );
  }

  function wrongHtml() {
    if (!ui.wrong.length) {
      return (
        '<section class="panel"><h2>Wrong pool</h2>' +
        "<p>No missed questions yet. When you check an answer and get it wrong, the question is saved here on this browser.</p>" +
        '<div class="actions"><button class="btn btn-secondary" type="button" data-action="home">Back</button></div></section>'
      );
    }
    var items = ui.wrong.map(function (entry) {
      var question = ui.byId.get(entry.id);
      if (!question) return "";
      var yours = entry.selected.length ? entry.selected.join(", ") : "none";
      var when = "";
      var parsed = Date.parse(entry.missedAt);
      if (!isNaN(parsed)) when = new Date(parsed).toLocaleString();
      return (
        '<article class="panel wrong-item"><div class="item-top"><h3>' + escapeHtml(domainName(question.domain)) +
        "</h3><button class=\"icon-btn\" type=\"button\" data-action=\"remove-wrong\" data-id=\"" + question.id +
        "\">Remove</button></div><p>" + rich(question.stem) + "</p>" +
        "<p><strong>Your answer:</strong> " + escapeHtml(yours) +
        " · <strong>Correct:</strong> " + escapeHtml(question.answers.join(", ")) + "</p>" +
        (question.explanation ? "<p>" + rich(question.explanation) + "</p>" : "") +
        "<p class=\"meta-line\">Missed " + entry.timesMissed + " time" + (entry.timesMissed === 1 ? "" : "s") +
        (when ? " · " + escapeHtml(when) : "") + " · Practice exam " + question.exam + "</p></article>"
      );
    }).join("");
    var practiceCount = Math.min(ui.wrong.length, ui.data.meta.examSize);
    return (
      '<section class="panel"><h2>Wrong pool</h2>' +
      "<p>" + ui.wrong.length + " missed question" + (ui.wrong.length === 1 ? "" : "s") +
      ". A question leaves the pool when you answer it correctly later. Practice uses " +
      practiceCount + " of them.</p>" +
      '<div class="actions"><button class="btn btn-primary" type="button" data-action="practice-wrong">Practice wrong pool</button>' +
      '<button class="btn btn-secondary" type="button" data-action="clear-wrong">Clear pool</button>' +
      '<button class="btn btn-secondary" type="button" data-action="home">Back</button></div></section>' +
      '<div class="wrong-list">' + items + "</div>"
    );
  }

  function timerHtml() {
    if (!ui.session.endsAt) return "";
    var remaining = Math.max(0, ui.session.endsAt - Date.now());
    var totalSeconds = Math.ceil(remaining / 1000);
    var minutes = Math.floor(totalSeconds / 60);
    var seconds = totalSeconds % 60;
    var label = String(minutes) + ":" + (seconds < 10 ? "0" : "") + seconds;
    var over = remaining <= 0;
    return '<p class="timer' + (over ? " over" : "") + '" aria-label="Time remaining">' + label + "</p>";
  }

  function startTimer() {
    if (!ui.session || !ui.session.endsAt || ui.screen !== "exam") return;
    ui.timerId = window.setInterval(function () {
      var slot = document.querySelector(".timer");
      if (!slot || !ui.session || !ui.session.endsAt) return;
      var remaining = ui.session.endsAt - Date.now();
      if (remaining <= 0) {
        if (!ui.timeUpNoted) {
          ui.timeUpNoted = true;
          render();
        }
        return;
      }
      var totalSeconds = Math.ceil(remaining / 1000);
      var minutes = Math.floor(totalSeconds / 60);
      var seconds = totalSeconds % 60;
      slot.textContent = String(minutes) + ":" + (seconds < 10 ? "0" : "") + seconds;
    }, 1000);
  }

  function stopTimer() {
    if (ui.timerId) {
      window.clearInterval(ui.timerId);
      ui.timerId = null;
    }
  }

  function loadWrong() {
    try {
      var parsed = JSON.parse(localStorage.getItem(WRONG_KEY) || "[]");
      if (!Array.isArray(parsed)) return [];
      return parsed.filter(function (item) {
        return item && typeof item.id === "string" && Array.isArray(item.selected);
      });
    } catch (error) {
      return [];
    }
  }

  function saveWrong() {
    localStorage.setItem(WRONG_KEY, JSON.stringify(ui.wrong));
  }

  function loadSession() {
    try {
      var parsed = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
      if (!parsed || !Array.isArray(parsed.ids) || !parsed.ids.length) return null;
      if (!parsed.ids.every(function (id) { return ui.byId.has(id); })) return null;
      return parsed;
    } catch (error) {
      return null;
    }
  }

  function saveSession() {
    if (!ui.session) {
      sessionStorage.removeItem(SESSION_KEY);
      return;
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(ui.session));
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  function rich(value) {
    return escapeHtml(value)
      .replace(/\n/g, "<br>")
      .replace(/(https?:\/\/[^\s<]+)/g, function (url) {
        return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>";
      });
  }
})();
