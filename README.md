# Eco Farms Final

This is a Flask application for managing farmers, farms, supplies, daily updates, harvests, and payments.

## Setup

1. Install Python 3.11+.
2. Create and activate a virtual environment:
   - Windows PowerShell: `python -m venv venv` and `.
venv\Scripts\Activate.ps1`
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Run the app:
   - `python app.py`

## Notes

- The app uses SQLite by default.
- Add users on `/register` or use the default `admin/admin123` account.

## Uploading to GitHub

Once Git is installed, run:

```powershell
cd "D:\Documents\Eco Farms Final"
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

Replace `<your-username>` and `<repo-name>` with your GitHub account and repository name.
