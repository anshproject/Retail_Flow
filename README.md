# Smart Store — Capstone Integrated Project

This package contains the Smart Store application plus a **separate dataset layer**.

## Run
```powershell
cd "...\SmartStore_Integrated_FINAL"
python app.py
```
Open http://127.0.0.1:8000

Default login: `admin` / `admin123`

## Dataset integration
Put the actual CSV/JSON/XLSX dataset files inside:
`dataset/raw/`

The application exposes:
- `/api/v1/dataset/profile`
- `/api/v1/dataset/insights`

The operational SQLite database remains separate from the raw dataset.

**Important:** the supplied `Capstone-Dataset.zip` contained only a Google Drive folder link, not the actual dataset file. The link is preserved in `dataset/Source_Link.txt`. Therefore the integration code is ready and connected, but the real rows cannot be embedded until the actual dataset file is supplied/exported.
