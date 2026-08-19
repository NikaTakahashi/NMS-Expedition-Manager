# 5 · Personalización

Más allá de las tres dificultades estándar (Defaults / Easy / Hardcore), una
expedición puede afinarse parámetro a parámetro — exactamente lo que hace el
formulario de la web oficial. Este programa reproduce ese formulario y el
mismo comportamiento de "aplicar mis valores encima de la dificultad", tanto
en la GUI como en la CLI.

## El espacio de parámetros

El conjunto de parámetros ajustables lo define arriba en
`_data/customizations.yml`: **67 parámetros** en dos grupos.

- **General** (46) — reglas de juego: modo de supervivencia, carnage,
  recursos, facción (p. ej. Swarm / community-team), fecha de fin, etc.
- **Difficulty Minimums** (21) — valores mínimos de la escala de dificultad.

Cada parámetro tiene un `type` (bool / int / float / str / seed / enum), una
lista opcional `options` (para desplegables), un nombre `display`, una
`description` y a veces una `warning`. Algunos son *anidados* (un `subprop`
bajo una sección `parent`), lo que importa porque el valor debe caer en el
lugar correcto del JSON — el generador usa el prop map para ello.

## Los presets

- **Defaults** = *sin* sobreescrituras (el fichero estándar).
- **Easy** y **Hardcore** = un paquete fijo de **25** valores de parámetro
  cada uno (obtenidos de los JSON de preset de arriba). Hardcore es el preset
  *Permadeath*: pone `DifficultySettingPreset = "Permadeath"` (colocado por el
  prop map en la sección correcta del JSON), más las protecciones de
  sistema-inicio `BlockStormsAtStart` y
  `BlockAggressiveSentinelsInStartSystem`, el preset de juego Hard Mode y los
  mínimos de dificultad.

Un preset es simplemente un mapa plano de `prop → valor`. La personalización
de un usuario también es un mapa plano. La única diferencia entre "instalar
Easy" e "instalar Easy con mis ajustes" es **qué mapa plano se aplica** en la
etapa de preset del pipeline.

## Cómo se construye un fichero personalizado

La decisión de diseño clave: **los valores del usuario se aplican en la
*misma* etapa que el preset de dificultad** — es decir, como
`difficulty_overrides` en el generador. Un fichero personalizado pasa por el
*siguiente* pipeline que uno estándar; solo cambia el mapa de sobreescrituras:

```
JSON base
  → aplicar (preset ∪ valores-usuario)      ← misma etapa, mapa combinado
  → aplicar parches de versión
  → aplicar parches globales
  → serializar (estilo JS)
```

Consecuencia directa: **si el usuario no cambia nada, el mapa aplicado es
igual al preset plano, y la salida es byte-idéntica al fichero pre-construido
de la biblioteca.** La personalización es un superconjunto puro del
comportamiento estándar — nunca puede cambiar lo que produce una instalación
sin cambios.

`customize.install_source_from_flat(exp_id, mode, difficulty, flat)` es el
punto de decisión:

- **`flat == preset`** (sin cambios del usuario) → devuelve `None`: usar el
  fichero pre-construido de la biblioteca (rápido, verificado por hash).
- **`flat != preset`** (el usuario tocó algo) → **genera** el fichero al
  vuelo desde las fuentes cacheadas, lo escribe en
  `<state_dir>/custom/<expid>_<Mode>_<Difficulty>.json` y devuelve esa ruta.
  No necesita red (las fuentes ya están cacheadas) y no se añade nada a la
  biblioteca — el fichero custom vive en la carpeta de estado.

## En la GUI

El frame **Customization** de la pestaña Install es el formulario de la web,
1:1:

- Un **desplazable por parámetro** (67 en total), agrupado bajo *General* y
  *Difficulty Minimums*.
  - Parámetros con `options` → desplegable readonly con los textos.
  - Parámetros bool → `true` / `false`.
  - Números / seeds → texto editable.
  - El valor *`(game default)`* significa "dejarlo intacto".
- **Load selected mode** — rellena el formulario entero con el preset de la
  dificultad actual. **Reset all** — pone todos los parámetros a
  `(game default)`.
- **Hacer clic en un parámetro** → muestra abajo su descripción (y su
  advertencia ⚠, si la tiene).
- **Línea de estado** — cuenta cuántos parámetros difieren del preset del
  modo:
  - `0` → "No changes — the pre-built file will be installed".
  - `N` → "N parameter(s) changed vs \<mode\> — the file will be generated at
    install time".
- Cambiar **dificultad / versión / expedición** recarga el formulario con el
  preset de ese modo (el formulario refleja siempre la dificultad elegida).

Al instalar con cambios, el conjunto completo de valores resultantes se
**guarda con la instalación** en `state.json` (`installed.custom`), de modo
que al reabrir la GUI se restauran los valores exactos con los que instalaste.

## En la CLI

La misma capacidad sin GUI:

```
./run.sh install --exp e01 --difficulty easy \
    --custom "CarnageMode=true,StartingSuitSlots=24"
```

`--custom` toma una cadena `Prop=Value,Prop2=Value2,…`. Se parsea
(`parse_custom_spec`), se **valida** contra la especificación (parámetros
desconocidos, tipos malos, opciones fuera de rango → mensaje con ejemplos
válidos, salida 1, no toca ficheros), se combina sobre el preset de la
dificultad y se genera el fichero igual que en la GUI. Esto hace la
personalización **scriptable y repetible**: el mismo comando reproduce el
mismo fichero.

## Relación con `overrides.json`

No confundas las dos:

| | `--custom` / formulario GUI | `overrides.json` |
|---|---|---|
| Alcance | **Una instalación** (una expedición/modo/dificultad) | **Toda la biblioteca** (cualquier combinación) |
| Dónde se guarda | `state.json` (`installed.custom`) | un fichero en la carpeta del programa |
| Cuándo se aplica | Etapa de preset, solo para ese fichero | Etapa *final*, en sync, para las combinaciones que encajen |
| ¿Cambia los hashes de la biblioteca? | No (el fichero custom va aparte) | Sí (los ficheros personalizados ya no encajan con el hash estándar) |
| Para qué | "Quiero *esta* partida ajustada" | "Quiero *mis* reglas de casa metidas en la biblioteca" |

`overrides.json` usa el mismo lenguaje de sobreescrituras que los parches de
arriba (retiradas/apéndices/…) y se aplica después de todo, así puede
codificar lo que el formulario por instalación no puede (p. ej. un
ajuste global a todas las expediciones).

## Seguridad

- Los ficheros custom solo se **generan**; los ficheros pre-construidos de la
  biblioteca nunca se modifican con la personalización.
- La generación usa el *mismo* serializador byte-idéntico, así un fichero
  custom es un fichero de expedición fiel — el JSON normal del juego más tus
  valores.
- Una cadena `--custom` mala **falla rápido** (error de validación, salida
  no-nula) y no toca ningún fichero.
