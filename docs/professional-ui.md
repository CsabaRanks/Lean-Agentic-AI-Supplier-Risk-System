# Supplier Workspace: erste UI-Version

Der aktuelle englische Produkteinstieg steht in der [README](../README.md),
mit einem [englischen Demo-Durchlauf](demo-guide.md) und
[aktuellen Produktansichten](../README.md#see-it-in-action).
Die folgenden Prüfnotizen bewahren auch die früheren UI-Stände als Entwicklungsnachweis.

Die Oberfläche bleibt eine lokale Streamlit-Anwendung. Sie nutzt das offizielle Theme,
Container, Tabellen, Status-Badges, Formulare und aufklappbare Details. Es gibt kein
injiziertes CSS und keine Abhängigkeit von internen Streamlit-DOM-Strukturen im Produkt.

## Start

Aus dem Projektverzeichnis (Python 3.10 oder neuer):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
streamlit run ui/app.py
```

Windows PowerShell: `.venv\Scripts\Activate.ps1` statt `source ...`.
Danach `http://localhost:8501` öffnen und **Demo ausprobieren** wählen.
Die Demo enthält sechs synthetische Lieferanten. Bewertungen, Erklärungen und Korrekturen
benötigen keinen API-Key. Eine vorhandene LLM-Konfiguration löst keine automatische Anfrage aus.

## Seiten und Demo-Durchlauf

- **Start:** Einführung, Demo und Einstieg mit eigenen Daten.
- **Portfolio:** beide Bewertungen gemeinsam, Suche als wörtlicher Text (auch Sonderzeichen),
  Filter nach Warengruppe, Risiko, Performance und Prüfbedarf, Export. Die Sortierung
  berücksichtigt zuerst die endgültige Risikoklasse, dann den Score.
- **Lieferantendetail:** Risiko und Performance nebeneinander (auf schmalen Bildschirmen
  untereinander), Score-Richtung, Datenbasis, Eskalationshinweis und wichtigste Beiträge.
  Quellen, Regeln, vollständige Berechnung und Maßnahmen werden bei Bedarf aufgeklappt.
- **Maßnahmen:** bestehender Maßnahmenplan.
- **Verwaltung & Analyse:** Dashboard, Historie, Daten & Import, Kalibrierung, Freigaben und
  Einstellungen. Die Anwendungstexte einschließlich Modellkriterien und Maßnahmen sind
  über **DE | EN** in beiden Sprachen verfügbar.

1. **Demo ausprobieren**, im Portfolio nach `Delta` suchen.
2. Tabellenzeile auswählen oder **Lieferanten direkt öffnen → Bewertung öffnen** verwenden.
3. Unter **Warum diese Bewertung?** die Beiträge und die ausgelöste Compliance-Regel lesen.
4. Im Korrekturformular das Feld `compliance_status` auswählen, `minor_findings` eingeben
   und z. B. „Synthetische Demo: Ein erneutes Audit hat den kritischen Befund geschlossen“ begründen.
5. **Vorher/Nachher prüfen**: Risiko 41,75 → 35,75, Hoch → Mittel;
   Performance 38,75 → 40,62, C bleibt C. Die Compliance-Eskalation entfällt.
6. Erst **Korrektur bestätigen** übernimmt die Änderung und protokolliert sie.
   **Vorschau verwerfen** lässt die Bewertung unverändert.
7. **Korrekturhistorie** aufklappen; ins Portfolio zurückgehen und beide aktualisierten Werte prüfen.

Die KI-Erklärung ist ein optionaler Abschnitt **nach** dem Korrekturablauf. Der genaue Payload
bleibt vor dem expliziten API-Aufruf einsehbar. Veraltete Erklärungen bleiben gekennzeichnet.
Die bestehende Kalibrierung, Prüfung vorgeschlagener Gewichte, Freigabe und Protokollierung
werden weiterverwendet. Beim Neuberechnen bleiben bereits freigegebene Sitzungsgewichte erhalten,
auch ohne Dateispeicher. Eine Neubewertung kann erneut eine fachliche Freigabe erfordern.

## Ergebnisse der ersten Prüfung

Die alte Oberfläche hatte acht gleichrangige Tabs, ein globales Umschalten der Bewertung,
eine sehr breite Portfolio-Tabelle und eine weit unten liegende Erklärung. Die optionale
KI-Anfrage unterbrach den Weg von der Berechnung zur Korrektur. Ein klarer Demo-Einstieg fehlte.
Der ursprüngliche Browserdurchlauf umfasste SUP-004, Vorschau, Bestätigung und Historieneintrag.
Die Browserprüfungen schreiben ausschließlich synthetische Testhistorie in temporäre Ordner.

## Grenzen dieser Streamlit-Version

Die Tabelle scrollt auf kleinen Bildschirmen horizontal. Deshalb stehen Risiko und Performance
weit links; eine normale Auswahl mit Öffnen-Schaltfläche bietet einen alternativen Zugang zum
Detail. Mehrspaltige Bereiche brechen mit Streamlits nativer responsiver Darstellung um.
Es gibt keine individuellen, fest angehefteten Tabellenaktionen und keine eigenständigen URLs
für jede Lieferantenansicht. Dafür wäre eine spätere Abwägung eines eigenen Frontends sinnvoll;
für diese erste Version ist kein Technologiewechsel erforderlich.

Sitzungen bleiben wie bisher lokal und nicht dauerhaft gespeichert. Die Namen in Korrekturen
sind ungeprüfte Eingaben. Korrekturhistorie und freigegebene Gewichtsversionen verwenden weiterhin
die vorhandenen lokalen Dateispeicher. Produktionsdaten werden nicht in Screenshots oder Git übernommen.

## Prüfungen und Screenshots

```bash
pytest -q
ruff check src tests examples scripts ui
```

Die UI-Tests prüfen den neuen Einstieg, beide Bewertungsperspektiven, Navigation, Filter,
leere Ergebnisse, Korrektur mit Pflichtbegründung, Vorschau, Bestätigung, Verwerfen,
Historie, Kalibrierung und Freigabe sowie die optionale KI mit einem Testprovider.
Ein eigener Fall prüft den Erhalt freigegebener Gewichte nach einer Korrektur.

Screenshots liegen in [images/professional-ui](images/professional-ui/):

- [Einstieg](images/professional-ui/start-desktop.png)
- [Portfolio · Desktop](images/professional-ui/portfolio-desktop.png)
- [Lieferantendetail · Desktop](images/professional-ui/detail-desktop.png)
- [Korrekturvorschau](images/professional-ui/correction-preview.png)
- [Bestätigte Korrektur](images/professional-ui/detail-confirmed.png)
- [Portfolio · 390 px](images/professional-ui/portfolio-mobile.png)
- [Lieferantendetail · 390 px](images/professional-ui/detail-mobile.png)
- [Leeres Suchergebnis](images/professional-ui/empty-state.png)

Referenzen für die verwendeten öffentlichen APIs:
[Theme](https://docs.streamlit.io/develop/api-reference/configuration/config.toml),
[Tabellenauswahl](https://docs.streamlit.io/develop/api-reference/data/st.dataframe).

Prüfergebnis am 13.10.2026: **208 Tests bestanden** (187 fachliche Tests, 21 UI-Tests),
**1 Test übersprungen** (realer LLM-Aufruf ohne API-Key). Ruff und `git diff --check` bestanden.

Browserprüfung: Desktop **1440 × 1000**, schmaler Bildschirm **390 × 844**. Demo,
Suche einschließlich Sonderzeichen/Leerzustand, direkte Lieferantenauswahl, Erklärung,
Pflichtbegründung, Vorschau, Bestätigung, Historieneintrag und mobile Korrektur geprüft.
Risiko vor Bestätigung 41,75 / Hoch; nach Bestätigung 35,75 / Mittel. Die Testhistorie
liegt außerhalb des Projekts. Keine KI-Anfrage wurde ausgelöst.

Weitere mobile Ausschnitte: [beide Bewertungskarten](images/professional-ui/detail-mobile-scores.png)
und [Korrekturvorschau](images/professional-ui/correction-mobile.png).
Die Auswahl per Tabellenzeile und die Rücknavigation wurden ebenfalls im Browser geprüft.


## Sprache: DE | EN

Der Sprachschalter steht ganz oben in der Seitenleiste. Beim ersten Aufruf wird
`st.context.locale` ausgewertet: `de` (einschließlich `de-DE`, `de-AT` usw.) wählt
Deutsch, alle anderen oder nicht verfügbaren Browserangaben wählen Englisch. Die
Auswahl gilt für die aktuelle Streamlit-Sitzung. Auf schmalen Bildschirmen zuerst
die native Seitenleiste öffnen.

Der zentrale Katalog liegt in `ui/locales/messages.json`; `ui/i18n.py` enthält
Anzeigeformatierung und Übersetzungszugriff. Navigation und Auswahlfelder behalten
stabile interne Werte. Auswahl-Widgets erhalten zusätzlich einen Sprachsuffix am Schlüssel,
damit Streamlit auch den ausgewählten Beschriftungstext aktualisiert; die eigentliche
Auswahl liegt getrennt im Sitzungszustand. Korrektureingaben werden unmittelbar im Sitzungszustand
gehalten, statt erst beim Absenden eines Streamlit-Formulars. Eine offene Vorschau
wird beim Wechsel nur neu dargestellt. Weder Berechnung noch API-Aufruf werden ausgelöst.
Dynamische Eingabetabellen bewahren ihren zurückgegebenen Bearbeitungsstand beim Wechsel.

Zahlen in Ergebnistabellen, Karten und Vorschauen sowie Datumsangaben und Diagramme
folgen der ausgewählten Sprache. Die zugrunde liegenden numerischen Tabellenspalten
bleiben numerisch und sortierbar. Zeitstempel behalten ihre gespeicherte Zeitzone und
zeigen sie an. Im Korrekturfeld wird zusätzlich ein deutsches Dezimalkomma akzeptiert.
CSV-Exporte, interne IDs, Klassen-Codes, JSON-Vorschau, Rechenwerte und gespeicherte
Historie verwenden weiterhin ihr unverändertes Austauschformat.

Neue KI-Anfragen erhalten `language="de"` beziehungsweise `language="en"` als separate
Anweisung. Die Berechnungsspur und ihr Hash bleiben unverändert. Bereits erzeugte
Erklärungen werden in ihrer ursprünglichen Sprache gekennzeichnet und beibehalten;
Nutzerbegründungen, Kommentare und Namen werden nicht übersetzt. Für eine neue
Erklärung in der anderen Sprache die vorhandene Erklärung ausdrücklich verwerfen
und anschließend neu anfordern. Der Sprachwechsel selbst ist kostenlos und ruft
keinen Anbieter auf. Automatisierte Tests verwenden ausschließlich einen Testprovider.

### Grenzen nativer Streamlit-Elemente

Die von uns kontrollierten Beschriftungen und Auswahllisten sind übersetzt. Streamlit
1.65 bietet jedoch keinen anwendungsweiten Sprachparameter für seine eigenen Texte:

- Datei-Upload: „Drag and drop files here“, „Browse files“, Größen-/Typangaben.
- Tabellenwerkzeuge: Such-, Download-, Vollbild- und Kopiermenüs sowie native
  Leer-/Validierungsmeldungen des Zelleditors.
- Native Tastaturhinweise, etwa „Press Enter to apply“, und Bedienhilfen wie
  „Close sidebar“, „Open sidebar“ oder „Clear all“.
- Streamlit-Verbindungs-, Laufzeit- und Framework-Fehlerdialoge.

Diese Texte richten sich nach der Streamlit-Version beziehungsweise dem Browser und
können teilweise englisch bleiben. Native numerische **Eingabezellen** verwenden die
Formatierung/Validierung des Streamlit-Zelleditors; sie lassen sich nicht unabhängig
von der Browsersprache vollständig lokalisieren. Die Ergebnistabellen und die
Korrekturvorschau verwenden dagegen die ausgewählte Sprache. Wir ersetzen dafür weder
interne DOM-Strukturen noch Framework-Texte durch JavaScript oder CSS. Systemdialoge
zur Dateiauswahl werden vom Betriebssystem bereitgestellt.

Die zusätzliche Browserprüfung und Screenshots für DE/EN liegen unter
[images/professional-ui/i18n](images/professional-ui/i18n/).


Prüfergebnis der Sprachergänzung am 13.10.2026: **224 Tests bestanden, 1 übersprungen**
(realer LLM-Aufruf ohne API-Key). Nach der abschließenden Korrektur der Auswahl-Widgets
wurden die **23 UI-Tests erneut erfolgreich** ausgeführt; die **11 Lokalisierungstests**
bestehen ebenfalls. Ruff und `git diff --check` bestanden.

Zusätzliche Prüffälle: Browser-Sprachwahl einschließlich unbekannter Sprache,
Darstellung ohne Änderung der Rohwerte, Erhalt von Suche/Filtern/Lieferant/Ausfüllstand/
Korrekturvorschau beim Wechsel, unveränderte Nutzerbegründung, kein erneuter KI-Aufruf,
deutscher/englischer Prompt bei einer ausdrücklich angeforderten neuen Erklärung.


Browserprüfung: **1440 × 1000** und **390 × 844**, Deutsch und Englisch.
`de-DE` wurde automatisch erkannt; der englische Browser startete auf Englisch.
Suche und Lieferantenauswahl blieben beim Wechsel erhalten. Die offene Korrektur von
`compliance_status` wurde zwischen beiden Sprachen umgeschaltet, einschließlich der
Beschriftung des ausgewählten Felds und der unveränderten deutschen Nutzerbegründung.
Die mobile Bestätigung schrieb unverändert 41,75 → 35,75 in die synthetische Testhistorie
unter `/tmp/sra-i18n-browser-history`; es gab keinen API-Aufruf und keinen horizontalen
Seitenüberlauf. Zahlen in der JSON-Historie bleiben 41.75 beziehungsweise 35.75.

Aktuelle Screenshots:

- Einstieg: [DE](images/professional-ui/i18n/start-de.png), [EN](images/professional-ui/i18n/start-en.png)
- Portfolio: [DE](images/professional-ui/i18n/portfolio-de.png), [EN](images/professional-ui/i18n/portfolio-en.png)
- Lieferantendetail: [DE](images/professional-ui/i18n/detail-de.png), [EN](images/professional-ui/i18n/detail-en.png)
- Offene Korrektur: [DE](images/professional-ui/i18n/correction-preview-de.png), [EN](images/professional-ui/i18n/correction-preview-en.png)
- Mobile Korrektur: [DE](images/professional-ui/i18n/correction-mobile-de.png), [EN](images/professional-ui/i18n/correction-mobile-en.png)
- [Mobiler Sprachschalter](images/professional-ui/i18n/language-mobile-de.png)
- [Bestätigte Korrektur](images/professional-ui/i18n/detail-confirmed-de.png)
