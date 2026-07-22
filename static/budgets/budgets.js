(function () {
  "use strict";

  // ---------- Sortable tables ----------
  function sortTable(table, columnIndex, direction) {
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    var header = table.tHead.rows[0].cells[columnIndex];
    var kind = header.getAttribute("data-sort");
    rows.sort(function (a, b) {
      var cellA = a.cells[columnIndex];
      var cellB = b.cells[columnIndex];
      var valueA = cellA ? cellA.getAttribute("data-value") || cellA.textContent : "";
      var valueB = cellB ? cellB.getAttribute("data-value") || cellB.textContent : "";
      if (kind === "number") {
        return (parseFloat(valueA) || 0) - (parseFloat(valueB) || 0);
      }
      return valueA.localeCompare(valueB);
    });
    if (direction === "desc") {
      rows.reverse();
    }
    rows.forEach(function (row) {
      tbody.appendChild(row);
    });
  }

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    if (!table.tHead) {
      return;
    }
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (header, columnIndex) {
      if (!header.hasAttribute("data-sort")) {
        return;
      }
      header.classList.add("os-sortable-th");
      header.setAttribute("tabindex", "0");
      header.setAttribute("role", "button");
      var direction = "desc";
      var activate = function () {
        sortTable(table, columnIndex, direction);
        Array.prototype.forEach.call(table.tHead.rows[0].cells, function (cell) {
          cell.removeAttribute("aria-sort");
        });
        header.setAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");
        direction = direction === "asc" ? "desc" : "asc";
      };
      header.addEventListener("click", activate);
      header.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });
  });

  // ---------- Client-side text filter ----------
  document.querySelectorAll("[data-table-filter]").forEach(function (input) {
    var table = document.getElementById(input.getAttribute("data-table-filter"));
    if (!table) {
      return;
    }
    input.addEventListener("input", function () {
      var term = input.value.trim().toLowerCase();
      Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
        var text = row.textContent.toLowerCase();
        var matches = !term || text.indexOf(term) !== -1;
        if (matches) {
          row.removeAttribute("data-filtered-out");
        } else {
          row.setAttribute("data-filtered-out", "true");
        }
        row.hidden = row.hasAttribute("data-filtered-out") || row.classList.contains("os-budget-row--extra-collapsed");
      });
    });
  });

  // ---------- Show all / show top 10 ----------
  document.querySelectorAll("[data-show-all]").forEach(function (button) {
    var table = document.getElementById(button.getAttribute("data-show-all"));
    if (!table) {
      return;
    }
    var expanded = false;
    var defaultLabel = button.textContent;
    button.addEventListener("click", function () {
      expanded = !expanded;
      Array.prototype.forEach.call(table.querySelectorAll(".os-budget-row--extra"), function (row) {
        row.hidden = !expanded;
      });
      button.textContent = expanded ? "Show top 10" : defaultLabel;
    });
  });

  // ---------- CSV download ----------
  function tableToCsv(table) {
    function csvCell(value) {
      var text = String(value == null ? "" : value).replace(/"/g, '""');
      return '"' + text + '"';
    }
    var lines = [];
    var headerCells = table.tHead ? Array.prototype.slice.call(table.tHead.rows[0].cells) : [];
    lines.push(headerCells.map(function (cell) {
      return csvCell(cell.textContent.trim());
    }).join(","));
    Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
      if (row.hidden) {
        return;
      }
      var cells = Array.prototype.slice.call(row.cells);
      lines.push(cells.map(function (cell) {
        return csvCell(cell.getAttribute("data-value") || cell.textContent.trim());
      }).join(","));
    });
    return lines.join("\r\n");
  }

  document.querySelectorAll("[data-csv-source]").forEach(function (button) {
    button.addEventListener("click", function () {
      var table = document.getElementById(button.getAttribute("data-csv-source"));
      if (!table) {
        return;
      }
      var csv = tableToCsv(table);
      var blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = (table.id || "budget-data") + ".csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    });
  });

  // ---------- Sample question chips ----------
  document.querySelectorAll("[data-budget-question]").forEach(function (button) {
    button.addEventListener("click", function () {
      var field = document.getElementById("question");
      if (!field) {
        return;
      }
      field.value = button.dataset.budgetQuestion;
      field.focus();
      var form = document.getElementById("budget-ask-form");
      if (form && window.BudgetChat) {
        window.BudgetChat.submit(button.dataset.budgetQuestion);
      }
    });
  });

  // ---------- Streaming chat thread ----------
  var chatSection = document.getElementById("budget-chat");
  if (!chatSection || typeof fetch !== "function" || !window.ReadableStream) {
    return;
  }

  var form = document.getElementById("budget-ask-form");
  var thread = document.getElementById("budget-thread");
  var status = document.getElementById("budget-status");
  var samples = document.getElementById("budget-samples");
  var textarea = document.getElementById("question");
  var streamUrl = chatSection.getAttribute("data-stream-url");
  var jurisdiction = chatSection.getAttribute("data-jurisdiction");
  var year = chatSection.getAttribute("data-year");
  var previousResponseId = null;

  function csrfToken() {
    var input = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function addTurn(question) {
    var turn = document.createElement("div");
    turn.className = "os-budget-thread__turn";
    var q = document.createElement("div");
    q.className = "os-budget-thread__question";
    q.textContent = question;
    var a = document.createElement("div");
    a.className = "os-budget-thread__answer";
    turn.appendChild(q);
    turn.appendChild(a);
    thread.appendChild(turn);
    thread.scrollTop = thread.scrollHeight;
    return a;
  }

  function linkify(text) {
    var urlPattern = /(https?:\/\/[^\s)]+)/g;
    var frag = document.createDocumentFragment();
    var lastIndex = 0;
    var match;
    while ((match = urlPattern.exec(text)) !== null) {
      frag.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      var link = document.createElement("a");
      link.href = match[0];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = match[0];
      frag.appendChild(link);
      lastIndex = match.index + match[0].length;
    }
    frag.appendChild(document.createTextNode(text.slice(lastIndex)));
    return frag;
  }

  function renderAnswerText(container, text) {
    text.split("\n").forEach(function (line, index) {
      if (index > 0) {
        container.appendChild(document.createElement("br"));
      }
      container.appendChild(linkify(line));
    });
  }

  function money(value) {
    if (value === null || value === undefined) {
      return "—";
    }
    var abs = Math.abs(value);
    return (value < 0 ? "-$" : "$") + abs.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function renderTable(container, kind, data) {
    var table = document.createElement("table");
    table.className = "os-budget-thread__table";
    var thead = document.createElement("thead");
    var tbody = document.createElement("tbody");
    var rows = data.rows || [];
    var sourceLine = document.createElement("p");
    sourceLine.className = "os-budget-thread__source";

    function headerRow(labels) {
      var tr = document.createElement("tr");
      labels.forEach(function (label) {
        var th = document.createElement("th");
        th.scope = "col";
        th.textContent = label;
        tr.appendChild(th);
      });
      thead.appendChild(tr);
    }

    function cell(tr, text) {
      var td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }

    function citationLink(tr, sourceUrl, page) {
      var td = document.createElement("td");
      if (sourceUrl && page) {
        var a = document.createElement("a");
        a.href = sourceUrl + "#page=" + page;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = "p. " + page;
        td.appendChild(a);
      } else {
        td.textContent = "Not cited";
      }
      tr.appendChild(td);
    }

    if (kind === "breakdown") {
      headerRow(["Name", "Amount", "% of total", "Page"]);
      rows.forEach(function (row) {
        var tr = document.createElement("tr");
        cell(tr, row.name);
        cell(tr, money(row.amount));
        cell(tr, row.percent_of_side_total != null ? row.percent_of_side_total.toFixed(1) + "%" : "—");
        citationLink(tr, row.source_url, row.pages && row.pages[0]);
        tbody.appendChild(tr);
      });
    } else if (kind === "comparison" || kind === "per_capita") {
      var labels = ["Jurisdiction", "Amount"];
      if (kind === "per_capita") {
        labels.push("Population", "Per resident");
      }
      labels.push("Page");
      headerRow(labels);
      rows.forEach(function (row) {
        var tr = document.createElement("tr");
        cell(tr, row.jurisdiction.name);
        cell(tr, row.available ? money(row.amount) : "Not available");
        if (kind === "per_capita") {
          cell(tr, row.population != null ? row.population.toLocaleString() : "—");
          cell(tr, row.per_capita != null ? money(row.per_capita) : "—");
        }
        var citation = (row.citations || [])[0];
        citationLink(tr, row.source_url, citation && citation.page);
        tbody.appendChild(tr);
      });
    } else if (kind === "trend") {
      headerRow(["Year", "Amount"]);
      rows.forEach(function (row) {
        var tr = document.createElement("tr");
        cell(tr, row.year);
        cell(tr, row.amount != null ? money(row.amount) : "Not available");
        tbody.appendChild(tr);
      });
    } else if (kind === "search" || kind === "search_all") {
      var matchRows = kind === "search" ? [{ jurisdiction: data.jurisdiction, document: data.document, matches: data.matches }] : data.results;
      headerRow(["Jurisdiction", "Page", "Snippet"]);
      (matchRows || []).forEach(function (group) {
        (group.matches || []).forEach(function (match) {
          var tr = document.createElement("tr");
          cell(tr, group.jurisdiction.name);
          citationLink(tr, group.document.source_url, match.page);
          cell(tr, match.snippet);
          tbody.appendChild(tr);
        });
      });
    } else if (kind === "pages") {
      headerRow(["Page", "Text"]);
      (data.pages || []).forEach(function (page) {
        var tr = document.createElement("tr");
        cell(tr, page.page);
        cell(tr, page.text.slice(0, 400));
        tbody.appendChild(tr);
      });
      sourceLine.textContent = "Source: " + data.document.source_url;
    } else {
      return null;
    }

    table.appendChild(thead);
    table.appendChild(tbody);
    var wrap = document.createElement("div");
    wrap.className = "os-budget-table-wrap";
    wrap.appendChild(table);
    container.appendChild(wrap);
    if (sourceLine.textContent) {
      container.appendChild(sourceLine);
    }
    return table;
  }

  function renderSuggestions(suggestions) {
    if (!samples || !suggestions || !suggestions.length) {
      return;
    }
    samples.innerHTML = "<h3>Follow up</h3>";
    suggestions.forEach(function (text) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.addEventListener("click", function () {
        window.BudgetChat.submit(text);
      });
      samples.appendChild(button);
    });
  }

  function setStatus(message) {
    if (!message) {
      status.hidden = true;
      status.textContent = "";
      return;
    }
    status.hidden = false;
    status.textContent = message;
  }

  async function streamQuestion(question) {
    var answerEl = addTurn(question);
    setStatus("Thinking…");
    var body = new URLSearchParams();
    body.set("question", question);
    body.set("jurisdiction", jurisdiction || "");
    body.set("year", year || "");
    body.set("previous_response_id", previousResponseId || "");

    var response;
    try {
      response = await fetch(streamUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": csrfToken(),
        },
        body: body.toString(),
      });
    } catch (err) {
      setStatus(null);
      renderAnswerText(answerEl, "Budget chat is temporarily unavailable. Please try again.");
      return;
    }

    if (!response.body) {
      setStatus(null);
      renderAnswerText(answerEl, "Budget chat is temporarily unavailable. Please try again.");
      return;
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) {
        break;
      }
      buffer += decoder.decode(chunk.value, { stream: true });
      var parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (var i = 0; i < parts.length; i++) {
        var line = parts[i];
        if (!line.startsWith("data: ")) {
          continue;
        }
        var event;
        try {
          event = JSON.parse(line.slice(6));
        } catch (err) {
          continue;
        }
        if (event.type === "status") {
          setStatus(event.message);
        } else if (event.type === "context") {
          jurisdiction = event.jurisdiction;
          year = event.year;
        } else if (event.type === "heartbeat") {
          // keep-alive only
        } else if (event.type === "final") {
          setStatus(null);
          renderAnswerText(answerEl, event.answer || "");
          if (event.structured_result && event.structured_result.kind) {
            renderTable(answerEl, event.structured_result.kind, event.structured_result.data);
          }
          if (event.response_id) {
            previousResponseId = event.response_id;
          }
          renderSuggestions(event.suggestions);
        }
      }
    }
    setStatus(null);
  }

  window.BudgetChat = {
    submit: function (question) {
      textarea.value = "";
      streamQuestion(question);
    },
  };

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = textarea.value.trim();
    if (!question) {
      return;
    }
    window.BudgetChat.submit(question);
  });
})();
