// Automation builder: one automation with the trigger "Event received" for
// the selected event types, a notification with the ready-made texts of the
// integration and clear_notification for the "ended" events.
"use strict";

(() => {
  const { T, HA, alarms, report, eventTypes, entityId } = window.BGM;
  const params = new URLSearchParams(location.search);
  const prefilled = [...alarms.map((a) => a.key), report.key].some((key) =>
    params.has(key),
  );
  const soon = new Set((params.get("soon") || "").split(",").filter(Boolean));

  const form = document.getElementById("form");
  const nameInput = document.getElementById("name");
  const notifyInput = document.getElementById("notify");
  const ackInput = document.getElementById("ack");
  const eventsBox = document.getElementById("events");
  const yamlBox = document.getElementById("yaml");
  const requirementsBox = document.getElementById("requirements");

  document.getElementById(prefilled ? "prefill-note" : "manual-note").hidden = false;
  nameInput.value = params.get("name") || "";

  // Entities shown: with a link from Home Assistant only the configured ones.
  const groups = [
    ...alarms.map((alarm) => ({
      source: alarm,
      types: eventTypes(alarm).filter(
        ([type]) => !prefilled || !type.endsWith("_soon") || soon.has(alarm.key),
      ),
    })),
    {
      source: report,
      types: [["report", HA.event_types.report, report.report]],
    },
  ].filter(({ source }) => !prefilled || params.has(source.key));

  const guessEntity = (source) => entityId(nameInput.value, source);
  // Build the inputs.
  for (const group of groups) {
    const { source, types } = group;
    const fieldset = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = source.name;
    fieldset.append(legend);
    group.checks = types.map(([type, label]) => {
      const row = document.createElement("label");
      row.className = "check";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = type;
      row.append(box, ` ${label} `);
      const code = document.createElement("code");
      code.textContent = type;
      row.append(code);
      fieldset.append(row);
      return box;
    });
    const entityRow = document.createElement("div");
    entityRow.className = "field entity-row";
    const id = `entity-${source.key}`;
    const label = document.createElement("label");
    label.htmlFor = id;
    label.textContent = T.event_entity;
    const input = document.createElement("input");
    input.type = "text";
    input.id = id;
    input.spellcheck = false;
    if (prefilled) {
      input.value = params.get(source.key);
    } else {
      input.dataset.guessed = "true";
      input.value = guessEntity(source);
      input.addEventListener("input", () => delete input.dataset.guessed);
    }
    group.entity = input;
    entityRow.append(label, input);
    fieldset.append(entityRow);
    eventsBox.append(fieldset);
  }

  // YAML helpers. Plain values are written as they are, everything else as a
  // double-quoted (JSON) string, which is valid YAML.
  const value = (text) =>
    /^[a-z0-9_.]+$/.test(text) ? text : JSON.stringify(text);
  const attr = (name) => `"{{ trigger.to_state.attributes.${name} }}"`;

  const notifyLines = (action, withAck) => [
    `- action: ${value(action)}`,
    "  data:",
    `    title: ${attr("title")}`,
    `    message: ${attr("message")}`,
    "    data:",
    `      tag: ${attr("tag")}`,
    ...(withAck
      ? [
          "      actions:",
          `        - action: ${attr("ack_action")}`,
          `          title: ${JSON.stringify(T.ack_title)}`,
        ]
      : []),
  ];

  const clearLines = (action) => [
    `- action: ${value(action)}`,
    "  data:",
    "    message: clear_notification",
    "    data:",
    `      tag: ${attr("tag")}`,
  ];

  const indent = (lines, spaces) => lines.map((line) => " ".repeat(spaces) + line);

  const endsWith = (suffix) =>
    `"{{ trigger.to_state.attributes.event_type.endswith('${suffix}') }}"`;

  function build() {
    const selected = groups.flatMap((group) =>
      group.checks
        .filter((box) => box.checked)
        .map((box) => ({ group, type: box.value })),
    );
    if (!prefilled) {
      for (const group of groups) {
        if (group.entity.dataset.guessed) group.entity.value = guessEntity(group.source);
      }
    }
    renderRequirements(selected);
    if (!selected.length) {
      yamlBox.textContent = `# ${T.select_event}`;
      return;
    }

    const actions = notifyInput.value
      .split(",")
      .map((text) => text.trim())
      .filter(Boolean);
    if (!actions.length) actions.push("notify.mobile_app_your_phone");
    const ack = ackInput.checked;
    const types = selected.map(({ type }) => type);
    const entities = [
      ...new Set(selected.map(({ group }) => group.entity.value.trim())),
    ];

    const hasEnded = types.some((type) => type.endsWith("_ended"));
    const hasAckAlert = ack && types.some((type) => type.endsWith("_alert"));
    const hasPlain = types.some(
      (type) => !type.endsWith("_ended") && !(hasAckAlert && type.endsWith("_alert")),
    );

    const branches = [];
    if (hasEnded) {
      branches.push({ suffix: "_ended", lines: actions.flatMap(clearLines) });
    }
    if (hasAckAlert) {
      branches.push({
        suffix: "_alert",
        lines: actions.flatMap((action) => notifyLines(action, true)),
      });
    }
    const plain = hasPlain ? actions.flatMap((action) => notifyLines(action, false)) : [];

    let actionLines;
    if (branches.length === 1 && !hasPlain) {
      actionLines = branches[0].lines;
    } else if (!branches.length) {
      actionLines = plain;
    } else {
      actionLines = [
        "- choose:",
        ...branches.flatMap(({ suffix, lines }) => [
          "    - conditions:",
          "        - condition: template",
          `          value_template: ${endsWith(suffix)}`,
          "      sequence:",
          ...indent(lines, 8),
        ]),
        ...(hasPlain ? ["  default:", ...indent(plain, 4)] : []),
      ];
    }

    const name = nameInput.value.trim();
    const lines = [
      `alias: ${JSON.stringify(`${T.alias}${name ? `: ${name}` : ""}`)}`,
      `description: ${JSON.stringify(T.automation_description)}`,
      "mode: queued",
      "triggers:",
      "  - trigger: event.received",
      "    target:",
      "      entity_id:",
      ...entities.map((entity) => `        - ${value(entity)}`),
      "    options:",
      "      event_type:",
      ...types.map((type) => `        - ${type}`),
      "actions:",
      ...indent(actionLines, 2),
    ];
    yamlBox.textContent = lines.join("\n") + "\n";
  }

  function renderRequirements(selected) {
    requirementsBox.replaceChildren();
    if (!selected.length) {
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = T.select_event;
      requirementsBox.append(hint);
      return;
    }
    for (const group of groups) {
      const picked = selected.filter((item) => item.group === group);
      if (!picked.length) continue;
      const card = document.createElement("div");
      card.className = "card";
      const title = document.createElement("h3");
      title.textContent = group.source.name;
      card.append(title);
      for (const { type } of picked) {
        const [, , requirements] = group.types.find(([t]) => t === type);
        const head = document.createElement("p");
        const strong = document.createElement("strong");
        strong.textContent = T.labels[type === "report" ? "report" : type.split("_").pop()];
        const code = document.createElement("code");
        code.textContent = type;
        head.append(strong, " ", code);
        const list = document.createElement("ul");
        list.className = "requirements";
        // Static texts from data.js (trusted markup).
        list.innerHTML = requirements.map((text) => `<li>${text}</li>`).join("");
        card.append(head, list);
      }
      requirementsBox.append(card);
    }
  }

  document.getElementById("copy").addEventListener("click", async () => {
    const status = document.getElementById("copied");
    try {
      await navigator.clipboard.writeText(yamlBox.textContent);
      status.textContent = T.copied;
    } catch {
      getSelection().selectAllChildren(yamlBox);
      status.textContent = T.copy_fallback;
    }
    setTimeout(() => (status.textContent = ""), 2500);
  });

  form.addEventListener("input", build);
  form.addEventListener("submit", (event) => event.preventDefault());
  build();
})();
