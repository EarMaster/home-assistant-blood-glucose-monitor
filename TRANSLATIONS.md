# Translations

Blood Glucose Monitor is translated in two places:

| What | Files | Source |
| --- | --- | --- |
| Integration (setup, options, entities, notifications, actions) | `custom_components/blood_glucose_monitor/translations/<language>.json` | `en.json` |
| Documentation site | `site/_data/i18n/<language>.json` | `en.json` |

English is the source; every other file has exactly the same keys, the same
placeholders (`{name}`, `%builder%`, …), HTML tags and backticked code.
`tests/test_translations.py` and `tests/test_site.py` check this.
`python scripts/i18n_diff.py [revision]` lists what the other languages have
to follow. After changing an integration translation run
`python scripts/site_i18n.py`: the site takes the names Home Assistant shows
from there (`site/_data/ha/`).

A new language needs both files, `python scripts/site_pages.py <language>`,
an entry in `site/_data/languages.json` and in `DOCS_LANGUAGES` (`const.py`),
and then `python scripts/site_i18n.py`.

## Rules

- Medical terms follow the established terms of the language: Dexcom and
  FreeStyle Libre, Nightscout (`translations/` of cgm-remote-monitor) and
  AndroidAPS. Never translate literally where users know another term.
- The notice "not a medical device / does not replace the alarms of your CGM,
  insulin pump or medical app" keeps its full strength in every language.
- Home Assistant's own words and form of address of the language (look them
  up in Home Assistant's core translations).
- "Data loss" means missing data from any cause (uploader, network, Home
  Assistant), not the sensor's signal loss.
- Entity names in sentence case; short labels stay short.

## Glossary

| English | Deutsch | Français | Español | Nederlands |
| --- | --- | --- | --- | --- |
| Form of address | du | vous | tú | je |
| not a medical device | kein Medizinprodukt | pas un dispositif médical | no es un producto sanitario | geen medisch hulpmiddel |
| CGM | CGM | MCG | MCG | CGM |
| glucose | Glukose | glucose | glucosa | glucose |
| reading / reading time | Messwert / Messzeitpunkt | mesure / heure de mesure | lectura / hora de la lectura | meting / meettijdstip |
| Urgent low alarm | Alarm dringend niedrig | Alarme d'urgence glucose bas | Alarma de glucosa baja urgente | Alarm urgent laag |
| Low alarm | Alarm niedrig | Alarme de glucose bas | Alarma de glucosa baja | Alarm laag |
| Low (episode, report count) | Unterzucker | hypoglycémie | hipoglucemia | hypoglykemie (plural hypoglykemieën) |
| High alarm | Alarm hoch | Alarme de glucose élevé | Alarma de glucosa alta | Alarm hoog |
| Urgent high alarm | Alarm dringend hoch | Alarme d'urgence glucose élevé | Alarma de glucosa alta urgente | Alarm urgent hoog |
| Falling fast / Rising fast | schnell fallend / schnell steigend | Chute rapide / Hausse rapide | Bajada rápida / Subida rápida | Snel dalend / Snel stijgend |
| Data loss | Datenausfall | Absence de données | Falta de datos | Geen metingen |
| time in range / below / above | Zeit im Zielbereich / darunter / darüber | temps dans la cible / sous / au-dessus de la cible | tiempo en rango / por debajo / por encima del rango | tijd binnen / onder / boven bereik |
| target range | Zielbereich | cible / plage cible | rango objetivo | streefbereik |
| threshold | Schwellwert | seuil | umbral | drempelwaarde |
| Cannula change (infusion set, site change, pod) | Kanülenwechsel (Katheter-/Infusionssetwechsel, Pod) | changement de canule (cathéter, set de perfusion, pod) | cambio de cánula (set de infusión, cambio de catéter, pod) | canulewissel (infusieset, inbrengplaats, pod) |
| Sensor change | Sensorwechsel | changement de capteur | cambio de sensor | sensorwissel |
| Reservoir change (cartridge) | Reservoirwechsel (Ampulle, Patrone, Kartusche) | changement de réservoir (cartouche) | cambio de reservorio (cartucho) | reservoirwissel (cartridge, ampul) |
| Charging reminder | Lade-Erinnerung | Rappel de charge | Recordatorio de carga | Oplaadherinnering |
| Snooze | Schlummern | Mise en sourdine | Silenciar | Sluimeren |
| Acknowledge | Bestätigen | Acquitter | Confirmar | Bevestigen |
| Pause | Pause | Pause | Pausa | Pauze |
| Report | Bericht | Rapport | Informe | Rapport |
| Cooldown (report: restart counts as the same episode) | Karenzzeit | Délai de grâce | Periodo de gracia | Wachttijd |
| Event received (trigger) | Ereignis empfangen | Un événement a été reçu | Evento recibido | Gebeurtenis ontvangen |
| automation builder | Automation-Builder | générateur d'automatisations | generador de automatizaciones | automatiseringsbouwer |
| Visit (device page link) | Besuchen | Visiter | Visitar | Bezoeken |
| GMI (glucose management indicator) | GMI | GMI | GMI | GMI |
| Estimated HbA1c | Geschätzter HbA1c | HbA1c estimée | HbA1c estimada | Geschatte HbA1c |
| Mean glucose | Mittlere Glukose | Glucose moyenne | Glucosa media | Gemiddelde glucose |
| not a laboratory HbA1c | kein im Labor bestimmter HbA1c | pas une HbA1c de laboratoire | no una HbA1c de laboratorio | geen HbA1c uit het laboratorium |
| long-term statistics / state class | Langzeitstatistiken / Zustandsklasse | statistiques à long terme / classe d'état | estadísticas a largo plazo / clase de estado | langetermijnstatistieken / statusklasse |
