# 2 · La Biblioteca

La **biblioteca** es el almacén en disco de cada fichero de expedición
generado. Vive por defecto en `ExpeditionManagerLibrary/` dentro de la
carpeta del programa (cámbiase con `library_path` en `config.txt`, ver
[Configuración y datos](09-configuración-y-datos.md)).

## Tamaño y forma

La biblioteca contiene **126 ficheros**:

```
22 expediciones × {Original, Redux} × {Defaults, Easy, Hardcore}
```

menos las combinaciones que no existen. En concreto, por carpeta:

| Modo \ Dificultad | Defaults | Easy | Hardcore | Total |
|-------------------|:--------:|:----:|:--------:|:-----:|
| **Originals**     | 22       | 22   | 22       | 66    |
| **Redux**         | 20       | 20   | 20       | 60    |
| **Total**         | 42       | 42   | 42       | **126** |

Redux suma 20 porque dos expediciones **no tienen versión Redux**
(`e21 Remnant` y `e22 Swarm` son solo Original).

## Estructura de directorios

```
ExpeditionManagerLibrary/
├── manifest.json
├── Originals/
│   ├── Defaults/
│   │   ├── 01_Pioneers/SEASON_DATA_CACHE_S22.JSON
│   │   ├── 02_Beachhead/SEASON_DATA_CACHE_S22.JSON
│   │   └── …  (22 carpetas)
│   ├── Easy/
│   └── Hardcore/
└── Redux/
    ├── Defaults/
    ├── Easy/
    └── Hardcore/
```

Dos reglas de nombre que conviene conocer:

- La **dificultad** es la carpeta *intermedia* y el **modo** (Originals/Redux)
  la de arriba. Así, `Originals/Easy/01_Pioneers/…` es "Pioneers, versión
  original, preset Easy".
- Cada carpeta de expedición se llama **`NN_Name`** (p. ej. `01_Pioneers`),
  derivada del nombre humano sustituyendo todo carácter no alfanumérico por
  `_`. *No* es el id interno `e01`. El id interno solo se usa en la clave del
  manifiesto y en los ids de versión `eNNrNN`.

Todos los ficheros hoja se llaman **`SEASON_DATA_CACHE_S22.JSON`** — el nombre
histórico de S22. Ese nombre se conserva por estabilidad; el fichero *vivo*
del juego puede llamarse con una temporada más nueva, y el instalador traduce
entre ambos (ver [Instalar y desinstalar](04-instalar-y-desinstalar.md#actualizaciones-de-temporada)).

## El manifiesto

`manifest.json` es un mapa plano con **126 claves**, una por fichero
generado:

```jsonc
{
  "e01/Originals/Defaults": {
    "exp_id": "e01",
    "name": "01: Pioneers",
    "version_id": "e01r00",
    "mode": "Originals",
    "difficulty": "Defaults",
    "sha256": "a5e1e1ff91b39869a1febadbc7cfe8e5da58052b29e8b482455d7d3cabd40cff"
  },
  "e01/Originals/Easy": { … },
  "e01/Redux/Defaults":  { … },
  "e01/Redux/Easy":      { … }
}
```

- **Formato de la clave:** `<exp_id>/<Mode>/<Difficulty>` — p. ej.
  `e05/Redux/Hardcore`. Es la dirección canónica de un fichero.
- **`sha256`** es el hash del JSON generado *tal cual se escribe a disco*. Es
  la fuente de verdad de "¿está este fichero al día?": el sync lo usa para
  saltarse los ficheros cuyo contenido no ha cambiado (ver
  [Sincronización](03-sincronización.md)).
- **`version_id`** (`eNNrNN`) registra qué versión del catálogo se usó
  (la original `r00`, o el último redux `r01`/`r02`/…).

El manifiesto es lo que lee la **pestaña Library de la GUI** y el comando
**`list` de la CLI** para informar del estado de descarga/verificación, y lo
que consulta el instalador para localizar el fichero de una
`(exp_id, mode, difficulty)` elegida.

## El catálogo (de dónde sale la lista de expediciones)

La *lista* de expediciones, sus nombres, sus versiones (original vs redux) y
sus referencias a parches por versión/global, todo viene del
`_data/expeditions.yml` de arriba (ver [Sincronización](03-sincronización.md)).
`catalog.py` parsea ese YAML en objetos `Expedition`, cada uno con:

- `id` (`e01`), `name` (`01: Pioneers`), `description`, `notice`
- `versions` — lista de `Version`; `Version.original` es la no-redux,
  `Version.latest_redux` el redux más reciente (o `None`)
- `exp_patches` — referencias a parches a nivel de expedición

La biblioteca es por tanto una *materialización* del catálogo: por cada
expedición, por cada modo disponible (Original + Redux si existe), por cada
una de las tres dificultades, un fichero generado.

## Verificar un fichero

Como cada fichero se dirige por hash, "¿está mi biblioteca intacta?" es una
línea: recomputar el SHA-256 de cada `SEASON_DATA_CACHE_S22.JSON` y
compararlo con el `sha256` del manifiesto. Una discrepancia significa que el
fichero se editó o se escribió a medias. (Un resync *forzado* lo reescribe
todo y refresca los hashes; un sync normal deja intactos los que coinciden.)
