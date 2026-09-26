"""Actions guard for the code-corhuila organization.

The organization has 3,000 GitHub Actions minutes a month for private
repositories and a $0 budget: once the minutes run out, no job starts in ANY
private repository until the next month. In September 2026 one team's 30-minute
cron across 15 repositories spent the whole quota in four days and blocked every
other team.

This guard runs from the public .github repository (public repositories do not
spend the quota) and enforces ACTIONS-POLICY.md:

  1. Blocking rules: a private repository's workflow triggered by `schedule` or
     `workflow_run` is disabled and an issue explains why.
  2. Circuit breaker: a private repository that spends more than
     REPO_DAILY_LIMIT minutes in a day gets all its workflows disabled.
  3. Quota watch: a tracking issue in .github shows the month's consumption and
     mentions the instructor when 50 %, 75 % and 90 % of the quota are crossed.
  4. Warnings (no action): jobs without `timeout-minutes`, `push` without a
     branch filter, pull-request CI without `concurrency`.

It never checks out or runs any repository's code: it reads workflow files and
billing data through the API.
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import yaml

ORG = os.environ.get("ORG", "code-corhuila")
TOKEN = (os.environ.get("GUARD_TOKEN") or "").strip()
LOCAL_GH = not TOKEN  # without a token, go through the local `gh` login (testing)
DRY = (os.environ.get("DRY_RUN") or "").lower() == "true"
QUOTA = int(os.environ.get("QUOTA_MINUTES") or 3000)
REPO_DAILY_LIMIT = int(os.environ.get("REPO_DAILY_LIMIT") or 60)
MAX_TIMEOUT = 15
NOTIFY = os.environ.get("NOTIFY", "ariel5253")
LEVELS = (50, 75, 90)
POLICY_URL = f"https://github.com/{ORG}/.github/blob/main/ACTIONS-POLICY.md"
MARK = "<!-- actions-guard"


# ── GitHub API ────────────────────────────────────────────────────────────────

def api(path, method="GET", payload=None):
    if LOCAL_GH:
        args = ["gh", "api", "-X", method, path]
        if payload is not None:
            args += ["--input", "-"]
        r = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            raise RuntimeError(f"{method} {path}: {r.stderr.strip() or r.stdout.strip()}")
        return json.loads(r.stdout or "{}")
    req = urllib.request.Request(
        f"https://api.github.com/{path}", method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "actions-guard"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read()[:300]!r}") from None


def graphql(query, **variables):
    data = api("graphql", "POST", {"query": query, "variables": variables})
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]


REPOS_QUERY = """
query($org: String!, $after: String) {
  organization(login: $org) {
    repositories(first: 40, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name visibility isArchived hasIssuesEnabled
        object(expression: "HEAD:.github/workflows") {
          ... on Tree { entries { name object { ... on Blob { text } } } }
        }
      }
    }
  }
}"""


def load_repos():
    repos, after = [], None
    while True:
        page = graphql(REPOS_QUERY, org=ORG, after=after)["organization"]["repositories"]
        for n in page["nodes"]:
            files = []
            for e in (n["object"] or {}).get("entries", []):
                if e["name"].endswith((".yml", ".yaml")) and e.get("object"):
                    files.append((e["name"], e["object"].get("text") or ""))
            repos.append({"name": n["name"], "private": n["visibility"] != "PUBLIC",
                          "archived": n["isArchived"], "issues": n["hasIssuesEnabled"],
                          "workflows": files})
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        after = page["pageInfo"]["endCursor"]


# ── Workflow rules ────────────────────────────────────────────────────────────

def triggers(doc):
    # YAML 1.1 reads the key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {t: None for t in on}
    return dict(on or {})


def check_workflow(text):
    """Returns (blocking, warnings) as lists of (rule, message)."""
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return [], [("R0", f"invalid YAML ({str(e).splitlines()[0]})")]
    trig = triggers(doc)
    blocking, warnings = [], []
    if "schedule" in trig:
        crons = ", ".join(c.get("cron", "?") for c in (trig["schedule"] or []) if isinstance(c, dict))
        blocking.append(("R1", f"`schedule` trigger ({crons})"))
    if "workflow_run" in trig:
        blocking.append(("R1", "`workflow_run` trigger (chained workflows)"))
    push = trig.get("push", "absent")
    if push != "absent" and not (isinstance(push, dict) and (push.get("branches") or push.get("tags"))):
        warnings.append(("R2", "`push` without a `branches` or `tags` filter"))
    for name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict) or "uses" in job:
            continue
        t = job.get("timeout-minutes")
        if t is None:
            warnings.append(("R3", f"job `{name}` has no `timeout-minutes` (default is 360)"))
        elif isinstance(t, (int, float)) and t > MAX_TIMEOUT:
            warnings.append(("R3", f"job `{name}` allows {t} minutes (maximum {MAX_TIMEOUT})"))
    if "pull_request" in trig and "concurrency" not in doc:
        warnings.append(("R4", "pull-request CI without `concurrency` (superseded runs keep running)"))
    return blocking, warnings


# ── Actions on repositories ───────────────────────────────────────────────────

def active_workflows(repo):
    out, page = [], 1
    while True:
        data = api(f"repos/{ORG}/{repo}/actions/workflows?per_page=100&page={page}")
        out += [w for w in data.get("workflows", []) if w["state"] == "active"]
        if len(data.get("workflows", [])) < 100:
            return out
        page += 1


def disable(repo, workflow):
    if DRY:
        return
    api(f"repos/{ORG}/{repo}/actions/workflows/{workflow['id']}/disable", "PUT")


def open_issue_once(repo, key, title, body):
    """Opens an issue unless an open one with the same marker already exists."""
    marker = f"{MARK}:{key} -->"
    existing = api(f"repos/{ORG}/{repo}/issues?state=open&per_page=100")
    if any(marker in (i.get("body") or "") for i in existing):
        return False
    if not DRY:
        api(f"repos/{ORG}/{repo}/issues", "POST", {"title": title, "body": f"{marker}\n{body}"})
    return True


def violation_body(file, reasons):
    items = "\n".join(f"- **{rule}**: {msg}" for rule, msg in reasons)
    return (
        f"El guardián de Actions de la organización **desactivó** el workflow "
        f"`.github/workflows/{file}` de este repositorio.\n\n{items}\n\n"
        f"La organización comparte un solo cupo de minutos para todos los repositorios "
        f"privados. Cuando se agota, **ningún** equipo puede ejecutar su CI hasta el mes "
        f"siguiente. Lee la política: {POLICY_URL}\n\n"
        f"**Para reactivarlo:** corrige el workflow en un PR (quita el disparador "
        f"prohibido) y pide al docente que lo reactive. Reactivarlo sin corregirlo hace "
        f"que el guardián lo vuelva a desactivar en la siguiente pasada.")


# ── Billing ───────────────────────────────────────────────────────────────────

def month_usage(now):
    data = api(f"organizations/{ORG}/settings/billing/usage?year={now.year}&month={now.month}")
    return [i for i in data.get("usageItems", []) if (i.get("product") or "").lower() == "actions"]


def upsert_tracking_issue(title, body, level_comments):
    marker = f"{MARK}:usage:{title} -->"
    issues = api(f"repos/{ORG}/.github/issues?state=open&per_page=100")
    issue = next((i for i in issues if marker in (i.get("body") or "")), None)
    if DRY:
        return
    if issue:
        api(f"repos/{ORG}/.github/issues/{issue['number']}", "PATCH", {"body": f"{marker}\n{body}"})
        number = issue["number"]
    else:
        number = api(f"repos/{ORG}/.github/issues", "POST",
                     {"title": title, "body": f"{marker}\n{body}"})["number"]
    posted = "\n".join(c.get("body") or "" for c in
                       api(f"repos/{ORG}/.github/issues/{number}/comments?per_page=100"))
    for level, text in level_comments:
        tag = f"{MARK}:level:{level} -->"
        if tag not in posted:
            api(f"repos/{ORG}/.github/issues/{number}/comments", "POST", {"body": f"{tag}\n{text}"})


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date().isoformat()
    repos = load_repos()
    private = {r["name"] for r in repos if r["private"]}
    by_name = {r["name"]: r for r in repos}
    log, warnings_all = [], []

    # 1. Blocking rules on workflow files.
    for r in repos:
        if r["archived"]:
            continue
        for file, text in r["workflows"]:
            if not r["private"]:
                continue  # public repositories do not spend the quota
            blocking, warnings = check_workflow(text)
            warnings_all += [(r["name"], file, rule, msg) for rule, msg in warnings]
            if not blocking:
                continue
            matches = [w for w in active_workflows(r["name"])
                       if w["path"] == f".github/workflows/{file}"]
            for w in matches:
                disable(r["name"], w)
                log.append(f"DISABLED {r['name']}/{file}: " + "; ".join(m for _, m in blocking))
                if r["issues"]:
                    open_issue_once(r["name"], f"disabled:{file}",
                                    f"[actions-guard] Workflow desactivado: {file}",
                                    violation_body(file, blocking))

    # 2. Circuit breaker and 3. quota watch, from billing data.
    items = month_usage(now)
    total, per_repo, per_repo_today = 0.0, {}, {}
    for i in items:
        repo = i.get("repositoryName") or "?"
        if repo in by_name and repo not in private:
            continue  # public repositories do not spend the quota
        q = float(i.get("quantity") or 0)
        total += q
        per_repo[repo] = per_repo.get(repo, 0) + q
        if (i.get("date") or "").startswith(today):
            per_repo_today[repo] = per_repo_today.get(repo, 0) + q

    for repo, minutes in per_repo_today.items():
        if minutes <= REPO_DAILY_LIMIT or repo not in by_name:
            continue
        for w in active_workflows(repo):
            disable(repo, w)
        log.append(f"CIRCUIT BREAKER {repo}: {minutes:.0f} min today > {REPO_DAILY_LIMIT}")
        if by_name[repo]["issues"]:
            open_issue_once(
                repo, f"breaker:{today}",
                f"[actions-guard] Workflows desactivados por consumo ({today})",
                f"Este repositorio consumió **{minutes:.0f} minutos** de Actions hoy; el límite "
                f"por repositorio es {REPO_DAILY_LIMIT}. El guardián desactivó todos sus "
                f"workflows para proteger el cupo compartido de la organización.\n\n"
                f"Revisa qué se ejecutó (pestaña Actions), corrígelo y pide al docente que "
                f"los reactive. Política: {POLICY_URL}")

    pct = 100 * total / QUOTA if QUOTA else 0
    top = sorted(per_repo.items(), key=lambda kv: -kv[1])[:10]
    rows = "\n".join(f"| `{r}` | {m:.0f} | {100 * m / QUOTA:.1f} % |" for r, m in top)
    warn_rows = "\n".join(f"| `{r}` | `{f}` | {rule} | {msg} |" for r, f, rule, msg in warnings_all)
    body = (
        f"**Minutos privados en {now:%Y-%m}:** {total:.0f} de {QUOTA} (**{pct:.1f} %**) · "
        f"actualizado {now:%Y-%m-%d %H:%M} UTC\n\n"
        f"| Repositorio | Minutos | % del cupo |\n|---|---:|---:|\n{rows or '| — | 0 | 0 % |'}\n\n"
        f"### Acciones de esta pasada\n" + ("\n".join(f"- {l}" for l in log) or "- Ninguna") +
        f"\n\n### Advertencias ({len(warnings_all)})\n"
        f"| Repositorio | Workflow | Regla | Detalle |\n|---|---|---|---|\n{warn_rows or '| — | — | — | — |'}\n\n"
        f"Política: {POLICY_URL}")
    crossed = [(lvl, f"@{NOTIFY} el consumo de Actions de {now:%Y-%m} cruzó el **{lvl} %** del cupo "
                     f"({total:.0f} de {QUOTA} minutos). Mayores consumidores: "
                     + ", ".join(f"`{r}` ({m:.0f})" for r, m in top[:3]))
               for lvl in LEVELS if pct >= lvl]
    upsert_tracking_issue(f"Consumo de GitHub Actions — {now:%Y-%m}", body, crossed)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(body + "\n")
    print(f"{'DRY RUN · ' if DRY else ''}{len(repos)} repos · private minutes {total:.0f}/{QUOTA} ({pct:.1f} %)")
    for l in log:
        print(l)
    print(f"{len(warnings_all)} warnings")
    for r, f, rule, msg in warnings_all:
        print(f"  {rule} {r}/{f}: {msg}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"::error::{e}")
        sys.exit(1)
