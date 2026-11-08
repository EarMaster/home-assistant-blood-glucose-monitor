// Catalogue of the event entities, event types, requirements and attributes.
// Used by the automation builder and the documentation page.
"use strict";

window.BGM = (() => {
  const menu = (item) => `<b>Configure → ${item}</b>`;

  const glucoseCommon = [
    "The glucose data has a reading time (a reading time sensor or the <code>date</code> attribute of the glucose sensor). Without it there are no glucose alarms and a repair issue tells you so.",
    "The latest reading is not older than the maximum data age of the data loss alarm; stale data neither starts nor ends a glucose alarm.",
  ];
  const common = (alarm, pausable = true) => [
    `With <i>Only when the person is at home</i> in ${menu(alarm)}: the person is at home when the alarm would start. A running alarm continues when the person leaves.`,
    "The alarm is not acknowledged: after an acknowledgement it stays silent for the snooze time and is then checked again.",
    ...(pausable
      ? ["The switch <i>Pause alarms</i> is off."]
      : ["The pause does not apply to this alarm."]),
    "Repeats: the event fires again in the repeat interval while the alarm is active (repeat interval 0 = only once).",
  ];
  const ended = [
    "The alarm is acknowledged: the <i>Acknowledge …</i> button, the action <code>blood_glucose_monitor.acknowledge</code> or the notification action <code>ack_action</code>.",
  ];

  const alarmAttributes = [
    ["title", "Ready-made title in the language of Home Assistant, for example <i>Alex: low glucose</i>."],
    ["message", "Ready-made message: glucose with unit and trend arrow for the glucose alarms, a matching text for data loss and the reminders; on acknowledge or end a short text."],
    ["alarm", "Key of the alarm, for example <code>low</code>."],
    ["phase", "<code>triggered</code>, <code>repeat</code>, <code>acknowledged</code>, <code>resolved</code> or <code>soon</code> (warning of a change reminder)."],
    ["glucose", "Latest glucose value in the unit of the glucose sensor."],
    ["unit", "<code>mg/dL</code> or <code>mmol/L</code>."],
    ["delta", "Change since the previous reading."],
    ["rate", "Own rate of change per minute."],
    ["trend", "Trend key, for example <code>falling_quickly</code>."],
    ["trend_arrow", "Trend as arrow, for example <code>↘</code>."],
    ["data_age_min", "Age of the latest reading in minutes."],
    ["person_name", "Name of the entry (the person)."],
    ["entry_id", "ID of the config entry, for the actions of the integration."],
    ["tag", "Notification tag, unique per person and alarm. Use it to replace and clear the notification."],
    ["ack_action", "Mobile app notification action that acknowledges this alarm."],
  ];

  const alarms = [
    {
      key: "urgent_low",
      name: "Urgent low alarm",
      entity: "urgent_low_alarm",
      alert: [
        `A threshold entity is selected in ${menu("Urgent low alarm")}.`,
        "The glucose stays below the threshold for the delay.",
        ...glucoseCommon,
        ...common("Urgent low alarm", false),
      ],
      ended: [
        ...ended,
        "The glucose reaches the threshold plus the clear offset.",
      ],
    },
    {
      key: "low",
      name: "Low alarm",
      entity: "low_alarm",
      alert: [
        `A threshold entity is selected in ${menu("Low alarm")}.`,
        "The glucose stays below the threshold for the delay.",
        ...glucoseCommon,
        ...common("Low alarm"),
      ],
      ended: [
        ...ended,
        "The glucose reaches the threshold plus the clear offset.",
      ],
    },
    {
      key: "high",
      name: "High alarm",
      entity: "high_alarm",
      alert: [
        `A threshold entity is selected in ${menu("High alarm")}.`,
        "The glucose stays above the threshold for the delay.",
        ...glucoseCommon,
        ...common("High alarm"),
      ],
      ended: [
        ...ended,
        "The glucose falls to the threshold minus the clear offset.",
      ],
    },
    {
      key: "urgent_high",
      name: "Urgent high alarm",
      entity: "urgent_high_alarm",
      alert: [
        `A threshold entity is selected in ${menu("Urgent high alarm")}.`,
        "The glucose stays above the threshold for the delay.",
        ...glucoseCommon,
        ...common("Urgent high alarm"),
      ],
      ended: [
        ...ended,
        "The glucose falls to the threshold minus the clear offset.",
      ],
    },
    {
      key: "rapid_fall",
      name: "Falling fast alarm",
      entity: "falling_fast_alarm",
      alert: [
        `A detection is selected in ${menu("Falling fast alarm")}: <i>trend</i> or <i>own rate of change</i>.`,
        "Trend: the trend of the glucose data (trend sensor or <code>direction</code> attribute) falls quickly (or only very quickly, as set).",
        "Own rate: two readings at most 15 minutes apart fall faster than the rate limit per minute.",
        "The fast fall lasts for the delay.",
        ...glucoseCommon,
        ...common("Falling fast alarm"),
      ],
      ended: [...ended, "The glucose no longer falls fast."],
    },
    {
      key: "rapid_rise",
      name: "Rising fast alarm",
      entity: "rising_fast_alarm",
      alert: [
        `A detection is selected in ${menu("Rising fast alarm")}: <i>trend</i> or <i>own rate of change</i>.`,
        "Trend: the trend of the glucose data (trend sensor or <code>direction</code> attribute) rises quickly (or only very quickly, as set).",
        "Own rate: two readings at most 15 minutes apart rise faster than the rate limit per minute.",
        "The fast rise lasts for the delay.",
        ...glucoseCommon,
        ...common("Rising fast alarm"),
      ],
      ended: [...ended, "The glucose no longer rises fast."],
    },
    {
      key: "data_loss",
      name: "Data loss alarm",
      entity: "data_loss_alarm",
      alert: [
        "Always active.",
        "No new reading arrives within the maximum data age.",
        "The glucose data has a reading time (a reading time sensor or the <code>date</code> attribute of the glucose sensor).",
        ...common("Data loss alarm"),
      ],
      ended: [...ended, "A new reading arrives."],
    },
    {
      key: "charging",
      name: "Charging reminder",
      entity: "charging_reminder",
      alert: [
        `A battery level and a charging state sensor are selected in ${menu("Charging reminder")}.`,
        "It is between the reminder time and midnight.",
        "The phone is not charging and the battery is at or below the limit.",
        ...common("Charging reminder"),
      ],
      ended: [
        ...ended,
        "The phone charges. After midnight a running reminder waits for charging; no new one starts before the next reminder time.",
      ],
      attributes: [["battery", "Battery level of the phone in percent."]],
    },
    ...[
      ["cannula_change", "Cannula change"],
      ["sensor_change", "Sensor change"],
      ["reservoir_change", "Reservoir change"],
    ].map(([key, item]) => ({
      key,
      name: `${item} reminder`,
      entity: `${key}_reminder`,
      change: true,
      alert: [
        `A wear duration (field or entity) is set in ${menu(item)}.`,
        "The last change is known: from the selected last change entity, or recorded with the <i>… changed</i> button or the action <code>blood_glucose_monitor.record_change</code>.",
        "The due time is reached: last change plus wear duration, or the fixed time on the due day.",
        ...common(item),
      ],
      ended: [
        ...ended,
        "The next change is recorded (button, action or a new time of the last change entity).",
      ],
      soon: [
        `A warning time (<i>Warning before</i>) is set in ${menu(item)}.`,
        "It fires once per due time, this long before the due time.",
        "While the person is away (with <i>Only when the person is at home</i>) or alarms are paused, it is sent as soon as possible before the due time.",
      ],
      attributes: [
        ["last_change", "Time of the last change (ISO 8601)."],
        ["due", "Due time (ISO 8601)."],
      ],
    })),
  ];

  const report = {
    key: "report",
    name: "Report",
    entity: "report",
    report: [
      `An entity with the periods (for example a schedule helper) is selected in ${menu("Reports")}.`,
      "A period ends: the entity turns off. A period that ends during a restart is reported afterwards.",
      `With <i>Only when the person is at home</i> in ${menu("Reports")}: the person is at home when the period ends. The <i>Last report</i> sensor is updated anyway.`,
      "Statistics need the recorder; the time in range needs a low (or urgent low) and a high (or urgent high) threshold.",
    ],
    attributes: [
      ["title", "Ready-made title, for example <i>Alex: report</i>."],
      ["message", "Ready-made summary of the period."],
      ["start", "Start of the period (ISO 8601)."],
      ["end", "End of the period (ISO 8601)."],
      ["duration_min", "Length of the period in minutes."],
      ["unit", "<code>mg/dL</code> or <code>mmol/L</code>."],
      ["glucose_min", "Lowest glucose value."],
      ["glucose_max", "Highest glucose value."],
      ["glucose_mean", "Mean glucose, weighted by time."],
      ["below", "Share of the time below range in percent (empty without both thresholds)."],
      ["in_range", "Share of the time in range in percent (empty without both thresholds)."],
      ["above", "Share of the time above range in percent (empty without both thresholds)."],
      ["coverage", "Share of the period with glucose data in percent."],
      ["alarms", "Number of alarms that started in the period, per alarm."],
      ["low_alarms", "Number of low and urgent low alarms in the period."],
      ["tag", "Notification tag, unique per person, so a new report replaces the last one."],
      ["person_name", "Name of the entry (the person)."],
      ["entry_id", "ID of the config entry."],
    ],
  };

  // Event types of an alarm: [type, label, requirements].
  const eventTypes = (alarm) => [
    [`${alarm.key}_alert`, "started or repeated", alarm.alert],
    [`${alarm.key}_ended`, "acknowledged or over", alarm.ended],
    ...(alarm.change ? [[`${alarm.key}_soon`, "due soon", alarm.soon]] : []),
  ];

  return { alarms, report, alarmAttributes, eventTypes };
})();
