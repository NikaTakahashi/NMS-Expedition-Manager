# 6 · La GUI

La GUI es una app **Qt6**. Usa **PyQt6** cuando está disponible (el
`python-pyqt6` de Arch se reutiliza directamente a través del venv) y
**PySide6** en caso contrario (`run.sh` lo instala en el venv
automáticamente) — ambos bindings comparten la misma API de Qt6 y el código
(`gui_qt.py`) funciona con cualquiera de los dos. En **Linux funciona sobre
Wayland nativo (xdg-shell)**: los lanzadores fijan `QT_QPA_PLATFORM=wayland`
en sesiones Wayland (y `gui_qt.launch()` lo refuerza como segunda línea de
defensa), así que la ventana es un cliente real de `xdg-shell` **sin
ningún X11 de por medio**. En Windows/macOS usa la integración de plataforma
nativa. Se conserva un fallback en tkinter (`gui.py`, X11) para sistemas
donde no se pueda instalar ningún binding de Qt6.

Tiene **tres pestañas** más un panel de log y una barra de estado, y comparte
al 100% su lógica con la CLI (los mismos módulos `sync`, `installer`,
`customize`, `config`), así que nada que pueda la GUI falta en la CLI, y
viceversa.

## Layout de la ventana

```
┌────────────────────────────────────────────────────────┐
│  [ Library | Install | Settings ]                      │
├────────────────────────────────────────────────────────┤
│                                                        │
│                        (cuerpo de la pestaña)          │
│                                                        │
├────────────────────────────────────────────────────────┤
│  Franja de Sync  [ Sync all ] [ Force resync ]  barra  │
├────────────────────────────────────────────────────────┤
│  Panel de log (coloreado: info / ok / error)          │
├────────────────────────────────────────────────────────┤
│  Barra de estado (estado de una línea)                │
└────────────────────────────────────────────────────────┘
```

- **Library / Install** hacen scroll vertical si la ventana es demasiado
  baja (la pestaña Install, con el formulario de 67 líneas, es la alta).
- El **panel de log** refleja todo lo que imprimiría la CLI, con colores.
- La **barra de estado** muestra el último estado de alto nivel.

## Las pestañas

### Library
- Una **tabla** con las 22 expediciones: id, nombre, modos disponibles
  (Original / Redux, con Redux atenuado cuando no existe, p. ej. e21/e22) y
  un **estado de descarga** por dificultad (p. ej. `D ✔ E ✔ H ✔`).
- Clic en una fila para inspeccionar; la vista es de solo lectura (la
  descarga ocurre en la franja de Sync, para que Library nunca bloquee la UI).
- **No** es una pestaña con canvas scrolleable: la tabla (un `Treeview`) tiene
  su propio scroll interno, así que el cuerpo de la pestaña no hace doble
  scroll.

### Install
De arriba abajo:
1. **Expedition** — desplegable (`eNN — Name`).
2. **Version** — Original / Redux (el botón Redux se desactiva si la
   expedición no tiene Redux).
3. **Difficulty** — Defaults / Easy / Hardcore. Cambiar cualquiera de (1–3)
   re-deriva la línea de estado *Downloaded ✓ / not downloaded* **y** recarga
   el formulario de personalización con el preset de la dificultad elegida.
4. **Customization** — el formulario de 67 parámetros (ver
   [Personalización](05-personalización.md)).
5. La **línea de estado de descarga**: verde *Downloaded ✓* si la combinación
   exacta `(exp, mode, difficulty)` está en la biblioteca; si no, un aviso en
   gris y el botón principal se convierte en **Download first** (bajar solo
   esa combinación) antes de volver a ser **Install**. Los ficheros
   *personalizados* no necesitan esto (se generan de las fuentes cacheadas).
6. **NMS cache folder** — autodetectado y pre-rellenado; **Re-detect**
   re-sondea; una línea en rojo avisa si no hay ninguno (con el remedio
   específico de la plataforma).
7. **Current installation** — qué está instalado, la cache objetivo, la ruta
   del backup y (si aplica) cuántos valores de personalización hay guardados.
8. **Install** / **Uninstall** — ambas piden confirmación; el diálogo de
   instalación repite la advertencia ⚠ *pone Steam en offline*.

### Settings
- **Proton prefix** (solo Linux) — la ruta del prefix para encontrar la
  cache; en Windows/macOS esta fila se sustituye por una nota gris con la ruta
  nativa del juego (ahí no hay Proton).
- **Library path** — dónde vive la biblioteca de 126 ficheros (por defecto la
  carpeta del programa).
- Botón **Restore defaults**.
- Guardar escribe `config.txt` (ver [Configuración y datos](09-configuración-y-datos.md)).

## Modelo de hilos (por qué la UI nunca se congela)

El hilo de la GUI es de un solo hilo, pero las descargas por red, la
generación de ficheros y las copias a disco son lentas. La GUI usa un patrón
estricto de **hilo de trabajo + cola**:

```
hilo principal (Qt)               hilo de trabajo (fondo)
─────────────────                 ─────────────────────────
  clic en Install  ──────────▶    ejecuta sync / generar / install
  QTimer(100 ms) poller ◀────     q.put(("log", level, msg))
  pinta los widgets desde la cola
```

Reglas que lo mantienen seguro:
- **Solo el hilo de la GUI toca widgets.** El worker nunca llama a ninguna
  API de Qt; solo empuja mensajes a un `queue.Queue`.
- **Un worker a la vez.** Una segunda acción mientras otro corre se ignora
  (el estado ocupado se muestra en el log).
- **Polling, no callbacks.** Un `QTimer` iniciado a 100 ms vacía la cola; el
  timer se **para en `closeEvent`** para que cerrar la ventana no deje un
  callback colgando. (Los workers son hilos daemon: mueren con el proceso.)
- **Los trabajos largos reportan progreso** (sync) por la misma cola,
  actualizando la barra de progreso sin bloquear.

## Comportamiento al arrancar

Al lanzarse, la app:
1. Carga el catálogo y el estado actual de la biblioteca (rápido, local).
2. **Autodetecta las carpetas cache de NMS** (un barrido local rápido) y
   pre-llena el combo de cache de la pestaña Install.
3. Si hay una expedición instalada, **pre-selecciona** (expedición, versión,
   dificultad) y **restaura los valores de personalización guardados** en el
   formulario.
4. Usa el estilo nativo de widgets de la plataforma (Breeze/Windows/macOS) y
   carga el icono de ventana desde `assets/ExpeditionManager.ico`.
5. Arranca el poller de la cola e instala el manejador de cierre limpio.

## Consciencia de plataforma en la GUI

`gui_qt.py` calcula `IS_LINUX` / `IS_WINDOWS` / `IS_MACOS` una vez y los usa
solo para **presentación** (qué fila de settings mostrar, qué texto de aviso,
fallbacks de icono/tema) y para seleccionar el plugin de plataforma
**Wayland** en sesiones Wayland. Toda la *lógica* se comparte. Ver
[Plataformas](08-plataformas.md).
