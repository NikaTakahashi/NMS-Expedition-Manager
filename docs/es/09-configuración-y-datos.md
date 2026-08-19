# 9 · Configuración y datos

Dónde vive todo y qué significa cada fichero.

## Mapa de ficheros

```
<carpeta del programa>/                   (p. ej. ~/Descargas/Expedition Manager)
├── expedition_manager/                  ← código fuente (el paquete Python)
├── assets/                              ← Logo.jpeg + ExpeditionManager.ico
├── ExpeditionManagerLibrary/            ← la biblioteca de 126 ficheros + manifest.json (gitignored, generada)
├── data/sources/                        ← entradas en bruto cacheadas del repo de GitHub (gitignored)
├── run.sh / run-gui.sh / run.bat / …    ← lanzadores (ver Plataformas)
└── *.example                            ← plantillas de referencia (config.txt.example, overrides.json.example)

<carpeta de estado>/                     (por usuario y por SO; ver abajo)
├── config.txt                           ← configuración del usuario (KEY=VALUE)
├── overrides.json                       ← SOBREESCRITURAS PERSONALES OPCIONALES
├── state.json                           ← instalación actual + cache + backup
├── custom/                              ← ficheros de personalización generados
└── backups/                             ← originales + temporadas archivadas
```

La carpeta del programa contiene **solo código, recursos y lanzadores** —
nada personal. Todo lo que es tuyo (config, overrides, estado, backups)
vive en la carpeta de estado:

| SO | Carpeta de estado |
|---|---|
| Linux | `~/.local/share/expedition-manager/` |
| Windows | `%LOCALAPPDATA%\expedition-manager\` |
| macOS | `~/Library/Application Support/expedition-manager/` |

> **Migración:** las versiones anteriores guardaban `config.txt` y
> `overrides.json` en la carpeta del programa. En el primer uso tras
> actualizar, ambos se **mueven** automáticamente a la carpeta de estado
> (idempotente; nada se copia dos veces ni se pierde).

## `config.txt`

Un fichero diminuto `KEY=VALUE`, en la carpeta de estado, creado
automáticamente en el primer uso si falta (nunca se sobreescribe una vez
existe, así que el usuario es su propietario). Dos claves:

| Clave | Significado | Defecto |
|-------|-------------|---------|
| `proton_prefix` | Ruta del prefix Proton para encontrar la cache (Linux). **Vacío = sondear** las localizaciones Steam estándar. | `""` |
| `library_path` | Dónde vive la biblioteca. | `<carpeta del programa>/ExpeditionManagerLibrary` |

- Es texto plano: edítalo a mano o con `./run.sh config`.
- `save_config()` **conserva las claves que el usuario añadió a mano** (las
  añade al final del fichero), así que extender la configuración no se
  pisa.
- Un `config.json` legacy (en el directorio de configuración XDG) y un
  `config.txt` legacy en la raíz (versiones antiguas) se **migra una vez**
  a la `config.txt` de la carpeta de estado si existen, por compatibilidad.

## `state.json`

El registro *en ejecución* de qué está instalado y dónde. Lo escriben
install/uninstall. Contenido típico con una expedición activa:

```jsonc
{
  "installed": {
    "exp_id": "e05",
    "mode": "Redux",
    "difficulty": "Hardcore",
    "custom": { "CarnageMode": "true", "…": "…" }   // solo si hay personalización
  },
  "cache_dir":    "<…>/NMS/<steamid>/cache",
  "target_cache": "<…>/cache/SEASON_DATA_CACHE_S22.JSON",
  "backup_cache": "<carpeta de estado>/backups/SEASON_DATA_CACHE_S22.json_20260101_120000"
}
```

- `installed.custom` guarda el conjunto *completo* de valores que se
  instalaron (preset + ajustes del usuario) para que la GUI pueda
  re-llenar su formulario en el siguiente arranque.
- Las claves `installed`, `cache_dir`, `backup_cache`, `target_cache` se
  quitan al desinstalar (los *ficheros* de `backups/` se conservan en disco).
- Un `{}` vacío (o el fichero ausente) significa "nada instalado".

## `overrides.json` (opcional)

Reglas de casa personales, en la **carpeta de estado**, aplicadas en
**sync**, al *final* del pipeline, a las combinaciones que encajen.
Formato:

```jsonc
{
  "e05/Redux/Hardcore": {
    "alguna/ruta/en/el/json": "valor",
    "paraQuitar/ruta": "[[removed]]",
    "paraAnadir/ruta": "[[append]] extra"
  }
}
```

Usa el mismo lenguaje de sobreescrituras que los parches de arriba (ver
[Personalización](05-personalización.md#relación-con-overridesjson) para la
diferencia con el formulario `--custom` por instalación).

## `data/sources/`

La **caché de los ficheros en bruto** de arriba (el `expeditions.yml`, los
JSON base por versión, los YAML de parches, los JSON de preset,
`customizations.yml`, …). Un sync normal lee de aquí sin red; un **force
resync** los vuelve a obtener. Es seguro borrarla (se volverá a descargar),
pero haz que el siguiente sync necesite red.

## `manifest.json`

El índice de 126 entradas con hashes de la biblioteca (ver
[La Biblioteca](02-la-biblioteca.md)). Se regenera en cada sync; el SHA-256
por fichero es la fuente de verdad de "¿al día?".

## Backups y la regla de "nada se borra"

Cada instalación:
- **copia** el fichero vivo actual a `backups/<nombre>_<timestamp>`, y
- **mueve** cualquier fichero vivo de *temporada anterior* a
  `backups/…_<timestamp>_archived`.

Así `backups/` es un archivo en crecimiento, de solo-apéndice, de todo lo que
el programa ha desplazado. Es seguro podar entradas viejas a mano si quieres
ahorrar espacio — el *último* backup de una instalación activa lo referencia
`state.json` y hay que conservarlo mientras esa instalación esté en pie.

## Reproducibilidad y qué hacer backup

- La **biblioteca** y **`data/sources`** son totalmente regenerables desde
  el repo de arriba (basta un force sync).
- Tu **carpeta de estado** entera es tuya — contiene `config.txt`,
  `overrides.json`, los backups y (sobre todo) tu *cache original* del
  juego. Hazle backup si la instalación te importa: si la borras, uninstall
  no podrá restaurar la cache intacta.
