---
name: github-org-permissions
description: Modelo completo de permisos en GitHub para code-corhuila, code-sena y cualquier org académica de ariel5253. Regla de oro, jerarquía de teams, herencia, y comandos exactos para cada operación.
---

# Modelo de Permisos GitHub — ariel5253

## Regla de oro

```
ariel5253 (Owner)
  └── organización (org owner)
        └── team / materia
              └── subteam → [repos-propios + project-propio]
```

**Admin fluye solo hacia abajo y dentro del scope. Nunca hacia arriba ni hacia los lados.**

- Un subteam solo tiene admin sobre sus repos y su GitHub Project.
- Un team maintainer puede gestionar su team sin escalar a la org.
- Nadie puede tocar repos o projects de otro scope.

---

## Roles de org

| Rol | Puede hacer |
|-----|-------------|
| Owner (ariel5253) | Todo — billing, members, teams, repos |
| Member | Solo lo que el team le da; no puede cambiar org settings |

Asignar owner a alguien más solo si es absolutamente necesario (ej: jesusgonzalezcorhuila en code-corhuila).

---

## Niveles de permiso en repos

| Nivel | Descripción |
|-------|-------------|
| read | Ver/clonar |
| triage | Gestionar issues/PRs sin push |
| write (push) | Push a ramas no protegidas |
| maintain | Push + merge PRs + editar topics; SIN cambiar settings críticos ni gestionar acceso |
| admin | Todo incluyendo settings, branch protection, agregar colaboradores |

**Regla:** los subteams deben tener `admin` en sus propios repos. Los parent teams que agrupan subteams deben tener como máximo `maintain` en repos compartidos (ej: g1/g2 en sistemas distribuidos).

---

## Herencia de permisos en teams

**PROBLEMA CLAVE:** los child teams heredan los permisos del parent. Si el parent tiene `admin` en un repo, todos sus hijos también lo tienen aunque el hijo tenga un nivel menor asignado directamente — GitHub no permite reducir permisos heredados desde el hijo.

**Solución correcta:** el parent team NUNCA debe tener `admin` en repos que no sean de scope común. Usar `maintain` como máximo en repos compartidos.

Para verificar si un equipo tiene permisos heredados:
```bash
gh api orgs/{org}/teams/{team-slug}/repos --paginate --jq '.[] | "\(.name): \(.role_name)"'
```

---

## Team maintainer (admin de equipo)

Un team maintainer puede:
- Agregar/quitar miembros al team
- Los miembros nuevos reciben automáticamente los permisos del team
- Editar nombre y descripción del team
- Ver todos los repos del team

Un team maintainer NO puede:
- Tocar parent teams ni la org
- Dar acceso a repos fuera de su scope
- Crear nuevos teams

**Asignar maintainer:**
```bash
gh api --method PUT orgs/{org}/teams/{team-slug}/memberships/{username} \
  --field role=maintainer
```

**Verificar maintainers actuales:**
```bash
gh api orgs/{org}/teams/{team-slug}/members --jq '.[] | "\(.login): maintainer=\(.role)"'
# (la API de members no muestra role directamente; usar memberships endpoint)
gh api orgs/{org}/teams/{team-slug}/memberships/{username} --jq '.role'
```

---

## GitHub Projects v2

Los GitHub Projects son INDEPENDIENTES de los repos — son de la org, no del repo. Un subteam necesita:
1. Un proyecto creado en la org
2. Ese team asignado como collaborator con role ADMIN en el proyecto

Con admin en el project, el equipo puede:
- Agregar/mover/eliminar items (issues, HUs, PRs)
- Crear y editar campos, vistas, filtros
- Renombrar el proyecto
- Agregar otros collaborators a su propio project

**Crear proyecto (GraphQL):**
```bash
gh api graphql -f query='
mutation {
  createProjectV2(input: {
    ownerId: "{org-node-id}",
    title: "{Nombre — Backlog}"
  }) { projectV2 { id number title } }
}'
```

**Asignar team como admin del proyecto (GraphQL):**
```bash
gh api graphql -f query='
mutation {
  updateProjectV2Collaborators(input: {
    projectId: "{project-node-id}",
    collaborators: [{ teamId: "{team-node-id}", role: ADMIN }]
  }) { collaborators { nodes { ... on Team { name } } } }
}'
```

**Obtener node_id de un team:**
```bash
gh api orgs/{org}/teams/{team-slug} --jq '.node_id'
```

**Obtener node_id de la org:**
```bash
gh api orgs/{org} --jq '.node_id'
```

---

## Permisos de repo para un team

**Asignar permiso:**
```bash
gh api --method PUT orgs/{org}/teams/{team-slug}/repos/{org}/{repo} \
  --field permission={read|write|maintain|admin}
```

**Quitar acceso directo (NO elimina herencia del parent):**
```bash
gh api --method DELETE orgs/{org}/teams/{team-slug}/repos/{org}/{repo}
```

**Listar repos de un team con su nivel:**
```bash
gh api orgs/{org}/teams/{team-slug}/repos --paginate \
  --jq '.[] | "\(.name): \(.role_name)"'
```

---

## Orgs principales y sus IDs

| Org | node_id | Rol ariel5253 | Plan |
|-----|---------|---------------|------|
| code-corhuila | (ver `gh api orgs/code-corhuila --jq .node_id`) | Owner | Team |
| code-sena | O_kgDOCG6DOw | Owner | Team |

---

## Estructura actual — code-corhuila

- **Sistemas Distribuidos 2026-B**: `distributed-systems-2026-b` (parent) → `team-1-2026-b` (10 subteams) + `team-2-2026-b` (8 subteams)
  - Parent tiene `maintain` (NO admin) en `sistemas-distribuidos-2026-b-g1` y `g2`
  - Cada subteam tiene `admin` en sus repos propios + `admin` en su GitHub Project ✅
- **Mobile Programming 2026-B**: `mobile-programming-2026-b` (parent) → 8 subteams
  - Cada subteam tiene `admin` en sus repos propios + `admin` en su GitHub Project ✅

## Estructura actual — code-sena

- **ADSO-3145556**: parent sin repos → 10 subteams con repos propios + admin ✅ | sin GitHub Projects ⚠️
- **ADSO-3239137**: parent sin repos → 4 subteams con repos propios + admin ✅ | sin GitHub Projects ⚠️
- **ADSO-3239188**: parent sin repos → 10 subteams con repos propios + admin ✅ | sin GitHub Projects ⚠️
- **design-software**: 41 repos con admin → hereda a design-software-develop y design-software-qa (equipos de rol, no de proyecto)
