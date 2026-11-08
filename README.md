# Berichtsheft

Web-App zum Ausfüllen des wöchentlichen Ausbildungsnachweises (IHK-Vorlage).
Die Daten liegen im Google Drive des angemeldeten Nutzers (Ordner „Berichtsheft“),
die App erzeugt daraus ein Word-Dokument (eine Woche pro Seite).

- `index.html` – die gebaute App (wird von GitHub Pages ausgeliefert)
- `config.js` – Google-Client-ID (öffentlich, kein Geheimnis)
- `src/` – Quellcode: `app_src.html` (Oberfläche), `docxgen.js` (Word-Erzeugung),
  `drive.js` (Speicher in Google Drive), `template.json` (Word-Vorlage ohne persönliche Daten)
- `tools/` – Hilfsskripte (Vorlage bauen, bestehendes .docx in eine Sicherung umwandeln)

Bauen: `python3 src/build.py src/template.json /tmp/preview.html index.html`
