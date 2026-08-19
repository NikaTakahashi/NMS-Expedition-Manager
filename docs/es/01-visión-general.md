# 1 · Visión general

## Qué es la herramienta

Expedition Manager es un **gestor local y offline** de las *expediciones*
comunitarias de No Man's Sky. La web oficial de
[cwmonkey](https://cwmonkey.github.io/nms-expeditions/) permite personalizar y
descargar ficheros de expedición desde el navegador; este programa lleva la
misma capacidad a una aplicación de escritorio autónoma, con dos
interfaces (mismo conjunto de funciones):

- una **GUI** (Qt6 vía PyQt6/PySide6 — Wayland nativo en Linux) para uso
  por clic, y
- una **CLI** para scripting y para máquinas sin pantalla.

Hace tres cosas:

1. **Construir la biblioteca** — generar, para cada expedición y cada
   dificultad, el JSON exacto de la expedición (ver
   [La Biblioteca](02-la-biblioteca.md) y [Sincronización](03-sincronización.md)).
2. **Instalar** — copiar uno de esos ficheros en la carpeta cache del juego,
   con copia de seguridad del original (ver
   [Instalar y desinstalar](04-instalar-y-desinstalar.md)).
3. **Desinstalar** — restaurar el fichero original desde la copia.

## La idea central: offline + reproducible

Las expediciones online requieren que el juego se conecte a los servidores
comunitarios que las distribuyen. Las *offline* de este programa lo
sustituyen: el juego lee un fichero local de su propia carpeta cache y no
llama nunca a casa por datos de expedición.

Para construir ese fichero local, el programa **no hace scrapeo de la web**.
En cambio **reimplementa en Python el generador de la web**, usando los mismos
datos de origen que usa la web (el repositorio público
[cwmonkey/nms-expeditions](https://github.com/cwmonkey/nms-expeditions)).
Como sigue los mismos pasos, en el mismo orden, con las mismas reglas de
serialización, la salida es **byte-idéntica** a lo que entregaría la web
(los detalles de por qué es difícil la identidad byte a byte y cómo se logra
están en [Sincronización](03-sincronización.md)).

## Las tres capas de datos

```
 Repo de GitHub (cwmonkey/nms-expeditions)
        │  sources.py  ── descarga y cachea los ficheros en bruto
        ▼
 data/sources/        ← entradas en bruto cacheadas (yaml/json de parches)
        │  sync.py     ── base + preset + parches, JSON estilo JS
        ▼
 ExpeditionManagerLibrary/   ← 126 .JSON generados + manifest.json
        │  installer.py ── elegir uno, hacer backup del original, copiar
        ▼
 <NMS cache>/SEASON_DATA_CACHE_S<N>.json   ← lo que el juego lee de verdad
```

Cada flecha es un módulo distinto con una única responsabilidad. Cada etapa
puede correr por su lado (sync sin instalar, listar la biblioteca, etc.), y
ninguna etapa sorprende: lo que ves en la biblioteca es determinista a partir
del repo de arriba, y lo que ves en la cache del juego es exactamente un
fichero de la biblioteca (más tus personalizaciones opcionales).

## Invariantes que protege todo el diseño

Estas son las intocables. Si un cambio rompe alguna, es un bug:

1. **Identidad byte a byte de los ficheros estándar.** Un fichero generado
   *sin* personalizaciones debe ser igual bit a bit al que produce la web para
   la misma expedición/modo/dificultad. (Verificado por SHA-256 y a partir de
   los presets.)
2. **Reversibilidad.** Cada instalación deja una copia que, al desinstalar,
   devuelve la cache a sus bytes previos. Restaurar es idempotente.
3. **Ninguna mutación silenciosa de datos del usuario.** El fichero de cache
   del juego solo se toca *después* de escribir su copia; los ficheros de
   temporada vieja se *mueven* a la copia, nunca se borran.
4. **Reproducibilidad.** Dadas las mismas entradas, un sync produce los
   mismos hashes; un sync "sin cambios" no descarga nada.
5. **Temporadas a prueba de futuro.** Debe seguir funcionando al pasar de S22
   a S23 (o S40) sin cambiar código (ver
   [Instalar y desinstalar](04-instalar-y-desinstalar.md#actualizaciones-de-temporada)).

## ¿Por qué "expediciones offline"?

- **Sin red en el juego.** El juego funciona 100% offline; Steam debe estar en
  *Modo Offline* para que no sobrescriba la cache al lanzar.
- **Rejugable.** Puedes jugar cualquier expedición, en cualquier orden, para
  siempre, sin depender de que los servidores comunitarios estén arriba.
- **Auditable.** El fichero en tu cache es un JSON plano que puedes diffar,
  hacer hash y regenerar cuando quieras.

## Glosario

| Término | Significado |
|---------|-------------|
| **Expedición** | Una de las 22 expediciones comunitarias (`e01`…`e22`). |
| **Original** | La expedición tal y como se publicó (versión `r00`). |
| **Redux** | Un rework posterior (`r01`, `r02`, …). No todas tienen. |
| **Dificultad / preset** | *Defaults*, *Easy*, *Hardcore* — paquetes de valores. |
| **Preset** | El JSON de sobreescrituras que aplica una dificultad (Hardcore pone *Permadeath*). |
| **Parche** | Una sobreescritura data-driven (retiradas, apéndices, sustituciones) que la web aplica por versión o global. |
| **Biblioteca** | La carpeta local con los 126 ficheros + `manifest.json`. |
| **Fichero cache** | `SEASON_DATA_CACHE_S<N>.json` en la cache — lo que lee el juego. |
| **Sync** | (Re)generar la biblioteca a partir de las fuentes. |
