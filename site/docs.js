// Renders the tables and requirement lists of the documentation from data.js
// (static, trusted texts).
"use strict";

(() => {
  const { alarms, report, alarmAttributes, eventTypes } = window.BGM;

  const attributeTable = (rows) =>
    "<thead><tr><th>Attribute</th><th>Content</th></tr></thead><tbody>" +
    rows.map(([name, text]) => `<tr><td><code>${name}</code></td><td>${text}</td></tr>`).join("") +
    "</tbody>";
  const list = (items) => items.map((text) => `<li>${text}</li>`).join("");

  document.getElementById("alarm-attributes").innerHTML = attributeTable([
    ["event_type", "The event type, for example <code>low_alert</code>."],
    ...alarmAttributes,
  ]);

  document.getElementById("toc").innerHTML = alarms
    .map((alarm) => `<li><a href="#${alarm.key}">${alarm.name}</a></li>`)
    .join("");

  document.getElementById("alarm-sections").innerHTML = alarms
    .map((alarm) => {
      const types = eventTypes(alarm)
        .map(
          ([type, label, requirements]) => `
            <h4>${label[0].toUpperCase()}${label.slice(1)} <code>${type}</code></h4>
            <ul class="requirements">${list(requirements)}</ul>`,
        )
        .join("");
      const extra = alarm.attributes
        ? `<h4>Additional values</h4><div class="table-wrap"><table>${attributeTable(alarm.attributes)}</table></div>`
        : "";
      return `
        <section class="card" id="${alarm.key}">
          <h3>${alarm.name}</h3>
          <p>Entity <code>event.&lt;person&gt;_${alarm.entity}</code> (English entity IDs).</p>
          ${types}
          ${extra}
        </section>`;
    })
    .join("");

  document.getElementById("report-requirements").innerHTML = list(report.report);
  document.getElementById("report-attributes").innerHTML = attributeTable([
    ["event_type", "<code>report</code>"],
    ...report.attributes,
  ]);

  // Jump to an anchor once the sections exist.
  if (location.hash) document.querySelector(location.hash)?.scrollIntoView();
})();
