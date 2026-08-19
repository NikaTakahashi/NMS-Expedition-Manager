# 7 · La CLI

La línea de comandos tiene **dos modos**:

- **Menú interactivo** — se corre *sin* argumentos (`./run.sh`).
- **Subcomandos** — se corre con un argumento (`./run.sh sync`,
  `./run.sh install …`).

Ambos envuelven las mismas funciones, así que lo que puedes hacer en el menú
lo puedes hacer en una línea, y viceversa.

## Lanzar

Lanzadores por plataforma (cada uno crea un virtualenv oculto en la primera
ejecución e instala `requirements.txt` — el usuario nunca toca pip):

| SO    | CLI                                            | GUI                                          |
|-------|-----------------------------------------------|----------------------------------------------|
| Linux | `./run.sh`                                     | `./run.sh gui` o `./run-gui.sh`              |
| macOS | `./run.sh` o doble clic en `run.command`       | `./run.sh gui` o `run-gui.command`           |
| Windows | doble clic en `run.bat` (o `run.bat` en terminal) | doble clic en `run-gui.bat`          |

## Menú interactivo

```
+====================================+
|           Expedition Manager       |
+====================================+
| 1) Synchronize expeditions         |
| 2) Install expedition              |
| 3) Uninstall expedition            |
| 4) List                            |
| 5) Configure                       |
| 6) Open graphical interface        |
| 0) Quit                            |
+====================================+
Option >
```

La opción **2** (install) está totalmente guiada si se corre desde el menú:
lista las 22 expediciones para que elijas el número, y luego pide

- **Version** `[o]riginal / [r]edx` (por defecto `o`);
- **Difficulty** `[d]efault / [e]asy / [h]ardcore` (por defecto `d`).

(Desde el menú no se puede pasar `--custom`; usa la forma de subcomando para
eso.)

## Subcomandos

### `sync`
```
./run.sh sync [--force] [--exp eNN]
```
- (sin flags) — bajar/actualizar lo que falte o haya cambiado.
- `--force` — re-descargar todas las fuentes en bruto y reescribir los 126.
- `--exp eNN` — solo las combinaciones de esa expedición.

La salida termina con `Synchronization complete: N downloaded/updated, M unchanged.`

### `install`
```
./run.sh install [--exp eNN] [--mode original|redux]
                 [--difficulty default|easy|hardcore]
                 [--custom "Prop=Value,Prop2=Value2,…"]
```
- Cualquiera de `--exp / --mode / --difficulty` omitido se **pregunta en
  interactivo** (con los mismos prompts `[o]riginal/[r]edx` y
  `[d]efault/[e]asy/[h]ardcore` del menú).
- `--mode` y `--difficulty` se dan en minúsculas y se normalizan a los
  nombres de carpeta (`Originals`/`Redux`, `Defaults`/`Easy`/`Hardcore`).
- `--custom` — el formulario de la web en la línea de comandos. Se parsea y
  **valida** (parámetros desconocidos / tipos malos / opciones malas → error +
  lista de ejemplos válidos, salida 1, no toca ficheros). Ver
  [Personalización](05-personalización.md).

Ejemplos:
```
./run.sh install --exp e14 --mode original --difficulty hardcore
./run.sh install --exp e01 --difficulty easy --custom "CarnageMode=true,StartingSuitSlots=24"
./run.sh install                    # totalmente guiado
```

### `uninstall`
```
./run.sh uninstall
```
Restaura el fichero cache original desde el último backup y limpia el estado
de la instalación. Es seguro correrlo sin nada instalado (no-op).

### `list`
```
./run.sh list
```
Imprime la ruta de la biblioteca, un listado por `Mode/Difficulty` (con un
marcador por cada expedición que tenga su `INSTRUCTIONS.md`), la instalación
actual y la configuración activa.

### `config`
```
./run.sh config
```
Editor interactivo de `config.txt`: muestra los valores actuales y te deja
poner `proton_prefix` (escribe `default` para la ruta Steam estándar) o
`library_path`.

### `gui`
```
./run.sh gui
```
Abre la GUI. Prioridad de backends:
1. **Qt6** (`gui_qt.py`, PyQt6 o PySide6) — Wayland nativo (xdg-shell) en
   Linux, sin X11; en una sesión Wayland el lanzador/`launch()` fija
   `QT_QPA_PLATFORM=wayland`.
2. **tkinter** (`gui.py`) — fallback X11/XWayland, solo si no hay ningún
   binding de Qt6 importable.

Si ninguno está disponible, imprime la pista de instalación exacta para tu
distro (`pacman -S python-pyqt6`, `apt install python3-pyqt6`,
`pip install PySide6`, o las pistas de tkinter) y avisa de que la CLI sigue
funcionando. Ambas importaciones son perezosas, así que una máquina sin
pantalla nunca rompe la CLI.

## Códigos de salida

Los comandos devuelven `0` en éxito y no-cero en fallo (p. ej. una instalación
fallida, un error de validación en `--custom`, una expedición desconocida o
una combinación faltante). Esto hace la CLI scriptable:

```bash
./run.sh sync || exit 1
./run.sh install --exp e05 --mode redux --difficulty easy
```

## De dónde sale el estado

La CLI lee/escribe el mismo `state.json` y `config.txt` que la GUI (ver
[Configuración y datos](09-configuración-y-datos.md)), así que las dos
interfaces son intercambiables — instalar en la GUI y desinstalar desde el
terminal, etc.
