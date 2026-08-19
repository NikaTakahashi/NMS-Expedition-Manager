# 4 · Instalar y desinstalar

Esta es la parte que toca el **juego**. Todo aquí está diseñado para que lo
único irreversible sea *elegir jugar una expedición*; los ficheros siempre son
recuperables.

## El objetivo: el fichero de temporada vivo

El juego lee su expedición de un único fichero en su carpeta cache
por-usuario, llamado **`SEASON_DATA_CACHE_S<N>.json`**, donde `<N>` es el
número de temporada actual (esta biblioteca se generó para **S22**; el número
solo sube). El programa **nunca** hardcodea qué `<N>` está vivo: lo detecta.

- `season_files(cache)` — lista todos los `SEASON_DATA_CACHE_S<N>.json`
  presentes (insensible a mayúsculas), indexados por `<N>`.
- `current_cache_file(cache)` — el fichero que el juego **lee ahora mismo**:
  el de **mayor** `<N>` (las temporadas solo aumentan, gana el más nuevo). Si
  no hay ninguno, hace fallback al nombre histórico S22.

En Linux el fichero suele vivir en **minúsculas**
(`season_data_cache_s22.json`) aunque el nombre canónico del programa sea en
mayúsculas; `_resolve_cache_file()` encaja cualquier mayusculización para que
los backups/restores siempre lleguen al fichero que el juego usa de verdad en
sistemas de archivos sensibles a mayúsculas.

## Dónde se encuentra la cache (por plataforma)

`find_nms_cache_dirs()` sondea las localizaciones específicas del SO (ver
[Plataformas](08-plataformas.md) para la tabla completa):

- **Windows:** `%APPDATA%\HelloGames\NMS\*\cache`
- **macOS:** `~/Library/Application Support/HelloGames/NMS/cache`
- **Linux:** `<proton_prefix>/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS/*/cache`
  (el prefix viene de `config.txt` o de las localizaciones Steam estándar)

Si se encuentran **varias** carpetas cache y estás en modo interactivo, te
piden elegir una. Si no se encuentra ninguna, te dicen que ejecutes el juego
una vez (para crear la carpeta) y, en Linux, que configures el prefix.

## Instalar — paso a paso

`installer.install(exp_id, mode, difficulty, …)`:

1. **Resuelve el fichero de origen.** Normalmente el fichero de la biblioteca
   para `(exp_id, mode, difficulty)` vía el manifiesto. Si se pasa
   `source_file` (el flujo de personalización), se usa ese.
2. **Resuelve el objetivo** vivo (la temporada) en la cache elegida.
3. **Archiva ficheros de temporada vieja.** Cualquier
   `SEASON_DATA_CACHE_S<N>.json` que *no* sea el actual se **mueve** (no se
   borra) a la carpeta de backups, con el sufijo `_archived`. Mantiene la
   cache tan limpia como una limpieza a mano, sin perder nada.
4. **Hace backup del fichero actual.** Si existe, se copia a
   `backups/<nombre>_<timestamp>`.
5. **Copia el origen** como el fichero vivo.
6. **Graba el estado** en `state.json`: qué expedición/modo/dificultad está
   instalada, la carpeta cache, el fichero objetivo y la ruta del backup.

El backup con timestamp hace que *instalar* distintas expediciones una tras
otra nunca destruya un original anterior: cada instalación deja una copia
fechada.

## Desinstalar — restaurar

`installer.uninstall()`:

1. Lee el estado grabado. Si nada está instalado, es un no-op.
2. **Restaura el fichero vivo** desde su backup.
   - Si el fichero grabado aún existe → copia el backup encima.
   - Si el juego pasó a una **temporada más nueva** (el fichero grabado ya no
     existe y ahora está vivo un `<N>` mayor) → el fichero viejo ya está
     muerto para el juego, no hay *nada* que restaurar en el vivo; imprime una
     nota y **no** toca el fichero de la nueva temporada.
   - Si no existía backup (el fichero lo creó la instalación, no sobrescribió
     un original) → simplemente se elimina.
3. **Limpia el estado** de la instalación (los backups se conservan en disco).

Restaurar es **idempotente**: correr uninstall sin instalación no hace nada y
no da error.

## Los backups viven en la carpeta de estado

Los backups se guardan en la **carpeta de estado** por plataforma (no en la
carpeta del programa, no en la del juego):

```
<state_dir>/
├── state.json
├── custom/                 ← ficheros de personalización generados (ver Personalización)
└── backups/
    ├── SEASON_DATA_CACHE_S22.json_20260101_120000
    └── season_data_cache_s22.json_20260102_083000_archived
```

Esto mantiene los datos del usuario fuera de la carpeta del programa (que
podrías re-descargar/sustituir) y fuera del árbol del juego.

## ⚠ Pone Steam en Modo Offline

La causa más común de fallo **no** es un bug del programa: si Steam está
online, al lanzar NMS puede que Steam (o la comprobación online del juego)
**revierta el fichero cache**, borrando la expedición instalada. Antes de
jugar, pon Steam en **Modo Offline**. El diálogo de instalación siempre te lo
recuerda.

## Actualizaciones de temporada

Como el fichero vivo se resuelve como "el número de temporada mayor presente"
y el nombre del fichero de la biblioteca es una constante estable, **un salto
de temporada (S22 → S23, o S40) no requiere cambiar código**:

- **Instalar** apunta a sea cual sea el `S<N>` mayor presente, y archiva los
  anteriores.
- **Desinstalar** sabe que el fichero grabado puede ya no ser el vivo, y no
  pisa el fichero de una temporada más nueva.
- El fichero de la biblioteca conserva su nombre histórico `…_S22.JSON`; el
  instalador lo traduce a lo que ahora se llame el fichero vivo.

Así, tras una actualización del juego, el flujo es: lanza el juego una vez
(crea el fichero nuevo `S23`), e instala como siempre — el fichero viejo `S22`
se archiva y la expedición cae en el fichero vivo `S23`.

## Modos de fallo y seguridad

- **No se encontró cache** → la instalación se aborta *antes* de tocar
  fichero alguno.
- **Falta el origen** (la combinación no está en la biblioteca) → aborta con
  "ejecuta sync".
- **Copia interrumpida** → el backup del paso 4 ya existe, puedes restaurar;
  lo peor es re-instalar.
- **Nada se borra**, solo se mueve a `backups/`.
