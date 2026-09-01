---
name: github-team-setup
description: Checklist paso a paso para crear un nuevo subteam en code-corhuila o code-sena con permisos correctos — repos, branches, GitHub Project, HUs, maintainer. Usar cuando se agrega un equipo nuevo a cualquier org académica.
---

# Setup de Nuevo Subteam — Checklist

Usar cuando el usuario pide agregar un equipo nuevo a code-corhuila, code-sena, o cualquier org académica.

## Datos que necesitas antes de empezar

- `{org}` — código de la org (ej: `code-corhuila`, `code-sena`)
- `{parent-team}` — slug del team padre (ej: `mobile-programming-2026-b`)
- `{team-slug}` — kebab-case único (ej: `uni-reserve`)
- `{project-name}` — nombre para el GitHub Project (ej: `Uni Reserve — Backlog`)
- `{docs-repo}` — slug del repo docs (ej: `uni-reserve-docs` o patrón del equipo)
- `{code-repo}` — slug del repo código (ej: `uni-reserve` o nombre del proyecto)
- `{username-maintainer}` — GitHub user del admin del equipo (declarado por ariel5253)
- `{miembros[]}` — lista de GitHub users del equipo

---

## Fase 1 — Crear el team

```bash
# Crear subteam bajo el parent
gh api --method POST orgs/{org}/teams \
  --field name="{nombre visible}" \
  --field slug="{team-slug}" \
  --field privacy=closed \
  --field parent_team_id=$(gh api orgs/{org}/teams/{parent-team} --jq '.id')
```

---

## Fase 2 — Crear repos

```bash
# Repo docs (solo rama main)
gh api --method POST orgs/{org}/repos \
  --field name="{docs-repo}" \
  --field private=true \
  --field auto_init=true

# Repo código (3 ramas: main + qa + develop)
gh api --method POST orgs/{org}/repos \
  --field name="{code-repo}" \
  --field private=true \
  --field auto_init=true

# Crear ramas develop y qa en el repo código
SHA=$(gh api repos/{org}/{code-repo}/git/refs/heads/main --jq '.object.sha')
gh api --method POST repos/{org}/{code-repo}/git/refs \
  --field ref="refs/heads/develop" --field sha="$SHA"
gh api --method POST repos/{org}/{code-repo}/git/refs \
  --field ref="refs/heads/qa" --field sha="$SHA"
```

---

## Fase 3 — Asignar permisos al team sobre sus repos

```bash
# Admin en repo docs
gh api --method PUT orgs/{org}/teams/{team-slug}/repos/{org}/{docs-repo} \
  --field permission=admin

# Admin en repo código
gh api --method PUT orgs/{org}/teams/{team-slug}/repos/{org}/{code-repo} \
  --field permission=admin
```

---

## Fase 4 — Crear GitHub Project y asignar team como admin

```bash
# Obtener org node_id
ORG_ID=$(gh api orgs/{org} --jq '.node_id')

# Crear proyecto
PROJECT=$(gh api graphql -f query="
mutation {
  createProjectV2(input: {
    ownerId: \"$ORG_ID\",
    title: \"{project-name}\"
  }) { projectV2 { id number } }
}")
PROJECT_ID=$(echo $PROJECT | jq -r '.data.createProjectV2.projectV2.id')

# Obtener team node_id
TEAM_ID=$(gh api orgs/{org}/teams/{team-slug} --jq '.node_id')

# Asignar team como admin del proyecto
gh api graphql -f query="
mutation {
  updateProjectV2Collaborators(input: {
    projectId: \"$PROJECT_ID\",
    collaborators: [{ teamId: \"$TEAM_ID\", role: ADMIN }]
  }) { collaborators { nodes { ... on Team { name } } } }
}"
```

---

## Fase 5 — Agregar miembros y maintainer

```bash
# Invitar miembros a la org si aún no son miembros
gh api --method PUT orgs/{org}/memberships/{username} --field role=member

# Agregar al team
gh api --method PUT orgs/{org}/teams/{team-slug}/memberships/{username} \
  --field role=member

# Asignar maintainer (admin del equipo) — declarado por ariel5253
gh api --method PUT orgs/{org}/teams/{team-slug}/memberships/{maintainer-username} \
  --field role=maintainer
```

---

## Fase 6 — Crear HUs iniciales (Epic 1)

```bash
# HU-01 y HU-02 en repo docs
gh api --method POST repos/{org}/{docs-repo}/issues \
  --field title="HU-01 — Selección de Stack Tecnológico" \
  --field body="{HU01_BODY}" \
  --field labels='["HU","Corte 1"]'

gh api --method POST repos/{org}/{docs-repo}/issues \
  --field title="HU-02 — Discovery del Proyecto" \
  --field body="{HU02_BODY}" \
  --field labels='["HU","Corte 1"]'

# HU-03 en repo código
gh api --method POST repos/{org}/{code-repo}/issues \
  --field title="HU-03 — MVP Corte 1" \
  --field body="{HU03_BODY}" \
  --field labels='["HU","Corte 1"]'

# Agregar issues al GitHub Project
# (usar addProjectV2ItemById con el node_id de cada issue)
```

---

## Verificación final

```bash
# Confirmar permisos del team sobre sus repos
gh api orgs/{org}/teams/{team-slug}/repos --jq '.[] | "\(.name): \(.role_name)"'

# Confirmar que el team NO tiene acceso a repos de otros equipos
# (la lista anterior debe mostrar solo {docs-repo} y {code-repo})

# Confirmar miembros del team
gh api orgs/{org}/teams/{team-slug}/members --jq '.[].login'
```

---

## Checklist rápido (marcar al completar)

- [ ] Team creado bajo el parent correcto
- [ ] Repo docs creado (solo rama `main`)
- [ ] Repo código creado con `main` + `qa` + `develop`
- [ ] Team tiene `admin` en repo docs
- [ ] Team tiene `admin` en repo código
- [ ] GitHub Project creado con nombre `{Nombre} — Backlog`
- [ ] Team tiene `admin` en el GitHub Project
- [ ] Miembros del equipo agregados al team
- [ ] Maintainer designado (role=maintainer)
- [ ] HU-01 y HU-02 creadas en docs, HU-03 en código
- [ ] Issues agregados al GitHub Project
- [ ] Verificación: el team NO tiene acceso a repos ajenos

---

## Notas importantes

- **Herencia de permisos:** si el parent team tiene permisos sobre algún repo, todos sus hijos lo heredan. Verificar que el parent NO tenga admin en repos compartidos — máximo `maintain`.
- **Repos docs:** solo rama `main` — sin develop ni qa.
- **Repos código:** siempre 3 ramas: `develop` (trabajo activo) → `qa` (testing) → `main` (entrega).
- **Entrega:** GitHub Release en el repo código + copia en `docs/05-release/`.
- **Admin individual:** ariel5253 declara un maintainer por team cuando lo informa — no agregarlo por defecto.
