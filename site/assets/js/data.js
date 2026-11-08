// Catalogue of the event entities, event types, requirements and attributes,
// in the language of the page. Used by the automation builder and the
// documentation page.
//
// Texts: window.BGM_TEXT (site/_data/i18n/<lang>.json, "js") and the names
// Home Assistant shows: window.BGM_HA (site/_data/ha/<lang>.json, generated
// from the integration's translations). The layout embeds both.
"use strict";

window.BGM = (() => {
  const T = window.BGM_TEXT;
  const HA = window.BGM_HA;
  const R = T.req;

  const fill = (text, values) =>
    text.replace(/\{(\w+)\}/g, (match, key) => values[key] ?? match);
  const menu = (key) => `<b>${T.configure} → ${HA.menu[key]}</b>`;
  const req = (key, menuKey, urgentKey) =>
    fill(R[key], {
      menu: menuKey ? menu(menuKey) : "",
      pause: HA.pause,
      urgent: urgentKey ? `<i>${HA.names[urgentKey]}</i>` : "",
    });

  const glucoseCommon = [req("reading_time"), req("fresh")];
  const common = (key, pausable = true) => [
    req("home", key),
    req("not_acknowledged"),
    req(pausable ? "pause_off" : "pause_never"),
    req("repeats"),
  ];

  const attributes = (keys, texts) => keys.map((key) => [key, texts[key]]);
  const alarmAttributes = attributes(
    [
      "title",
      "message",
      "alarm",
      "phase",
      "glucose",
      "unit",
      "delta",
      "rate",
      "trend",
      "trend_arrow",
      "data_age_min",
      "person_name",
      "entry_id",
      "tag",
      "icon",
      "ack_action",
    ],
    T.attributes,
  );

  const alarm = (key, alert, ended, extra = {}) => ({
    key,
    name: HA.names[key],
    alert,
    ended: [req("acknowledged"), ...ended],
    ...extra,
  });

  // urgent: the urgent alarm that supersedes this one (low → urgent low).
  const threshold = (key, below, pausable = true, urgent = null) =>
    alarm(
      key,
      [
        req("threshold_set", key),
        req(below ? "below_for_delay" : "above_for_delay"),
        ...glucoseCommon,
        ...common(key, pausable),
        ...(urgent ? [req("not_superseded", null, urgent)] : []),
      ],
      [
        ...(urgent ? [req("urgent_acknowledged", null, urgent)] : []),
        req(below ? "back_above" : "back_below"),
      ],
    );

  const rate = (key, prefix) =>
    alarm(
      key,
      [
        req("detection_set", key),
        req(`${prefix}_trend`),
        req(`${prefix}_rate`),
        req(`${prefix}_delay`),
        ...glucoseCommon,
        ...common(key),
      ],
      [req(`${prefix}_over`)],
    );

  const change = (key) =>
    alarm(
      key,
      [
        req("change_duration", key),
        req("change_last"),
        req("change_due"),
        ...common(key),
      ],
      [req("change_next")],
      {
        change: true,
        soon: [req("soon_set", key), req("soon_once"), req("soon_away")],
        attributes: attributes(["last_change", "due"], T.attributes),
      },
    );

  const alarms = [
    threshold("urgent_low", true, false),
    threshold("low", true, true, "urgent_low"),
    threshold("high", false, true, "urgent_high"),
    threshold("urgent_high", false),
    rate("rapid_fall", "fall"),
    rate("rapid_rise", "rise"),
    alarm(
      "data_loss",
      [
        req("always_active"),
        req("no_reading"),
        req("reading_time_short"),
        ...common("data_loss"),
      ],
      [req("new_reading")],
    ),
    alarm(
      "charging",
      [
        req("charging_set", "charging"),
        req("charging_time"),
        req("charging_state"),
        ...common("charging"),
      ],
      [req("charging_over")],
      { attributes: attributes(["battery"], T.attributes) },
    ),
    change("cannula_change"),
    change("sensor_change"),
    change("reservoir_change"),
  ];

  const report = {
    key: "report",
    name: HA.names.report,
    report: [
      req("report_entity", "report"),
      req("report_end"),
      req("report_home", "report"),
      req("report_stats"),
    ],
    attributes: Object.entries(T.report_attributes),
  };

  // Event types of an alarm: [type, label, requirements]. The label is the
  // name Home Assistant shows for the event type.
  const eventTypes = (item) => [
    [`${item.key}_alert`, HA.event_types[`${item.key}_alert`], item.alert],
    [`${item.key}_ended`, HA.event_types[`${item.key}_ended`], item.ended],
    ...(item.change
      ? [[`${item.key}_soon`, HA.event_types[`${item.key}_soon`], item.soon]]
      : []),
  ];

  // Entity ID as Home Assistant creates it from the device and entity name
  // (in the language of Home Assistant at setup).
  const slug = (text) =>
    text
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/ß/g, "ss")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  const entityId = (person, item) =>
    `event.${slug(person) || "person"}_${slug(item.name)}`;

  return { T, HA, alarms, report, alarmAttributes, eventTypes, entityId, fill };
})();
