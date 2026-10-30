# Setting up the profile card

GitHub shows the README of a repo named exactly like your username on your profile page.

1. **Create the repo.** On GitHub: New repository → name it exactly your username
   (`rezamirjaliliphd/rezamirjaliliphd`) → Public → create (no template files needed).

2. **Upload these files** (keep the folder structure, including `.github/workflows/`):
   ```
   README.md  SETUP.md  generate.py  make_ascii.py  ascii.txt
   dark_mode.svg  light_mode.svg  cache/.gitkeep
   .github/workflows/update-card.yml
   ```
   Easiest: `git clone` the new repo, copy everything in, `git add -A && git commit -m init && git push`.
   (The GitHub web uploader skips hidden folders like `.github`, so use git or create the workflow file by hand.)

3. **Create a token** so the Action can read your stats:
   GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token.
   Scopes: `repo` (to count private repos/commits) and `read:user`. Set an expiration you're happy with.

4. **Add it as a secret** in the profile repo: Settings → Secrets and variables → Actions →
   New repository secret → Name `ACCESS_TOKEN`, value = the token.

5. **Run it once:** Actions tab → "Update profile card" → Run workflow.
   It then refreshes every day and on every push. The first run walks your whole commit
   history for the lines-of-code count, so it may take a few minutes; later runs use `cache/`.

## Customizing

- **Text on the card:** edit the `INFO` list near the top of `generate.py`, push, done.
  Remove the `("Uptime", "{uptime}")` line (or set `BIRTHDAY = None`) if you don't want your age shown.
- **Portrait:** `ascii.txt` was made from your photo with the background cut out. To redo it with
  another photo: `pip install pillow numpy`, then
  `python make_ascii.py photo.png --crop LEFT,TOP,RIGHT,BOTTOM --gamma 1.1` → overwrites `ascii.txt`.
  A PNG with a transparent background gives the cleanest result; crop to head and shoulders.
  The portrait uses a 10px font (`ART_FONT_SIZE` in `generate.py`) so ~64×40 characters fit.
- **Colors:** `THEMES` in `generate.py` (GitHub's own palette by default).
- **Preview locally:** `python generate.py --offline` rebuilds the SVGs without calling GitHub;
  open them in a browser.
