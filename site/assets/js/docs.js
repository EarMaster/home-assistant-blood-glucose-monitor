// Renders the tables and requirement lists of the documentation from data.js
// (static, trusted texts) in the language of the page.
"use strict";

(() => {
  const { T, alarms, report, alarmAttributes, eventTypes, entityId } = window.BGM;

  const attributeTable = (rows) =>
    `<thead><tr><th>${T.attribute}</th><th>${T.content}</th></tr></thead><tbody>` +
    rows.map(([name, text]) => `<tr><td><code>${name}</code></td><td>${text}</td></tr>`).join("") +
    "</tbody>";
  const list = (items) => items.map((text) => `<li>${text}</li>`).join("");
  const label = (type) => T.labels[type.split("_").pop()];

  document.getElementById("alarm-attributes").innerHTML = attributeTable([
    ["event_type", T.event_type_value],
    ...alarmAttributes,
  ]);

  document.getElementById("toc").innerHTML = alarms
    .map((alarm) => `<li><a href="#${alarm.key}">${alarm.name}</a></li>`)
    .join("");

  document.getElementById("alarm-sections").innerHTML = alarms
    .map((alarm) => {
      const types = eventTypes(alarm)
        .map(
          ([type, , requirements]) => `
            <h4>${label(type)} <code>${type}</code></h4>
            <ul class="requirements">${list(requirements)}</ul>`,
        )
        .join("");
      const extra = alarm.attributes
        ? `<h4>${T.additional_values}</h4><div class="table-wrap"><table>${attributeTable(alarm.attributes)}</table></div>`
        : "";
      const entity = entityId("<person>", alarm).replace("event.person_", "event.&lt;person&gt;_");
      return `
        <section class="card" id="${alarm.key}">
          <h3>${alarm.name}</h3>
          <p>${T.entity_note.replace("{entity}", entity)}</p>
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
