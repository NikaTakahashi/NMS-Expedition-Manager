# Expedition Manager — Documentación (español)

Esta carpeta documenta **cómo funciona el programa**: sus funciones, el flujo
de datos y el razonamiento detrás de las decisiones de diseño. No es un
tutorial para jugar; es una referencia para quien quiera entender, modificar o
fiarse de la herramienta.

> **¿Solo quieres usar la herramienta?** Con la [README](../../README.md) y la
> sección *Guide* que incluye basta. Empieza aquí si quieres saber *por qué*
> las cosas son como son y *qué* hace cada pieza.

---

## Contenido

| # | Documento | Qué cubre |
|---|-----------|-----------|
| 1 | [Visión general](01-visión-general.md) | Qué es, el panorama global y las invariantes que protege |
| 2 | [La Biblioteca](02-la-biblioteca.md) | La biblioteca de 126 ficheros, el manifiesto, nombres y estructura |
| 3 | [Sincronización](03-sincronización.md) | Cómo se generan ficheros byte-idénticos a los de la web oficial |
| 4 | [Instalar y desinstalar](04-instalar-y-desinstalar.md) | Copias de seguridad, el fichero de temporada vivo, modo offline |
| 5 | [Personalización](05-personalización.md) | El formulario de 67 parámetros, los presets y la generación al vuelo |
| 6 | [La GUI](06-gui.md) | Las tres pestañas, el modelo de hilos y la cola |
| 7 | [La CLI](07-cli.md) | Todos los comandos, flags y el menú interactivo |
| 8 | [Plataformas](08-plataformas.md) | Windows / macOS / Linux: rutas, lanzadores y comportamiento por SO |
| 9 | [Configuración y datos](09-configuración-y-datos.md) | `config.txt`, `state.json`, cachés y dónde vive todo |

La **versión principal (en inglés)** está en [`../README.md`](../README.md).

---

## Resumen en un párrafo

El programa es un **cliente local y offline** para las expediciones de
No Man's Sky. *Descarga y reproduce, fichero a fichero, el JSON exacto que
genera la web oficial de*
[cwmonkey](https://cwmonkey.github.io/nms-expeditions/)*, los guarda en una
biblioteca local y permite* **instalar** alguno en la carpeta cache del juego
(con copia de seguridad del original) o **desinstalarlo** (restaurando el
original). Todo es reversible, verificable por SHA-256 y funciona sin que el
juego necesite estar online.

La garantía más importante que protege todo el diseño:

> **Una instalación sin modificaciones es byte a byte idéntica al fichero que
> descargaría la web oficial.**

Sobre esa garantía se construye todo lo demás (sync, presets,
personalización, manejo de temporadas).

---

> Si te resulta útil este proyecto, puedes apoyar su desarrollo en
> **[ko-fi.com/nikatakahashi](https://ko-fi.com/nikatakahashi)**. ☕
