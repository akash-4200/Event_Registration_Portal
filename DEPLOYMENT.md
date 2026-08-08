# Deploying to Render

This project is now configured for Render. Two changes were needed beyond
just "add a Procfile": the database and uploaded files (posters, QR codes,
certificates) needed to move onto a **persistent disk** (Render wipes the
regular filesystem on every deploy/restart), and uploads are now served
through a dedicated `/uploads/<path>` route instead of Flask's `static/`
folder, so their storage location isn't tied to the app's own code folder.
See `config.py` (`DATA_DIR`) and `app.py` (`serve_upload`) if you want the
details.

You have two ways to deploy: the one-click Blueprint (uses `render.yaml`,
recommended) or manual setup. Both end up identical.

## Option A -- Blueprint deploy (recommended, ~3 clicks)

1. Push this project to a GitHub repository (see "Pushing to GitHub"
   below if you haven't done this yet).
2. Go to [render.com](https://render.com) and sign up / log in (free,
   GitHub login works).
3. Click **New +** → **Blueprint**.
4. Connect your GitHub account if you haven't, then select this
   repository. Render will detect `render.yaml` automatically and show
   you a preview of what it's about to create (a web service + a 1GB
   persistent disk).
5. Click **Apply**. Render builds and deploys automatically — this takes
   a few minutes the first time.
6. Once it's live, open the **Shell** tab for your service (in the Render
   dashboard) and run:
   ```bash
   python seed.py
   ```
   This creates the database tables and demo accounts on the persistent
   disk. You only need to do this once — the data survives future deploys.

Your app is now live at `https://event-registration-portal-XXXX.onrender.com`
(Render assigns the exact subdomain).

## Option B -- Manual setup

If you'd rather configure it by hand (or want to understand what the
Blueprint is doing for you):

1. Push the project to GitHub.
2. On Render: **New +** → **Web Service** → connect your repo.
3. Fill in:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --workers 2 --threads 4 --timeout 60`
   - **Instance Type:** Free
4. Under **Environment**, add these variables:
   | Key | Value |
   |---|---|
   | `SECRET_KEY` | click "Generate" for a random secure value |
   | `DATA_DIR` | `/var/data` |
   | `FLASK_DEBUG` | `false` |
5. Under **Disks**, add a disk:
   - **Name:** `event-portal-data`
   - **Mount Path:** `/var/data`
   - **Size:** 1 GB (free tier minimum, plenty for this project)
6. Click **Create Web Service**. Once deployed, open the **Shell** tab and
   run `python seed.py` (same as step 6 above).

## Pushing to GitHub (if you haven't yet)

From inside the `event_portal` folder:
```bash
git init
git add .
git commit -m "Initial commit: event registration portal"
git branch -M main
git remote add origin https://github.com/yourusername/event-portal.git
git push -u origin main
```
The included `.gitignore` already excludes `instance/`, local `uploads/`
content, and virtual environments, so your repo stays clean.

## Verifying the deploy

Once live, check that:
- The landing page loads over `https://` (Render provides this automatically).
- You can log in with the seeded demo accounts (see `README.md` for the list).
- Registering for an event actually generates and displays a QR ticket
  (this confirms the persistent disk + `/uploads/` route are both working
  correctly — if the QR image is broken, double check the `DATA_DIR`
  environment variable matches your disk's mount path exactly).
- **Restart the service** from the Render dashboard once, then log back in
  — if your demo accounts and events are still there, persistence is
  working correctly. If everything's gone, the disk mount path and
  `DATA_DIR` don't match.

## Known limitations once deployed (same as running locally)

These aren't deployment bugs — they're documented gaps in the app itself
(see the main `README.md`'s "What's Simplified / Not Included" section):

- **No real email delivery.** Password reset links and admin-generated
  temporary passwords still show up as an on-screen flash message rather
  than being emailed. This works fine for demoing the feature but isn't
  what you'd want for real users — adding `Flask-Mail` with real SMTP
  credentials (as Render environment variables) is the natural next step.
- **No payment gateway.** Paid events track a price but there's no real
  checkout.
- **Free tier sleep.** Render's free web services spin down after 15
  minutes of inactivity and take ~30-50 seconds to wake back up on the
  next request. This is normal Render free-tier behavior, not a bug in
  this project — upgrading to a paid instance removes it.

## Moving beyond SQLite (optional, but worth knowing)

SQLite on a persistent disk works fine for a portfolio demo and even
light real use, but it only safely handles one writer at a time. If you
ever wanted this handling real concurrent traffic, the standard next
step is Render's free PostgreSQL instance, which would mean:
- Swapping `db.py`'s `sqlite3` calls for `psycopg2`/`psycopg`
- Adjusting `schema.sql`'s SQLite-specific syntax (e.g. `AUTOINCREMENT` →
  `SERIAL`, `datetime('now')` → `NOW()`)

This is a genuinely good thing to mention in an interview even if you
don't implement it: "I deployed it on SQLite with a persistent disk for
the demo, and the natural next step for production would be Postgres for
concurrent writes."
