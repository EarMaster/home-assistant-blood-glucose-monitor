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
  const channelInput = document.getElementById("channel");
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
  // The event data, as variable "event" (see the variables block below).
  const attr = (name) => `"{{ event.${name} }}"`;

  // Android notification channel: the field, else the name of the person
  // from the event (follows a renamed entry).
  const channel = () => {
    const text = channelInput?.value.trim();
    return text ? JSON.stringify(text) : attr("person_name");
  };

  // Alarm notifications (started or repeated) get high importance and,
  // if wanted, the acknowledge button.
  const notifyLines = (action, isAlarm, withAck) => [
    `- action: ${value(action)}`,
    "  data:",
    `    title: ${attr("title")}`,
    `    message: ${attr("message")}`,
    "    data:",
    `      tag: ${attr("tag")}`,
    `      notification_icon: ${attr("icon")}`,
    `      channel: ${channel()}`,
    ...(isAlarm ? ["      importance: high"] : []),
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

  // Kinds of events the actions choose by: "alert" (started or repeated),
  // "ended" (acknowledged or over: remove the notification), "notify"
  // (warnings and reports).
  const kindOf = (type) => {
    if (type.endsWith("_ended")) return "ended";
    if (type.endsWith("_alert")) return "alert";
    return "notify";
  };
  const KINDS = ["alert", "ended", "notify"];

  function build() {
    const selected = groups.flatMap((group) =>
      group.checks
        .filter((box) => box.checked)
        .map((box) => ({ group, type: box.value })),
    );
    if (channelInput) channelInput.placeholder = nameInput.value.trim() || "Alex";
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

    // One notify action: a phone, a notify group for several phones, or
    // notify.notify (all phones with the Companion app).
    const action = notifyInput.value.trim() || "notify.notify";
    const ack = ackInput.checked;
    const kinds = KINDS.map((id) => {
      const items = selected.filter(({ type }) => kindOf(type) === id);
      const lines =
        id === "ended"
          ? clearLines(action)
          : notifyLines(action, id === "alert", ack && id === "alert");
      return { id, items, lines };
    }).filter(({ items }) => items.length);

    // One trigger per selected event: ID = event type, alias = the name
    // Home Assistant shows for it. Each can be moved to its own automation.
    const triggerLines = kinds.flatMap(({ items }) =>
      items.flatMap(({ group, type }) => [
        "  - trigger: event.received",
        `    alias: ${JSON.stringify(HA.event_types[type] || type)}`,
        `    id: ${type}`,
        "    target:",
        `      entity_id: ${value(group.entity.value.trim())}`,
        "    options:",
        "      event_type:",
        `        - ${type}`,
      ]),
    );

    const actionLines =
      kinds.length === 1
        ? kinds[0].lines
        : [
            "- choose:",
            ...kinds.flatMap(({ items, lines }) => [
              "    - conditions:",
              "        - condition: trigger",
              "          id:",
              ...items.map(({ type }) => `            - ${type}`),
              "      sequence:",
              ...indent(lines, 8),
            ]),
          ];

    const name = nameInput.value.trim();
    const lines = [
      `alias: ${JSON.stringify(`${T.alias}${name ? `: ${name}` : ""}`)}`,
      `description: ${JSON.stringify(T.automation_description)}`,
      "mode: queued",
      "triggers:",
      ...triggerLines,
      "variables:",
      '  event: "{{ trigger.to_state.attributes }}"',
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
