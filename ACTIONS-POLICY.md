# Política de uso de GitHub Actions — code-corhuila

Todos los repositorios **privados** de la organización comparten un solo cupo de
**3.000 minutos de Actions al mes**. Cuando se agota, GitHub deja de iniciar jobs en
**todos** los repositorios privados, de todos los equipos y de todos los cursos, hasta
el primer día del mes siguiente. El job aparece fallido con el mensaje *"recent
account payments have failed or your spending limit needs to be increased"* y cero
pasos ejecutados.

Ya pasó una vez: en septiembre de 2026, un workflow con `cron` cada 30 minutos,
copiado en 15 repositorios, gastó el cupo del mes en cuatro días y dejó sin CI al
resto de la organización.

Esta política evita que se repita. Un guardián automático la hace cumplir cada hora.

## Reglas

| Regla | Qué se exige | Por qué |
|---|---|---|
| **R1** | **Prohibidos** los disparadores `schedule` y `workflow_run` en repositorios privados | Un `cron` cada 30 minutos son unos 1.440 minutos al mes **por repositorio**, aunque nadie trabaje |
| **R2** | `push` siempre con filtro de ramas (`branches: [main, develop]`) o de etiquetas | Sin filtro, cada push a cualquier rama personal lanza el CI |
| **R3** | Todo job declara `timeout-minutes`, **máximo 15** | Sin él, un job colgado corre 360 minutos |
| **R4** | El CI de pull request declara `concurrency` con `cancel-in-progress: true` | Cada commit nuevo cancela la corrida anterior, que ya no sirve |
| **R5** | Nada de "monitoreo 24/7", bucles de espera, `sleep`, ni integraciones con servicios externos (Trello, APIs de modelos, bots) desde Actions sin autorización escrita del docente | Actions es para verificar el código del PR, no para operar servicios |
| **R6** | Filtros `paths` / `paths-ignore` cuando el cambio no afecta lo que el CI verifica | Un cambio en un `.md` no necesita compilar el servicio |

Los disparadores permitidos son `pull_request`, `push` filtrado (R2), `workflow_dispatch`
e `issues`, este último solo para la sincronización del tablero que instala el docente.

## Un CI que cumple

```yaml
name: CI

on:
  pull_request:
    branches: [develop, main]
  push:
    branches: [develop, main]
    paths-ignore: ["**/*.md", "docs/**"]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      # instalar dependencias con caché, compilar y probar
```

## Qué hace el guardián

Corre cada hora desde el repositorio público `code-corhuila/.github`, cuyas
ejecuciones no gastan el cupo.

1. **Desactiva** todo workflow de un repositorio privado que viole **R1** y abre un
   issue en ese repositorio explicando por qué.
2. **Cortacircuito:** si un repositorio privado consume más de **60 minutos en un
   día**, desactiva **todos** sus workflows y abre un issue.
3. Publica el consumo del mes en un issue del repositorio `.github` y avisa al docente
   al cruzar el 50 %, el 75 % y el 90 % del cupo.
4. Lista como **advertencias** las violaciones de R2, R3 y R4, que aparecen en el
   issue de consumo.

## Cómo reactivar un workflow desactivado

1. Corrígelo en un PR: quita el disparador prohibido o la causa del consumo.
2. Cuando el PR esté integrado, pide al docente que reactive el workflow.

Reactivarlo sin corregirlo no sirve: el guardián lo vuelve a desactivar en la
siguiente pasada. La reincidencia se trata según la norma de cada curso.
