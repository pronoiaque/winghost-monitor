# Changelog — WinGhost Monitor

Toutes les modifications notables sont documentées ici.
Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) — versionnage [SemVer](https://semver.org/lang/fr/).

> **Note de fork.** WinGhost Monitor est une refonte de WinGhost RPA (v6.x). Le
> changelog du monolithe historique reste consultable sur la branche `main`.

---

## [0.3.0] — 2026-06-16

### Ajouté

- **IHM — boutons de transport explicites** (`gui.py`) : **REC**, **STOP**,
  **REPLAY**, **AUTO**, **RAPPORT KPI** (au lieu des 3 boutons à bascule). États
  colorés conformes à la demande :
  - en attente : **REC rouge**, **STOP grisé** ;
  - pendant l'enregistrement : **REC grisé + ● clignotant**, **STOP rouge** ;
  - pendant le rejeu : **REC grisé**, **STOP rouge**.
  Le bouton **STOP** interrompt l'action en cours (enregistrement, rejeu ou auto).
- **Mode automatique** (bouton **⏱ AUTO**) : rejoue la session sélectionnée **en
  boucle à intervalle régulier** (champ « Intervalle auto », **30 min** par
  défaut via `config.AUTO_REPLAY_INTERVAL_MIN`, surchargé par
  `WINMONITOR_AUTO_INTERVAL_MIN`). Branche la Couche 4 (scheduler) sur l'IHM et
  répond à la spec « tourner toutes les 30 min ».
- **Gestion des sessions** : chaque scénario peut être **renommé** (✏️) ou
  **supprimé** (🗑️) depuis l'IHM. Nouvelles API `Scenario.rename()`,
  `Scenario.delete()`, `Scenario.sanitize_name()`.
- **Splash de chargement** (PyInstaller `Splash`, logo CHU) affiché dès la 1re
  seconde du lancement de `winmonitor.exe` ; fermé par `gui.run()` (`pyi_splash`)
  dès que la fenêtre est prête.
- **Logo CHU** embarqué dans le binaire (`assets/logo_chu.png`) et affiché dans
  l'en-tête (résolution via `sys._MEIPASS`).

### Modifié

- **IHM — thème clair lisible** : `ThemeMode.LIGHT` + fond blanc et palette CHU
  Toulouse (corrige le fond sombre illisible).
- Bouton **RAPPORT** renommé **« RAPPORT KPI »**.
- Compatibilité icônes Flet (`ft.Icons` ≥ 0.25 / `ft.icons` 0.21–0.24).

### Note d'architecture

- Les **Couches 3 (KPI Collector, `winmonitor/kpi/`)** et **4 (Scheduler,
  `winmonitor/scheduler/`)** existaient déjà côté code ; cette version les
  **expose dans l'IHM** (RAPPORT KPI = couche 3, mode AUTO = couche 4).

## [0.2.3] — 2026-06-16

### Corrigé — Binaire Windows : client desktop Flet manquant

- **`requirements-build.txt`** : ajout de `flet-desktop>=0.21.0`. Depuis Flet
  ≥ 0.21 le client desktop est un package SÉPARÉ ; sans lui, `winmonitor.exe`
  plantait au lancement (`ModuleNotFoundError: flet_desktop`, puis tentative de
  `pip install` impossible dans un exe figé).
- **`winghost-monitor.spec`** : la collecte de `flet_desktop` n'est plus avalée
  silencieusement (`try/except`) — le build échoue désormais franchement si le
  client desktop est absent, pour ne plus jamais livrer un binaire cassé.

## [0.2.2] — 2026-06-16

### Ajouté — Release à la demande (sans push de tag)

- **`build-windows.yml`** : entrée `workflow_dispatch` `release`. Quand elle est
  cochée (*Run workflow*), l'action `softprops/action-gh-release` crée
  elle-même le tag `vX.Y.Z` (lu dans `version.py`) côté GitHub via le
  `GITHUB_TOKEN`, puis publie la Release avec `winmonitor.exe`. Permet de
  publier une Release sans aucun `git push` de tag.
- Étape `Lire la version applicative` exposant `version.__version__` au job.

## [0.2.1] — 2026-06-16

### Ajouté — Build du binaire Windows (CI)

- **`.github/workflows/build-windows.yml`** : workflow GitHub Actions sur
  `windows-latest` qui compile `winmonitor.exe` (PyInstaller, depuis
  `winghost-monitor.spec`). PyInstaller ne cross-compilant pas, le build doit
  tourner sur un runner Windows.
  - garde-fou de cohérence des versions (`tools/check_version.py`) avant build ;
  - smoke-test `winmonitor.exe --version` après compilation ;
  - exe **publié en artefact** à chaque push (onglet *Actions*) ;
  - exe **attaché en Release** sur tag `v*`.

---

## [0.2.0] — 2026-06-16

### Ajouté — Interface graphique Flet (logique « magnéto » v6.6.0)

- **`winmonitor/gui.py`** : nouvelle IHM **Flet** reprenant la logique des boutons
  de la v6.6.0 :
  - **🔴 REC** bascule en **« ⏹ STOP REC »** (rouge) pendant l'enregistrement
  - **▶️ REPLAY** bascule en **« ⏹ STOP »** (rouge) pendant le rejeu, puis revient
  - **📝 RAPPORT** (re)génère le dashboard et l'ouvre dans le navigateur
- **Journal « Replay live »** : chaque action rejouée décrite en langage clair et
  en temps réel (*Clic en (x, y)*, *Saisie clavier : « … »*, *Touche « enter »*,
  *Déplacement vers (x, y)*) avec temps de réponse visuel, icône d'ancrage
  (🔍 template / 📌 absolu) et statut coloré (vert/orange/rouge)
- **Accordéon « Scénarios »** repliable (sélection du scénario à rejouer)
- Enregistrement et rejeu exécutés dans des **threads** dédiés ; arrêt coopératif
  (`threading.Event` pour le rejeu, `Recorder.stop()` pour l'enregistrement)

### Modifié

- **`replayer.run()`** accepte désormais `on_action` (callback de progression) et
  `stop_event` (arrêt propre entre deux actions) — utilisés par l'IHM
- **CLI** : sous-commande **`gui`** ajoutée ; **sans argument, l'application ouvre
  la GUI** (corrige le « double-clic → fenêtre noire puis rien »)
- **`winghost-monitor.spec`** : Flet embarqué (`collect_all`), exe **fenêtré**
  (`console=False`, plus de console DOS)
- `flet>=0.21.0` ajouté aux dépendances (exécution et build)

---

## [0.1.1] — 2026-06-15

### Ajouté — Build Windows (exécutable mono-fichier)

- **`winghost-monitor.spec`** : recette PyInstaller produisant `dist/winmonitor.exe`,
  la CLI packagée. OpenCV est désormais **embarqué** (ancrage visuel obligatoire,
  contrairement au build « léger » v6.x) via `opencv-python-headless`
- **`run_winmonitor.py`** : point d'entrée packagé (tire `winmonitor` + `version.py`)
- **`.github/workflows/build-windows.yml`** : build sur `windows-latest` à chaque
  push (`main`, `redesign/**`) et à la demande ; **Release** attachée sur tag `v*` ;
  smoke test `winmonitor.exe --version`
- **`requirements-build.txt`** : dépendances de packaging (toutes les couches +
  `pyinstaller`)

---

## [0.1.0] — 2026-06-15

### Ajouté — Refonte complète « table rase » en 4 couches

Nouvelle architecture orientée **supervision de performance applicative**,
calquée sur le diagramme de conception. Le code monolithique v6.x (Tkinter,
recorder/replayer/locator/scheduler dispersés) est retiré de cette branche.

#### 🏗️ Couche 1 — Recorder (`winmonitor/recorder/`)
- `listener.py` : hooks **pynput** souris + clavier ; les frappes imprimables
  sont regroupées en saisies texte, les touches spéciales restent distinctes
- `screenshot.py` : capture rapide **MSS** (repli Pillow), renvoyée en image
  OpenCV (BGR) — pixels homogènes entre enregistrement et chrono
- `scenario.py` : modèle JSON `Scenario`/`Action`/`Anchor` (tempo + ancre visuelle)

#### 🎯 Couche 2 — Replayer (`winmonitor/replayer/`)
- `anchor.py` : ancrage visuel **OpenCV `matchTemplate`** multi-échelle (TM_CCOEFF_NORMED)
- `dpi.py` : adaptateur **DPI/RDP** (facteur d'échelle + échelles de recherche centrées)
- `injector.py` : injection **chemin rapide** — `SendInput` Windows (clavier en
  `KEYEVENTF_UNICODE`, indépendant AZERTY/QWERTY), **sans délai artificiel**
  (corrige l'« hésitation » clavier de la v6.x) ; repli `pyautogui` unique
- `replayer.py` : orchestration **retry + timeout + fallback** (coordonnées mises
  à l'échelle + screenshot de diagnostic si l'ancrage échoue)

#### 📊 Couche 3 — KPI Collector (`winmonitor/kpi/`)
- `chrono.py` : **chronomètre visuel** `t_action → écran stable` — la mesure ne
  dépend plus de la vitesse d'injection des entrées
- `store.py` : **SQLite** horodaté UTC (tables `runs` + `action_metrics`),
  plage horaire dérivée
- `baseline.py` : médiane / p95 par scénario et par plage + détection de régression
- `dashboard.py` : **tableau de bord HTML autonome** (Chart.js, repli SVG si
  hors-ligne) ; `fetch_chartjs.py` pour un déploiement 100 % hors-ligne

#### ⏰ Scheduler (`winmonitor/scheduler/`)
- `runner.py` : **APScheduler** — un déclenchement par scénario et par plage horaire
- `report.py` : **rapport quotidien** agrégé (HTML + Markdown)

#### 🧰 Outillage
- CLI unique `winmonitor` (record / replay / list / schedule / dashboard / report / fetch-chartjs)
- Test de fumée de la chaîne KPI sans IHM (`tests/test_smoke.py`)
- `version.py` source unique ; CI de cohérence de version conservée
