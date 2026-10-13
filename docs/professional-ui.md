# Supplier Workspace: erste UI-Version

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
  Einstellungen. Fachliche Modelltexte und Teile dieser bestehenden Verwaltungsansichten
  bleiben in dieser ersten Version auf Englisch.

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
