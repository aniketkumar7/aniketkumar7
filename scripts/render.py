"""
Renders every README card into cards/*.svg from live GitHub data.
Runs daily via .github/workflows/render-cards.yml (needs GITHUB_TOKEN; locally falls back to `gh auth token`).

Design: dark terminal windows + editorial serif. Cards are opaque, so they read the same on
GitHub light and dark themes. Animations are SMIL (GitHub runs it inside <img> SVGs; no JS/CSS anims).

    python scripts/render.py
"""
import base64
import datetime as dt
import html
import json
import os
import subprocess
import urllib.request
from collections import Counter, OrderedDict

from PIL import Image

USER = "aniketkumar7"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "cards")

# ---- content you edit -------------------------------------------------------
ROLE = "SOFTWARE ENGINEER @ CATALYZE-X"
FIRST, LAST = "Aniket", "Kumar"
TYPED = [
    ("$ whoami", "full-stack engineer. API design -> backend -> polished UI."),
    ("$ cat focus.txt", "scalable backends · clean UI/UX · developer tooling"),
    ("$ cat now.txt", "legal-tech at Catalyze-X, side projects on weekends"),
]
FOOTER = "loc: Uttar Pradesh, IN  ·  edu: B.Tech CSE '25  ·  offline: gaming"

STACK = OrderedDict([
    ("languages", ["TypeScript", "JavaScript", "Python", "C++", "HTML", "CSS"]),
    ("frontend", ["React", "Next.js", "React Router", "Tailwind", "Vite", "Redux", "Zustand"]),
    ("backend", ["FastAPI", "Node.js", "Express", "MongoDB", "MySQL", "Redis", "Supabase", "Firebase"]),
    ("tools", ["Docker", "GitHub Actions", "AWS", "Vercel", "Linux", "Git", "Figma"]),
])

# name on GitHub (None = private, card links to demo), card title, blurb, stack, demo
FEATURED = [
    ("LinkVault", "LinkVault", "Save and organize links from Reels, Shorts, TikToks and the web. Collections, tags, auto metadata.",
     "React · Express · Supabase", "https://link-vault-two.vercel.app/"),
    ("Tydo", "Tydo", "Productivity workspace: todos, kanban, habits, focus timer, notes and analytics in one app.",
     "React · TanStack Query · Supabase · Hono", "https://tydo-rho.vercel.app"),
    (None, "Kaarigar Studio", "Business site for a laser cutting, CNC routing and engraving workshop.",
     "React Router v7 · Vite · Tailwind", "https://kaarigar-studio-mu.vercel.app"),
    ("NETFLIX_GPT", "Netflix GPT", "Netflix clone with GPT-powered movie search and recommendations.",
     "React · Redux Toolkit · Firebase · OpenAI", "https://netflix-gpt-jade-five.vercel.app"),
    ("Modern_Portfolio", "Modern Portfolio", "Responsive portfolio with dynamic themes and smooth motion.",
     "React · Vite · Framer Motion", "https://modern-portfolio-peach-ten.vercel.app/"),
]

# ---- palette ----------------------------------------------------------------
BG, BG2, PANEL, LINE = "#0b0e14", "#11151d", "#161b24", "#262c38"
INK, MUTED, DIM = "#e6edf3", "#8b949e", "#4b5563"
AMBER, BLUE, GREEN = "#ffb340", "#3b82f6", "#22c55e"
HEAT = ["#171c26", "#4a3108", "#8a5a0c", "#d48b12", "#ffb84d"]
LANG_DOT = {"TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572a5", "CSS": "#663399",
            "HTML": "#e34c26", "C++": "#f34b7d", "Jupyter Notebook": "#da5b0b"}
W = 880


# ---- data -------------------------------------------------------------------
def token():
    return os.environ.get("GITHUB_TOKEN") or subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def gql(query):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {token()}", "User-Agent": USER},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch():
    names = [f[0] for f in FEATURED if f[0]]
    repo_q = "".join(
        f'r{i}: repository(owner:"{USER}", name:"{n}") {{ stargazerCount primaryLanguage {{ name }} }}'
        for i, n in enumerate(names)
    )
    d = gql(f"""{{
      user(login:"{USER}") {{
        contributionsCollection {{ contributionCalendar {{ totalContributions
          weeks {{ contributionDays {{ date contributionCount }} }} }}
          totalCommitContributions totalPullRequestReviewContributions restrictedContributionsCount }}
        repositories(ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false, first:100) {{
          totalCount nodes {{ stargazerCount forkCount languages(first:10) {{ edges {{ size node {{ name }} }} }} }} }}
        pullRequests {{ totalCount }}
        issues {{ totalCount }}
        followers {{ totalCount }}
        repositoriesContributedTo(contributionTypes:[COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) {{ totalCount }}
      }}
      {repo_q}
    }}""")
    u = d["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [(dt.date.fromisoformat(x["date"]), x["contributionCount"])
            for w in cal["weeks"] for x in w["contributionDays"]]
    langs = Counter()
    for node in u["repositories"]["nodes"]:
        for e in node["languages"]["edges"]:
            langs[e["node"]["name"]] += e["size"]
    repos = {n: d[f"r{i}"] for i, n in enumerate(names)}
    cc, nodes = u["contributionsCollection"], u["repositories"]["nodes"]
    gh = {
        "stars": sum(n["stargazerCount"] for n in nodes),
        "forks": sum(n["forkCount"] for n in nodes),
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "reviews": cc["totalPullRequestReviewContributions"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "followers": u["followers"]["totalCount"],
        "languages": len(langs),
    }
    return days, cal["totalContributions"], u["repositories"]["totalCount"], langs, repos, gh


def compute(days):
    today = days[-1][0]
    counts = dict(days)
    # current streak: today may still be empty, so start from yesterday in that case
    cur, d = 0, today if counts[today] else today - dt.timedelta(days=1)
    while counts.get(d, 0) > 0:
        cur, d = cur + 1, d - dt.timedelta(days=1)
    longest = run = 0
    for _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    months = OrderedDict()
    y, m = today.year, today.month
    for _ in range(12):
        months[(y, m)] = 0
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months = OrderedDict(reversed(list(months.items())))
    for day, c in days:
        if (day.year, day.month) in months:
            months[(day.year, day.month)] += c
    return {
        "current": cur, "longest": longest, "active": sum(1 for _, c in days if c),
        "span": len(days), "busiest": max(c for _, c in days), "months": months,
    }


# ---- svg helpers ------------------------------------------------------------
def esc(s):
    return html.escape(str(s), quote=True)


def fonts(*names):
    rules = []
    for n in names:
        with open(os.path.join(ROOT, "fonts", f"{n}.woff2"), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        rules.append(f"@font-face{{font-family:'{n}';src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "<style>" + "".join(rules) + \
        ".m{font-family:'mono',ui-monospace,Menlo,Consolas,monospace}" \
        ".mb{font-family:'mono-bold',ui-monospace,Menlo,Consolas,monospace;font-weight:700}" \
        ".s{font-family:'serif',Georgia,serif}.si{font-family:'serif-italic',Georgia,serif;font-style:italic}</style>"


def svg(w, h, body, *font_names):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'{fonts(*font_names)}{body}</svg>')


def window(w, h, title, inset=6):
    """Rounded terminal window with traffic lights. Returns (markup, content_top_y)."""
    x, y, ww, hh = inset, inset, w - 2 * inset, h - 2 * inset
    dots = "".join(f'<circle cx="{x + 22 + i * 18}" cy="{y + 18}" r="5.5" fill="{c}"/>'
                   for i, c in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]))
    return (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG2}"/>'
            f'<stop offset="1" stop-color="{BG}"/></linearGradient></defs>'
            f'<rect x="{x}" y="{y}" width="{ww}" height="{hh}" rx="14" fill="url(#bg)" stroke="{LINE}"/>'
            f'<line x1="{x}" y1="{y + 36}" x2="{x + ww}" y2="{y + 36}" stroke="{LINE}"/>{dots}'
            f'<text class="m" x="{w / 2}" y="{y + 22}" fill="{MUTED}" font-size="12" text-anchor="middle">'
            f'{esc(title)}</text>'), y + 36


def typed(x, y, text, size, color, begin, cps=40, cls="m", uid="t"):
    """Text revealed left->right like typing (clip wipe, stepped)."""
    width = len(text) * size * 0.6 + 2
    dur = max(len(text) / cps, 0.05)
    return (f'<clipPath id="{uid}"><rect x="{x}" y="{y - size}" height="{size * 1.4}" width="0">'
            f'<animate attributeName="width" from="0" to="{width:.1f}" begin="{begin:.2f}s" dur="{dur:.2f}s" '
            f'calcMode="discrete" values="{";".join(f"{width * i / max(len(text), 1):.1f}" for i in range(len(text) + 1))}" '
            f'fill="freeze"/></rect></clipPath>'
            f'<text class="{cls}" x="{x}" y="{y}" fill="{color}" font-size="{size}" xml:space="preserve" '
            f'clip-path="url(#{uid})">{esc(text)}</text>'), begin + dur


def cursor(x, y, size, begin, color=AMBER):
    return (f'<rect x="{x}" y="{y - size + 2}" width="{size * 0.6}" height="{size}" fill="{color}" opacity="0">'
            f'<set attributeName="opacity" to="1" begin="{begin:.2f}s"/>'
            f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" dur="1s" '
            f'begin="{begin:.2f}s" repeatCount="indefinite"/></rect>')


def fade(begin, dur=0.5):
    return (f'<animate attributeName="opacity" from="0" to="1" begin="{begin:.2f}s" dur="{dur}s" fill="freeze"/>')


def wrap(text, chars):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > chars and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur] if cur else lines


def save(name, content):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  {name:28s} {len(content) // 1024:>4d} KB")


# ---- cards ------------------------------------------------------------------
def ascii_rows(cols, rows):
    """source-prepped.png is a light subject on black; brighter pixel -> denser char, black -> blank."""
    im = Image.open(os.path.join(ROOT, "source-prepped.png")).convert("L").resize((cols, rows), Image.LANCZOS)
    ramp = " .:-=+*#%@"
    px = im.load()
    out = []
    for y in range(rows):
        row = ""
        for x in range(cols):
            lum = (px[x, y] / 255) ** 0.9
            row += " " if lum < 0.08 else ramp[min(len(ramp) - 1, int(lum * (len(ramp) - 1) + 0.5))]
        out.append(row)
    return out


def hero():
    h = 480
    frame, top = window(W, h, f"{USER}@github: ~/readme")
    b = [frame]
    x = 40
    b.append(f'<text class="m" x="{x}" y="{top + 44}" fill="{AMBER}" font-size="12" letter-spacing="1.5">'
             f'<tspan fill="{AMBER}">&#9656;</tspan> {esc(ROLE)}</text>')
    b.append(f'<text class="s" x="{x - 4}" y="{top + 128}" fill="{INK}" font-size="92" opacity="0">{FIRST}{fade(0.1, 0.8)}</text>')
    b.append(f'<text class="si" x="{x - 4}" y="{top + 206}" fill="{AMBER}" font-size="92" opacity="0">{LAST}{fade(0.4, 0.8)}</text>')
    t, ly = 1.0, top + 248
    for i, (cmd, out) in enumerate(TYPED):
        m, t = typed(x, ly, cmd, 13, GREEN, t, uid=f"c{i}")
        b.append(m)
        m, t = typed(x, ly + 19, out, 13, INK, t + 0.15, cps=90, uid=f"o{i}")
        b.append(m)
        ly, t = ly + 44, t + 0.2
    b.append(f'<text class="m" x="{x}" y="{ly}" fill="{GREEN}" font-size="13" opacity="0">${fade(t, 0.1)}</text>')
    b.append(cursor(x + 14, ly, 13, t))
    b.append(f'<line x1="6" y1="{h - 42}" x2="{W - 6}" y2="{h - 42}" stroke="{LINE}"/>'
             f'<text class="m" x="{x}" y="{h - 19}" fill="{MUTED}" font-size="11.5">{esc(FOOTER)}</text>')

    # ascii portrait, right side, printed row by row
    cols, rows = 92, 49
    aw = ah = 330
    cw, ch = aw / cols, ah / rows
    ax, ay = W - aw - 34, top + 12
    rd = 4.0 / rows
    for r, line in enumerate(ascii_rows(cols, rows)):
        if not line.strip():
            continue
        yy = ay + r * ch
        b.append(f'<clipPath id="a{r}"><rect x="{ax}" y="{yy:.1f}" height="{ch:.2f}" width="0">'
                 f'<animate attributeName="width" from="0" to="{aw}" begin="{0.3 + r * rd:.2f}s" dur="{rd:.2f}s" '
                 f'fill="freeze"/></rect></clipPath>'
                 f'<text class="m" clip-path="url(#a{r})" x="{ax}" y="{yy + ch * 0.8:.1f}" fill="{INK}" opacity="0.92" '
                 f'font-size="{ch * 0.95:.2f}" textLength="{aw}" lengthAdjust="spacingAndGlyphs" '
                 f'xml:space="preserve">{esc(line)}</text>')
    return svg(W, h, "".join(b), "mono", "serif", "serif-italic")


def heatmap(days, total):
    h = 300
    frame, top = window(W, h, f"{USER}@github: ~/contributions.sh")
    b = [frame]
    x0 = 52
    b.append(f'<text class="m" x="40" y="{top + 34}" fill="{GREEN}" font-size="13">$ ./contributions.sh '
             f'<tspan fill="{MUTED}">--last-year</tspan></text>')
    b.append(f'<text class="s" x="40" y="{top + 74}" fill="{INK}" font-size="34">{total:,} contributions '
             f'<tspan class="si" fill="{AMBER}">in the last year</tspan></text>')
    b.append(f'<text class="m" x="{W - 40}" y="{top + 34}" fill="{DIM}" font-size="11" text-anchor="end" '
             f'letter-spacing="1.5">REFRESHED DAILY</text>')

    cell, gap = 11.5, 3.2
    gy = top + 104
    first = days[0][0]
    offset = (first.weekday() + 1) % 7  # sunday = row 0
    peak = max(c for _, c in days) or 1
    weeks = {}
    for i, (day, c) in enumerate(days):
        wk, wd = divmod(i + offset, 7)
        lvl = 0 if c == 0 else min(4, 1 + int(3 * c / peak + 0.5)) if c < peak else 4
        weeks.setdefault(wk, []).append(
            f'<rect x="{x0 + wk * (cell + gap):.1f}" y="{gy + wd * (cell + gap):.1f}" width="{cell}" '
            f'height="{cell}" rx="2.5" fill="{HEAT[lvl]}"/>')
        if day.day == 1 or i == 0:
            b.append(f'<text class="m" x="{x0 + wk * (cell + gap):.1f}" y="{gy - 8}" fill="{MUTED}" '
                     f'font-size="10">{day.strftime("%b")}</text>')
    for wk, cells in weeks.items():
        b.append(f'<g opacity="0">{"".join(cells)}{fade(0.2 + wk * 0.03, 0.35)}</g>')
    for wd, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        b.append(f'<text class="m" x="{x0 - 8}" y="{gy + wd * (cell + gap) + 9}" fill="{DIM}" font-size="9.5" '
                 f'text-anchor="end">{lab}</text>')
    ly = gy + 7 * (cell + gap) + 18
    lx = W - 40 - 5 * 14 - 34
    b.append(f'<text class="m" x="{lx - 8}" y="{ly + 9}" fill="{DIM}" font-size="10" text-anchor="end">less</text>')
    for i, c in enumerate(HEAT):
        b.append(f'<rect x="{lx + i * 14}" y="{ly}" width="10" height="10" rx="2" fill="{c}"/>')
    b.append(f'<text class="m" x="{lx + 5 * 14 + 4}" y="{ly + 9}" fill="{DIM}" font-size="10">more</text>')
    return svg(W, h, "".join(b), "mono", "serif", "serif-italic")


def activity(st, total):
    h = 320
    frame, top = window(W, h, f"{USER}@github: ~/stats")
    b = [frame]
    b.append(f'<text class="m" x="40" y="{top + 34}" fill="{GREEN}" font-size="13">$ git log --since="12 months" '
             f'<tspan fill="{MUTED}">| stats</tspan></text>')
    b.append(f'<text class="s" x="40" y="{top + 78}" fill="{INK}" font-size="40">{total:,} '
             f'<tspan class="si">contributions</tspan></text>')

    months = st["months"]
    peak = max(months.values()) or 1
    bx, base, maxh, bw, step = 40, h - 46, 118, 30, 40
    for i, ((y, m), c) in enumerate(months.items()):
        hh = max(3, maxh * c / peak) if c else 3
        x = bx + i * step
        col = AMBER if c == peak else ("#2a3140" if c == 0 else "#cfd6df")
        d = 0.3 + i * 0.07
        b.append(f'<rect x="{x}" y="{base}" width="{bw}" height="0" rx="3" fill="{col}">'
                 f'<animate attributeName="height" from="0" to="{hh:.1f}" begin="{d:.2f}s" dur="0.6s" fill="freeze" '
                 f'calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>'
                 f'<animate attributeName="y" from="{base}" to="{base - hh:.1f}" begin="{d:.2f}s" dur="0.6s" '
                 f'fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/></rect>')
        b.append(f'<text class="m" x="{x + bw / 2}" y="{base + 18}" fill="{MUTED}" font-size="10" '
                 f'text-anchor="middle">{dt.date(y, m, 1).strftime("%b")}</text>')
        if c == peak:
            b.append(f'<text class="m" x="{x + bw / 2}" y="{base - hh - 8:.1f}" fill="{AMBER}" font-size="11" '
                     f'text-anchor="middle" opacity="0">{c:,}{fade(d + 0.5)}</text>')

    rx = 560
    rows = [
        (f"{st['current']}", "days", f"current streak · longest {st['longest']}"),
        (f"{st['active']}", f"/ {st['span']}", "days with a contribution"),
        (f"{st['busiest']}", "", "on the busiest day"),
    ]
    for i, (big, unit, lab) in enumerate(rows):
        y = top + 60 + i * 74
        b.append(f'<g opacity="0">{fade(0.6 + i * 0.2)}'
                 f'<text class="s" x="{rx}" y="{y}" fill="{INK}" font-size="38">{big}'
                 f'<tspan class="si" fill="{MUTED}" font-size="26"> {unit}</tspan></text>'
                 f'<text class="m" x="{rx}" y="{y + 22}" fill="{MUTED}" font-size="11">{esc(lab)}</text></g>')
        if i < 2:
            b.append(f'<line x1="{rx}" y1="{y + 40}" x2="{W - 40}" y2="{y + 40}" stroke="{LINE}"/>')
    return svg(W, h, "".join(b), "mono", "serif", "serif-italic")


def block(name, color, ink, label, big, unit, desc):
    w, h, p = W / 3, 210, 6
    b = [f'<rect x="{p}" y="{p}" width="{w - 2 * p:.1f}" height="{h - 2 * p}" rx="14" fill="{color}"/>',
         f'<text class="mb" x="26" y="40" fill="{ink}" font-size="11" letter-spacing="1.8">{esc(label)}</text>',
         f'<text class="m" x="{w - 26:.1f}" y="40" fill="{ink}" font-size="13" text-anchor="end">&#8594;</text>',
         f'<text class="si" x="24" y="112" fill="{ink}" font-size="50">{esc(big)}'
         f'<tspan font-size="30"> {esc(unit)}</tspan></text>']
    for i, line in enumerate(wrap(desc, 34)):
        b.append(f'<text class="m" x="26" y="{148 + i * 17}" fill="{ink}" font-size="11.5" opacity="0.92">{esc(line)}</text>')
    save(name, svg(round(w, 2), h, "".join(b), "mono", "mono-bold", "serif-italic"))


def stack():
    h = 70 + 46 * len(STACK) + 30
    frame, top = window(W, h, f"{USER}@github: ~/stack")
    b = [frame, f'<text class="m" x="40" y="{top + 34}" fill="{GREEN}" font-size="13">$ ls ~/stack</text>']
    y = top + 70

    for group, items in STACK.items():
        b.append(f'<text class="m" x="40" y="{y + 5}" fill="{AMBER}" font-size="12.5">{group}/</text>')
        x = 160
        for it in items:
            pw = len(it) * 7.2 + 24
            dot = LANG_DOT.get(it, MUTED)
            b.append(f'<g><rect x="{x}" y="{y - 13}" width="{pw:.1f}" height="26" rx="13" '
                     f'fill="{PANEL}" stroke="{LINE}"/><circle cx="{x + 12}" cy="{y}" r="3" fill="{dot}"/>'
                     f'<text class="m" x="{x + 20}" y="{y + 4}" fill="{INK}" font-size="12">{esc(it)}</text></g>')
            x += pw + 8
        y += 46
    return svg(W, h, "".join(b), "mono")


def strip(name, cmd, sub):
    h = 76
    b = [f'<rect x="6" y="6" width="{W - 12}" height="{h - 12}" rx="14" fill="{BG}" stroke="{LINE}"/>',
         f'<text class="m" x="34" y="{h / 2 + 5}" fill="{GREEN}" font-size="14">{esc(cmd)}</text>',
         f'<text class="si" x="{W - 34}" y="{h / 2 + 9}" fill="{INK}" font-size="28" text-anchor="end">{esc(sub)}</text>']
    save(name, svg(W, h, "".join(b), "mono", "serif-italic"))


def repo_card(i, gh_name, title, blurb, tech, demo, info, width):
    h, p = 200, 6
    lang = (info or {}).get("primaryLanguage") or {}
    lang = lang.get("name") if lang else None
    dot = LANG_DOT.get(lang, AMBER)
    stars = (info or {}).get("stargazerCount")
    b = [f'<rect x="{p}" y="{p}" width="{width - 2 * p:.1f}" height="{h - 2 * p}" rx="14" fill="{PANEL}" stroke="{LINE}"/>',
         f'<text class="m" x="26" y="38" fill="{DIM}" font-size="11">./{i + 1:02d}{"" if gh_name else "  · private repo"}</text>',
         f'<text class="m" x="{width - 26:.1f}" y="38" fill="{AMBER}" font-size="11" text-anchor="end">live &#8599;</text>',
         f'<circle cx="31" cy="67" r="5" fill="{dot}"/>',
         f'<text class="mb" x="44" y="72" fill="{INK}" font-size="16">{esc(title)}</text>']
    for j, line in enumerate(wrap(blurb, int((width - 52) / 7.1))[:3]):
        b.append(f'<text class="m" x="26" y="{100 + j * 17}" fill="{MUTED}" font-size="11.5">{esc(line)}</text>')
    meta = tech + (f"  ★ {stars}" if stars else "")
    b.append(f'<line x1="{p}" y1="{h - 42}" x2="{width - p:.1f}" y2="{h - 42}" stroke="{LINE}"/>')
    b.append(f'<text class="m" x="26" y="{h - 19}" fill="{DIM}" font-size="10.5">{esc(meta)}</text>')
    return svg(round(width, 2), h, "".join(b), "mono", "mono-bold")


TIERS = ["C", "B", "A", "AA", "AAA", "S"]


def tier(value, steps):
    """steps = thresholds for C..S; returns index into TIERS or -1 if locked."""
    return sum(value >= s for s in steps) - 1


def img_b64(name):
    path = os.path.join(ROOT, name)
    if not os.path.exists(path):
        return None
    mime = "image/jpeg" if name.endswith(".jpg") else "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def portrait_circle(name, cx, cy, r):
    """Round illustrated portrait (already circular art) fitted into the rank ring, gently floating."""
    data = img_b64(name)
    disc = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{PANEL}"/>'
    if not data:
        return disc
    s = 2 * r * 1.04  # art's own circle sits ~2% inside its square, so overscan then clip
    y0 = cy - s / 2
    return (f'{disc}<clipPath id="pc"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>'
            f'<g clip-path="url(#pc)"><image href="{data}" x="{cx - s / 2:.1f}" y="{y0:.1f}" width="{s:.1f}" height="{s:.1f}">'
            f'<animate attributeName="y" values="{y0:.1f};{y0 - 2:.1f};{y0:.1f}" dur="4s" repeatCount="indefinite"/>'
            f'</image></g>')


def footer():
    """Sign-off banner: full-bleed illustration, dark fade on the left carrying the copy."""
    h = 420
    data = img_b64("footer-scene.jpg")
    b = [f'<defs><clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{h - 12}" rx="14"/></clipPath>'
         f'<linearGradient id="fadeL" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BG}" stop-opacity="0.92"/>'
         f'<stop offset="0.45" stop-color="{BG}" stop-opacity="0.55"/><stop offset="0.7" stop-color="{BG}" stop-opacity="0"/></linearGradient>'
         f'<linearGradient id="fadeB" x1="0" y1="0" x2="0" y2="1"><stop offset="0.6" stop-color="{BG}" stop-opacity="0"/>'
         f'<stop offset="1" stop-color="{BG}" stop-opacity="0.6"/></linearGradient></defs>',
         f'<g clip-path="url(#card)"><rect width="{W}" height="{h}" fill="{BG}"/>']
    if data:
        iw = W + 24  # cover the width (+ room for a slow pan); crop top/bottom evenly
        ih = iw * 619 / 1100
        y0 = (h - ih) / 2
        b.append(f'<image href="{data}" x="-24" y="{y0:.1f}" width="{iw}" height="{ih:.1f}">'
                 f'<animate attributeName="x" values="-24;0;-24" dur="18s" repeatCount="indefinite"/></image>')
    b.append(f'<rect width="{W}" height="{h}" fill="url(#fadeL)"/><rect width="{W}" height="{h}" fill="url(#fadeB)"/>'
             f'<text class="m" x="44" y="96" fill="{GREEN}" font-size="13">$ ./connect --all</text>'
             f'<text class="s" x="40" y="168" fill="#ffffff" font-size="60">Let&#8217;s build</text>'
             f'<text class="si" x="40" y="234" fill="{AMBER}" font-size="60">something.</text>'
             f'<text class="m" x="44" y="276" fill="{INK}" font-size="12.5">side projects · collabs · good ideas</text>'
             f'<text class="m" x="44" y="302" fill="{GREEN}" font-size="12.5">$<tspan fill="{INK}"> reply within a day</tspan></text>'
             f'{cursor(214, 302, 12.5, 0.5)}')
    b.append(f'</g><rect x="6" y="6" width="{W - 12}" height="{h - 12}" rx="14" fill="none" stroke="{LINE}"/>')
    return svg(W, h, "".join(b), "mono", "serif", "serif-italic")


def gh_stats(gh, st, total):
    h = 300
    frame, top = window(W, h, f"{USER}@github: ~/stats --all")
    b = [frame, f'<text class="m" x="40" y="{top + 34}" fill="{GREEN}" font-size="13">$ gh api user '
                f'<tspan fill="{MUTED}">| jq .stats</tspan></text>']
    cells = [
        (f"{gh['commits']:,}", "commits, last year"), (f"{gh['prs']}", "pull requests"),
        (f"{gh['stars']}", "stars earned"), (f"{gh['contributed']}", "contributed to"),
        (f"{gh['issues']}", "issues opened"), (f"{gh['forks']}", "forks of my repos"),
        (f"{gh['languages']}", "languages written"), (f"{gh['followers']}", "followers"),
    ]
    for i, (big, lab) in enumerate(cells):
        col, row = i % 4, i // 4
        x, y = 40 + col * 140, top + 100 + row * 92
        b.append(f'<g opacity="0">{fade(0.2 + i * 0.08)}'
                 f'<text class="s" x="{x}" y="{y}" fill="{INK}" font-size="40">{big}</text>'
                 f'<text class="m" x="{x}" y="{y + 22}" fill="{MUTED}" font-size="10.5">{esc(lab)}</text></g>')
    b.append(f'<line x1="40" y1="{top + 145}" x2="580" y2="{top + 145}" stroke="{LINE}"/>')

    # rank ring: each factor capped at 1 then weighted, so one huge number can't carry the grade
    factors = [(gh["commits"], 1000, 3), (gh["prs"], 100, 2), (gh["stars"], 50, 2), (gh["issues"], 50, 1),
               (gh["reviews"], 20, 1), (st["longest"], 60, 2), (gh["contributed"], 20, 1)]
    score = sum(min(v / target, 1) * w for v, target, w in factors) / sum(w for *_, w in factors)
    grade = next(g for t, g in ((0.9, "S"), (0.75, "A+"), (0.55, "A"), (0.4, "A-"), (0.28, "B+"), (0.15, "B"),
                                (0, "C")) if score >= t)
    pct = min(score / 0.9, 1)
    cx, cy, r = 735, top + 118, 70
    circ = 2 * 3.14159 * r
    b.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{LINE}" stroke-width="10"/>'
             f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{AMBER}" stroke-width="10" '
             f'stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ:.1f}" '
             f'transform="rotate(-90 {cx} {cy})"><animate attributeName="stroke-dashoffset" from="{circ:.1f}" '
             f'to="{circ * (1 - pct):.1f}" begin="0.3s" dur="1.4s" fill="freeze" calcMode="spline" '
             f'keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/></circle>'
             f'{portrait_circle("portrait-bust.jpg", cx, cy, r - 9)}'
             f'<text class="m" x="{cx}" y="{cy + r + 34}" fill="{MUTED}" font-size="11" text-anchor="middle" '
             f'letter-spacing="1.5">RANK · <tspan class="mb" fill="{AMBER}">{grade}</tspan></text>')
    return svg(W, h, "".join(b), "mono", "serif", "serif-italic")


def trophies(gh, st, repo_count):
    items = [
        ("COMMITS", gh["commits"], [1, 50, 200, 500, 1000, 2000], "commits"),
        ("STREAK", st["longest"], [3, 7, 14, 30, 60, 100], "day streak"),
        ("ACTIVE", st["active"], [30, 60, 120, 200, 300, 350], "active days"),
        ("POLYGLOT", gh["languages"], [1, 3, 5, 7, 9, 12], "languages"),
        ("SHIPPER", repo_count, [1, 5, 10, 20, 35, 50], "public repos"),
        ("STARS", gh["stars"], [1, 5, 10, 30, 50, 100], "stars"),
    ]
    h = 320
    frame, top = window(W, h, f"{USER}@github: ~/trophies")
    # metal per tier: (light, dark). locked trophies render as a dim outline.
    metal = {"C": ("#f0b47c", "#8a4f24"), "B": ("#f4f6fa", "#7d8794"), "A": ("#ffe08a", "#b07a12"),
             "AA": ("#ffe08a", "#b07a12"), "AAA": ("#fff0b8", "#c98a0c"), "S": ("#fff6d6", "#ffb340")}
    defs = "".join(f'<linearGradient id="m{g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{lt}"/>'
                   f'<stop offset="1" stop-color="{dk}"/></linearGradient>' for g, (lt, dk) in metal.items())
    defs += (f'<radialGradient id="glow"><stop offset="0" stop-color="{AMBER}" stop-opacity="0.45"/>'
             f'<stop offset="1" stop-color="{AMBER}" stop-opacity="0"/></radialGradient>')
    bowl = "M8 4 H52 V18 C52 34 42 44 30 44 C18 44 8 34 8 18 Z"
    b = [frame, f"<defs>{defs}</defs>",
         f'<text class="m" x="40" y="{top + 34}" fill="{GREEN}" font-size="13">$ ls ~/trophies '
         f'<tspan fill="{MUTED}">--sort=rank</tspan></text>']
    bw = (W - 80 - 5 * 12) / 6
    for i, (name, val, steps, unit) in enumerate(items):
        t = tier(val, steps)
        g = TIERS[t] if t >= 0 else None
        nxt = f"next at {steps[t + 1]:,}" if t + 1 < len(steps) else "maxed out"
        x, y = 40 + i * (bw + 12), top + 54
        cx = x + bw / 2
        fill = f"url(#m{g})" if g else "none"
        stroke = "none" if g else DIM
        dark = metal[g][1] if g else DIM
        # cup drawn in a 60x66 box, scaled 1.05 and centred
        ox, oy, s = cx - 31.5, y + 40, 1.05
        cup = (f'<g transform="translate({ox:.1f} {oy}) scale({s})" stroke="{stroke}" stroke-width="1.5">'
               f'<path d="M8 9 H2 C-1 9 -1 14 0 17 C2 25 6 28 11 29 M52 9 H58 C61 9 61 14 60 17 C58 25 54 28 49 29" '
               f'fill="none" stroke="{dark if g else DIM}" stroke-width="3.2" stroke-linecap="round"/>'
               f'<path d="{bowl}" fill="{fill}"/>'
               f'<rect x="26" y="44" width="8" height="9" fill="{fill}"/>'
               f'<rect x="18" y="53" width="24" height="5" rx="1.5" fill="{fill}"/>'
               f'<rect x="13" y="58" width="34" height="8" rx="2" fill="{dark if g else "none"}"/>')
        if g:
            cup += (f'<rect x="8" y="4" width="44" height="3" fill="#ffffff" opacity="0.35"/>'
                    f'<text class="si" x="30" y="{30 if len(g) < 3 else 29}" fill="{dark}" font-size="{17 if len(g) < 3 else 12}" '
                    f'text-anchor="middle" stroke="none" opacity="0.85">{g}</text>'
                    f'<clipPath id="cl{i}"><path d="{bowl}"/></clipPath>'
                    f'<g clip-path="url(#cl{i})"><rect x="-20" y="0" width="9" height="50" fill="#ffffff" opacity="0.45" '
                    f'transform="skewX(-20)"><animate attributeName="x" values="-20;80;80" keyTimes="0;0.25;1" '
                    f'dur="4s" begin="{1 + i * 0.25:.2f}s" repeatCount="indefinite"/></rect></g>')
        cup += "</g>"
        glow = f'<circle cx="{cx:.1f}" cy="{y + 70}" r="52" fill="url(#glow)"/>' if g == "S" else ""
        stars = "".join(
            f'<path transform="translate({cx - 35 + k * 14:.1f} {y + 132}) scale(0.5)" '
            f'd="M10 0 L12.9 6.9 L20 7.6 L14.6 12.3 L16.2 19.5 L10 15.7 L3.8 19.5 L5.4 12.3 L0 7.6 L7.1 6.9 Z" '
            f'fill="{AMBER if k <= t else LINE}"/>' for k in range(6))
        b.append(f'<g opacity="0">{fade(0.2 + i * 0.12)}'
                 f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="206" rx="12" fill="{PANEL}" '
                 f'stroke="{AMBER if t >= 4 else LINE}"/>{glow}'
                 f'<text class="mb" x="{cx:.1f}" y="{y + 24}" fill="{MUTED}" font-size="10" letter-spacing="1.4" '
                 f'text-anchor="middle">{name}</text>{cup}{stars}'
                 f'<text class="m" x="{cx:.1f}" y="{y + 170}" fill="{INK}" font-size="11" text-anchor="middle">'
                 f'{val:,} {esc(unit)}</text>'
                 f'<text class="m" x="{cx:.1f}" y="{y + 188}" fill="{DIM}" font-size="9.5" text-anchor="middle">'
                 f'{nxt}</text></g>')
    return svg(W, h, "".join(b), "mono", "mono-bold", "serif-italic")


ICONS = {
    # 24x24 line icons, stroked
    "globe": '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 7h14M5 17h14"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "linkedin": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 10v7M8 7v.01M12 17v-4a2 2 0 0 1 4 0v4M12 10v7"/>',
    "youtube": '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="M10 9l5 3-5 3z" fill="currentColor"/>',
}


def link_card(name, icon, color, label, handle):
    w, h, p = W / 4, 128, 6
    b = [f'<rect x="{p}" y="{p}" width="{w - 2 * p:.1f}" height="{h - 2 * p}" rx="14" fill="{PANEL}" stroke="{LINE}"/>',
         f'<rect x="22" y="22" width="40" height="40" rx="10" fill="{color}" opacity="0.14"/>',
         f'<g transform="translate(30 30)" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
         f'stroke-linejoin="round" color="{color}">{ICONS[icon]}</g>',
         f'<text class="m" x="{w - 24:.1f}" y="40" fill="{MUTED}" font-size="14" text-anchor="end">&#8599;</text>',
         f'<text class="si" x="22" y="92" fill="{INK}" font-size="24">{esc(label)}</text>',
         f'<text class="m" x="22" y="110" fill="{MUTED}" font-size="10.5">{esc(handle)}</text>']
    save(name, svg(round(w, 2), h, "".join(b), "mono", "serif-italic"))


def main():
    os.makedirs(OUT, exist_ok=True)
    days, total, repo_count, langs, repos, gh = fetch()
    st = compute(days)
    top_lang, top_bytes = langs.most_common(1)[0]
    pct = round(100 * top_bytes / sum(langs.values()))
    others = ", ".join(n for n, _ in langs.most_common(4)[1:])

    save("hero.svg", hero())
    save("heatmap.svg", heatmap(days, total))
    save("activity.svg", activity(st, total))
    save("gh-stats.svg", gh_stats(gh, st, total))
    save("trophies.svg", trophies(gh, st, repo_count))
    block("ship.svg", BLUE, "#ffffff", "SHIP", f"{repo_count}", "repos",
          "Public projects, most live on Vercel. Idea to deployed in a weekend.")
    block("commit.svg", AMBER, "#1a1204", "COMMIT", f"{st['active']}", "days",
          f"Active in the last year. Longest streak: {st['longest']} days.")
    block("stack.svg", GREEN, "#04140a", "STACK", f"{pct}%", top_lang,
          f"Of the code across my public repos. Then {others}.")
    save("stack-list.svg", stack())
    strip("title-projects.svg", "$ ls ~/projects --featured", "What I've built")
    save("connect-scene.svg", footer())
    link_card("link-portfolio.svg", "globe", AMBER, "Portfolio", "modern-portfolio.vercel.app")
    link_card("link-email.svg", "mail", GREEN, "Email", "aniketkumar639597@gmail")
    link_card("link-linkedin.svg", "linkedin", BLUE, "LinkedIn", "in/aniketkumar07")
    link_card("link-youtube.svg", "youtube", "#ff4d4d", "YouTube", "watch my builds")
    for i, f in enumerate(FEATURED):
        width = W / 3 if i < 3 else W / 2
        save(f"repo-{i + 1}.svg", repo_card(i, *f, repos.get(f[0]), width))


if __name__ == "__main__":
    main()
