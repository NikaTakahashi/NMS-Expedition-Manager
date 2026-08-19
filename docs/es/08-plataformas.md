# 8 · Plataformas

El programa funciona en **Windows, macOS y Linux** con la misma GUI y la misma
CLI. Toda la *lógica* es independiente de la plataforma (`pathlib` +
biblioteca estándar pura); solo unos pocos detalles de **presentación** y de
**localización** difieren por SO.

## Localizaciones por plataforma

| | **Windows** | **macOS** | **Linux** |
|---|---|---|---|
| **Cache del juego** | `%APPDATA%\HelloGames\NMS\*\cache` | `~/Library/Application Support/HelloGames/NMS/cache` | `<prefix>/drive_c/users/steamuser/AppData/Roaming/HelloGames/NMS/*/cache` |
| **Carpeta de estado** (`state.json`, `backups/`, `custom/`) | `%LOCALAPPDATA%\expedition-manager` | `~/Library/Application Support/expedition-manager` | `$XDG_DATA_HOME/expedition-manager` (~=`~/.local/share/…`) |
| **`config.txt`** | en la carpeta de estado | en la carpeta de estado | en la carpeta de estado |
| **Biblioteca** | carpeta del programa (defecto) | carpeta del programa (defecto) | carpeta del programa (defecto) |

Notas:

- **Fallback de estado en macOS:** si `~/Library/Application Support/expedition-manager`
  no existe pero hay un legacy `~/.local/share/expedition-manager`, se usa la
  ruta legacy (compatibilidad hacia atrás).
- **Solo la biblioteca** queda en la *carpeta del programa* (se genera ahí y
  está gitignored). `config.txt`, el `overrides.json` personal, el estado y
  los backups van todos a la localización de datos-de-usuario (carpeta de
  estado) de cada SO, de modo que la carpeta del programa no contiene nada
  específico de la máquina.
- Las versiones anteriores guardaban `config.txt` / `overrides.json` en la
  carpeta del programa; en el primer uso tras actualizar se **mueven** a la
  carpeta de estado automáticamente.

## Cómo se encuentra la cache

`find_nms_cache_dirs()` ramifica según el SO:

- **Windows / macOS** — el juego guarda datos nativamente (sin Proton), así
  que se sondea la carpeta de datos por-usuario estándar. Windows puede dar
  **dos** caches (una por-SteamID y una `DefaultUser`); el instalador ofrece
  la elección si hay varias.
- **Linux** — NMS corre bajo **Proton**, así que la cache vive *dentro* del
  árbol de Windows-falso del prefix de Wine. El prefix viene de
  `proton_prefix` en `config.txt`, o se sondan las localizaciones Steam
  estándar. La ruta dentro del prefix va en **minúsculas** en una instalación
  normal (y puede usar `Users/SteamUser` en Steam Deck); la búsqueda maneja
  ambos casos.

Si no se encuentra ninguna, el remedio es específico del SO (ejecuta el juego
una vez para crear la carpeta; en Linux además configura el prefix).

## Lanzadores (y la regla de "nunca toques pip")

Al usuario nunca se le pide correr `pip`. Cada lanzador da bootstrap a un
virtualenv oculto (`.venv`) en la primera ejecución:

- **`run.sh` / `run-gui.sh`** (Linux/macOS, bash) — la CLI y la GUI.
- **`run.command` / `run-gui.command`** (macOS) — doble-clicables en Finder
  (abren un Terminal automáticamente).
- **`run.bat` / `run-gui.bat`** (Windows) — doble-clicables en Explorer; la
  comprobación de hash del bootstrap usa `Get-FileHash -Algorithm MD5` de
  PowerShell (sin herramientas externas). Los `.bat` se guardan con finales
  de línea **CRLF**.

`requirements.txt` se mantiene mínimo: solo **`requests`** y **`PyYAML`**. La
dependencia Qt6 de la GUI se gestiona *por separado* de las deps de núcleo:

- **Linux** — el venv se crea con `--system-site-packages`, así que un
  binding de Qt6 proporcionado por el SO (p. ej. `python-pyqt6` en Arch) se
  **reutiliza tal cual**, sin descargas. Si no hay ninguno visible, `run.sh`
  instala **PySide6** en el venv la primera vez que se pide la GUI. En
  sesiones Wayland el lanzador también exporta **`QT_QPA_PLATFORM=wayland`**,
  forzando el cliente nativo `xdg-shell` (sin X11); `gui_qt.launch()` refuerza
  lo mismo como segunda línea de defensa.
- **Windows / macOS** — el venv es aislado, así que `run.bat` / `run.sh`
  instalan **PySide6** en el venv en el primer lanzamiento de la GUI
  (descarga única; licencia LGPL, wheels oficiales para cada plataforma).
- Si no se puede usar ningún binding de Qt6, la GUI cae a **tkinter**
  (X11 en Linux; los instaladores de Windows/macOS traen Tk por defecto).

## Lanzadores de escritorio (Linux) e icono de la aplicación

El repositorio **no incluye a propósito ningún fichero `.desktop`**: son
específicos de cada máquina (rutas absolutas hardcodeadas), así que no
pertenecen a un repositorio compartido. Si quieres un lanzador para el
visor de ficheros / menú de aplicaciones, crea tu propio
`expedition-manager.desktop` (p. ej. en `~/.local/share/applications/`)
apuntando a `run-gui.sh`, con `Exec=`/`WorkingDirectory=` **entre comillas**
(especificación freedesktop: la clave es `WorkingDirectory=`, no `Path=`) y
`StartupWMClass=expedition-manager` (el app-id de la app Qt, para que el
panel muestre el icono correcto y agrupe las ventanas).

> El icono de la aplicación es **`assets/ExpeditionManager.ico`** (un icono
> MS de 256×256; el logo usado en los README es `assets/Logo.jpeg`). Qt6
> carga el `.ico` de forma nativa en **todas** las plataformas, así que la
> ventana de la GUI lleva siempre el icono correcto. Para el visor de
> ficheros / menú de aplicaciones de Linux, registra los PNG del icono en el
> tema **hicolor** (`~/.local/share/icons/hicolor/<tamaño>/apps/
> expedition-manager.png`) — KDE ignora las rutas absolutas de icono local
> en los ficheros `.desktop`.

## Diferencias de comportamiento por SO (todas cosméticas)

| Aspecto | Linux | Windows / macOS |
|---|---|---|
| Pestaña Settings, fila *Proton prefix* | mostrada (editable) | oculta; sustituida por una nota gris con la ruta nativa del juego |
| Aviso "no se encontró cache" | "ejecuta el juego una vez bajo Proton y configura el prefix" | "ejecuta el juego una vez para que cree su carpeta de datos" |
| Protocolo de plataforma de la GUI | **Wayland (xdg-shell)** en sesiones Wayland; X11 vía el plugin `xcb` en Xorg | windowing nativo de Windows / macOS |
| Icono de ventana | `.ico` cargado por Qt + tema hicolor para el gestor de ficheros | `.ico` cargado por Qt (todas las plataformas) |

## Probar entre plataformas sin el hardware

Las rutas no-Linux se ejercitan mediante *simulación* en la suite de pruebas:
las ramas de descubrimiento de cache se conducen con un `$HOME`/`APPDATA` y un
prefix falsos, y se instala/desinstala un fichero cache fake de punta a
punta. En la máquina real, la regresión de Linux (prefix Proton real, cache
real, restauración byte-idéntica) es la que garantiza que la lógica compartida
sigue en pie.
