"""
Builds the neofetch-style profile card (dark_mode.svg + light_mode.svg) and README.md.

Edit the PROFILE section below to change what the card says.
Live GitHub stats are fetched when ACCESS_TOKEN is set (the GitHub Action does this);
without a token the script reuses the numbers in cache/stats.json, or zeros.

    python generate.py            # build with live stats (needs ACCESS_TOKEN, USER_NAME)
    python generate.py --offline  # build from cached stats only
"""

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent

# ─────────────────────────── PROFILE: edit me ────────────────────────────
HANDLE = "reza@mirjalili"
BIRTHDAY = dt.date(1990, 9, 14)          # drives the "Uptime" line; set to None to hide it
# Portrait (see make_ascii.py)
ASCII_FILES = {"dark_mode": ROOT / "ascii_dark.txt"}   # optional; otherwise ascii.txt for both

# Each entry is (key, value). Use "" for a blank line, ("#", "Title") for a section bar.
INFO = [
    ("OS", "Linux, macOS, Windows"),
    ("Uptime", "{uptime}"),
    ("Host", "University of Houston"),
    ("Kernel", "Ph.D. Industrial & Systems Engineering"),
    ("Shell", "Operations Research / Optimization"),
    ("IDE", "VS Code, CLion"),
    "",
    ("Languages.Programming", "Python, C++17, Cython"),
    ("Languages.Computer", "LaTeX, SQL, Bash"),
    ("Languages.Real", "Persian, English, Arabic"),
    "",
    ("Solvers", "Gurobi, CPLEX"),
    ("Methods.Exact", "Branch-and-Price-and-Cut, Benders"),
    ("Methods.Pricing", "Column Generation, ESPPRC Labeling"),
    ("Research", "Mothership-Drone Routing (SVDRP, MDRP)"),
    ("#", "Contact"),
    ("Email", "reza.mirjalili@gmail.com"),
    ("Website", "rezamirjaliliphd.github.io"),
    ("LinkedIn", "in/rezamirjalili"),
    ("Scholar", "xKo0UD0AAAAJ"),
    ("ORCID", "0000-0002-5228-061X"),
    ("#", "GitHub Stats"),
    ("@stats", None),
]

WIDTH = 60                 # characters per info line
FONT_SIZE = 16
LINE_H = 20
CHAR_W = 9.6               # approx monospace advance at 16px (Consolas ≈ 8.8, DejaVu ≈ 9.6)
ART_FONT_SIZE = 10         # portrait uses a smaller font for more detail; set to 16 to match the text
ART_LINE_H = 12.5

THEMES = {
    "dark_mode": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                      add="#3fb950", dele="#f85149", cc="#616e7f"),
    "light_mode": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                       add="#1a7f37", dele="#cf222e", cc="#c2cfde"),
}
# ─────────────────────────────────────────────────────────────────────────


def uptime(born: dt.date, today: dt.date) -> str:
    y, m, d = today.year - born.year, today.month - born.month, today.day - born.day
    if d < 0:
        m -= 1
        prev_month_end = today.replace(day=1) - dt.timedelta(days=1)
        d += prev_month_end.day
    if m < 0:
        y -= 1
        m += 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{plural(y, 'year')}, {plural(m, 'month')}, {plural(d, 'day')}"


# ─────────────────────────── GitHub stats ────────────────────────────────
API = "https://api.github.com/graphql"


def gql(query: str, variables: dict, token: str) -> dict:
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def fetch_stats(user: str, token: str, cache: dict) -> dict:
    base = gql(
        """query($login:String!){ user(login:$login){ id createdAt followers{totalCount}
             contributed: repositories(ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER]){totalCount} } }""",
        {"login": user}, token)["user"]
    uid = base["id"]

    # owned repos + stars
    repos, stars, cursor = 0, 0, None
    while True:
        page = gql(
            """query($login:String!,$after:String){ user(login:$login){
                 repositories(first:100, after:$after, ownerAffiliations:OWNER){
                   totalCount pageInfo{hasNextPage endCursor} nodes{stargazerCount} } } }""",
            {"login": user, "after": cursor}, token)["user"]["repositories"]
        repos = page["totalCount"]
        stars += sum(n["stargazerCount"] for n in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # commits: sum contribution calendars year by year since account creation
    commits = 0
    start = dt.datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    t = start
    while t < now:
        t2 = min(t + dt.timedelta(days=365), now)
        cc = gql(
            """query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
                 contributionsCollection(from:$from,to:$to){ totalCommitContributions restrictedContributionsCount } } }""",
            {"login": user, "from": t.isoformat(), "to": t2.isoformat()}, token)["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        t = t2

    # lines of code: walk default-branch history of every repo you touch, authored by you.
    # Per-repo results are cached and only recomputed when the branch history changes.
    loc_cache = cache.setdefault("loc", {})
    cursor = None
    while True:
        page = gql(
            """query($login:String!,$after:String){ user(login:$login){
                 repositories(first:50, after:$after, ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER]){
                   pageInfo{hasNextPage endCursor}
                   nodes{ nameWithOwner defaultBranchRef{ target{ ... on Commit{ oid history{totalCount} } } } } } } }""",
            {"login": user, "after": cursor}, token)["user"]["repositories"]
        for node in page["nodes"]:
            ref = node["defaultBranchRef"]
            if not ref:
                continue
            name, head = node["nameWithOwner"], ref["target"]["oid"]
            if loc_cache.get(name, {}).get("head") == head:
                continue
            owner, repo = name.split("/")
            try:
                add, dele = repo_loc(owner, repo, uid, token)
            except Exception as exc:          # archived/inaccessible repo: skip, keep old value
                print(f"  skip {name}: {exc}")
                continue
            loc_cache[name] = {"head": head, "add": add, "del": dele}
            print(f"  loc  {name:45s} +{add:,} -{dele:,}")
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    add = sum(v["add"] for v in loc_cache.values())
    dele = sum(v["del"] for v in loc_cache.values())
    return dict(repos=repos, contributed=base["contributed"]["totalCount"], stars=stars,
                commits=commits, followers=base["followers"]["totalCount"],
                loc_add=add, loc_del=dele)


def repo_loc(owner: str, repo: str, uid: str, token: str) -> tuple[int, int]:
    add = dele = 0
    hcur = None
    while True:
        h = gql("""query($o:String!,$r:String!,$id:ID!,$after:String){ repository(owner:$o,name:$r){
                     defaultBranchRef{ target{ ... on Commit{
                       history(first:100, after:$after, author:{id:$id}){
                         pageInfo{hasNextPage endCursor} nodes{additions deletions} } } } } } }""",
                {"o": owner, "r": repo, "id": uid, "after": hcur}, token)
        hist = h["repository"]["defaultBranchRef"]["target"]["history"]
        add += sum(n["additions"] for n in hist["nodes"])
        dele += sum(n["deletions"] for n in hist["nodes"])
        if not hist["pageInfo"]["hasNextPage"]:
            break
        hcur = hist["pageInfo"]["endCursor"]
    return add, dele


# ─────────────────────────── SVG building ────────────────────────────────
def span(cls: str, text: str) -> str:
    return f'<tspan class="{cls}">{escape(text)}</tspan>'


def key_spans(key: str) -> str:
    # "Languages.Real" -> key "Languages" + cc "." + key "Real"
    parts = key.split(".")
    out = span("key", parts[0])
    for p in parts[1:]:
        out += span("cc", ".") + span("key", p)
    return out


def kv(key: str, value: str, width: int, value_cls: str = "value") -> tuple[str, int]:
    """'. Key: ....... value' padded so the value ends at `width` chars."""
    fixed = 2 + len(key) + 2 + 1 + len(value)          # ". " + key + ": " + " " + value
    dots = max(1, width - fixed)
    markup = span("cc", ". ") + key_spans(key) + ":" + span("cc", " " + "." * dots + " ") + span(value_cls, value)
    return markup, fixed + dots


def section(title: str) -> str:
    bar = "—" * max(3, WIDTH - len(title) - 3)
    return f"- {escape(title)} " + span("cc", bar)


def stats_lines(s: dict) -> list[str]:
    n = lambda x: f"{x:,}"
    left_w = 33                       # visible chars before " | "
    right_w = WIDTH - left_w - 3      # visible chars after it
    strip = lambda m: m.replace(span("cc", ". "), "", 1)
    sep = span("cc", " | ")

    contrib_w = 2 + len("Contributed: ") + len(n(s["contributed"])) + 1
    a, la = kv("Repos", n(s["repos"]), left_w - contrib_w)
    b = span("cc", " {") + span("key", "Contributed") + ": " + span("value", n(s["contributed"])) + span("cc", "}")
    used = la + contrib_w
    c, _ = kv("Stars", n(s["stars"]), right_w + 2)
    line1 = a + b + " " * max(0, left_w - used) + sep + strip(c)

    d, _ = kv("Commits", n(s["commits"]), left_w)
    e, _ = kv("Followers", n(s["followers"]), right_w + 2)
    line2 = d + sep + strip(e)

    total = n(s["loc_add"] - s["loc_del"])
    tail = f"( {n(s['loc_add'])}++, {n(s['loc_del'])}-- )"
    f, _ = kv("Lines of Code on GitHub", total, WIDTH - len(tail) - 1)
    line3 = (f + " " + span("cc", "( ") + span("add", n(s["loc_add"]) + "++") + span("cc", ", ")
             + span("del", n(s["loc_del"]) + "--") + span("cc", " )"))
    return [line1, line2, line3]


def build_svg(theme: dict, art: list[str], stats: dict, today: dt.date) -> str:
    info = [f'{escape(HANDLE)} ' + span("cc", "—" * (WIDTH - len(HANDLE) - 1))]
    for item in INFO:
        if item == "":
            info.append("")
        elif item[0] == "#":
            info.append("")
            info.append(section(item[1]))
        elif item[0] == "@stats":
            info.extend(stats_lines(stats))
        else:
            k, v = item
            if v == "{uptime}":
                if not BIRTHDAY:
                    continue
                v = uptime(BIRTHDAY, today)
            info.append(kv(k, v, WIDTH)[0])

    art_w = max((len(l) for l in art), default=0)
    art_cw = CHAR_W * ART_FONT_SIZE / FONT_SIZE
    info_x = 15 + art_w * art_cw + 30
    width = int(info_x + WIDTH * CHAR_W + 20)
    height = int(max(30 + len(info) * LINE_H, 30 + len(art) * ART_LINE_H)) + 10

    art_tspans = "\n".join(f'<tspan x="15" y="{22 + i * ART_LINE_H:g}">{escape(l)}</tspan>' for i, l in enumerate(art))
    info_tspans = "\n".join(f'<tspan x="{info_x:.0f}" y="{30 + i * LINE_H}">{l}</tspan>'
                            for i, l in enumerate(info) if l)

    t = theme
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" font-family="ConsolasFallback,Consolas,'DejaVu Sans Mono',monospace" width="{width}px" height="{height}px" font-size="{FONT_SIZE}px">
<style>
@font-face {{ src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; font-display: swap; -webkit-size-adjust: 109%; size-adjust: 109%; }}
.key {{fill: {t['key']};}}
.value {{fill: {t['value']};}}
.add {{fill: {t['add']};}}
.del {{fill: {t['dele']};}}
.cc {{fill: {t['cc']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{width}px" height="{height}px" fill="{t['bg']}" rx="15"/>
<text x="15" y="22" fill="{t['text']}" font-size="{ART_FONT_SIZE}px" class="ascii">
{art_tspans}
</text>
<text x="{info_x:.0f}" y="30" fill="{t['text']}">
{info_tspans}
</text>
</svg>
"""


README = """<a href="https://github.com/{user}">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{user}/{user}/main/dark_mode.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{user}/{user}/main/light_mode.svg">
    <img alt="Reza Mirjalili's GitHub profile card" src="https://raw.githubusercontent.com/{user}/{user}/main/light_mode.svg">
  </picture>
</a>
"""


def main():
    offline = "--offline" in sys.argv
    user = os.environ.get("USER_NAME") or os.environ.get("GITHUB_REPOSITORY_OWNER")
    token = os.environ.get("ACCESS_TOKEN")

    cache_path = ROOT / "cache" / "stats.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    stats = cache.get("stats", dict(repos=0, contributed=0, stars=0, commits=0,
                                    followers=0, loc_add=0, loc_del=0))

    if not offline and token and user:
        print(f"Fetching stats for {user} …")
        stats = fetch_stats(user, token, cache)
        cache["stats"] = stats
        cache_path.parent.mkdir(exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True))
    elif not offline:
        print("ACCESS_TOKEN / USER_NAME not set — using cached stats.")

    today = dt.date.today()
    for name, theme in THEMES.items():
        f = ASCII_FILES.get(name)
        f = f if f and f.exists() else ROOT / "ascii.txt"
        art = f.read_text(encoding="utf-8").rstrip("\n").split("\n") if f.exists() else []
        (ROOT / f"{name}.svg").write_text(build_svg(theme, art, stats, today), encoding="utf-8")
    if user:
        (ROOT / "README.md").write_text(README.format(user=user), encoding="utf-8")
    print("Stats:", stats)


if __name__ == "__main__":
    main()
