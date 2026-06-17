"""
gui.py — Interface graphique Flet de WinGhost Monitor.

Barre de transport « magnéto » à boutons explicites :

  • 🔴 REC      lance l'enregistrement (rouge en attente, grisé + ● clignotant
                pendant l'enregistrement)
  • ⏹ STOP     arrête l'action en cours (grisé au repos, rouge dès qu'un
                enregistrement OU un rejeu OU le mode auto tourne)
  • ▶️ REPLAY   rejoue le scénario sélectionné
  • ⏱ AUTO     mode automatique : rejoue le scénario en boucle à intervalle
                régulier (30 min par défaut, cf. config.AUTO_REPLAY_INTERVAL_MIN)
  • 📊 RAPPORT KPI  (re)génère le dashboard HTML et l'ouvre dans le navigateur

Le journal « Replay live » décrit chaque action rejouée en langage clair et en
temps réel, avec son temps de réponse visuel et son statut. La liste des
scénarios (« sessions ») permet de sélectionner, renommer et supprimer.

Le rejeu, l'enregistrement et le mode auto tournent dans des threads dédiés afin
de ne jamais bloquer l'IHM ; l'arrêt est coopératif (threading.Event pour le
rejeu et l'auto, Recorder.stop() pour l'enregistrement).
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

import flet as ft

from version import __version__
from winmonitor import config

# Compat. : selon la version de Flet, les icônes sont exposées via `ft.Icons`
# (≥ 0.25) ou `ft.icons` (0.21–0.24).
_ICONS = getattr(ft, "Icons", None) or getattr(ft, "icons", None)


def _thin_border(color: str = "#DCE6EE"):
    """Bordure fine, tolérante aux variations d'API Flet (`ft.border.all` a
    disparu de certaines versions). Renvoie None si l'API n'existe pas."""
    for factory in (getattr(getattr(ft, "border", None), "all", None),
                    getattr(getattr(ft, "Border", None), "all", None)):
        if callable(factory):
            try:
                return factory(1, color)
            except Exception:
                pass
    return None

# ─── Palette CHU Toulouse (fond clair, lisible) ──────────────────────────────
_BLUE = "#0091CE"        # bleu institutionnel CHU
_BLUE_DARK = "#005B8F"
_GREEN = "#8BC53F"       # vert action
_RED = "#D64550"         # rouge action / alerte
_RED_DARK = "#8C1C24"
_AMBER = "#E8A33D"
_DARK = "#1E2A38"        # texte principal
_GREY = "#C2CCD4"        # bouton inactif/grisé
_GREY_TXT = "#7A8896"
_BG = "#FFFFFF"
_PANEL = "#F4F8FB"


def _resource(rel: str) -> str:
    """Chemin d'une ressource embarquée (PyInstaller `_MEIPASS`) ou du dépôt."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / rel
        if p.exists():
            return str(p)
    return str(Path(__file__).resolve().parent.parent / rel)


def _close_splash() -> None:
    """Ferme le splash PyInstaller dès que l'IHM est prête (no-op hors exe)."""
    try:
        import pyi_splash  # type: ignore

        pyi_splash.close()
    except Exception:
        pass


# ─── Descriptions humaines (journal « Replay live ») ──────────────────────────
def human_description(action, outcome) -> str:
    t = action.type
    coord = f"({outcome.x}, {outcome.y})" if outcome.x is not None else ""
    if t in ("click", "double_click", "right_click", "middle_click"):
        verb = {
            "click": "Clic", "double_click": "Double-clic",
            "right_click": "Clic droit", "middle_click": "Clic milieu",
        }[t]
        base = f"{verb} en {coord}"
    elif t == "text":
        base = f"Saisie clavier : « {action.text} »"
    elif t == "key":
        base = f"Touche « {action.key} »"
    elif t == "move":
        base = f"Déplacement de la souris vers {coord}"
    elif t == "scroll":
        base = f"Molette ({action.scroll_dy}) en {coord}"
    else:
        base = t
    anchor = "🔍" if outcome.anchored else "📌"
    return f"{base} — {outcome.response_ms:.0f} ms {anchor} [{outcome.status}]"


def _status_color(status: str) -> str:
    return {"ok": _GREEN, "fallback": _AMBER, "degraded": _AMBER,
            "timeout": _RED}.get(status, _DARK)


class MonitorGUI:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._recording = False
        self._replaying = False
        self._auto = False
        self._recorder = None
        self._rec_thread = None
        self._replay_thread = None
        self._auto_thread = None
        self._stop_event = threading.Event()
        self._auto_cancel = threading.Event()
        self._blink_on = False

        config.ensure_dirs()
        self._build()
        self._refresh_scenarios()
        _close_splash()

    # ─── Construction de l'IHM ────────────────────────────────────────────────
    def _build(self) -> None:
        p = self.page
        p.title = f"WinGhost Monitor v{__version__} — CHU Toulouse"
        p.padding = 16
        p.theme_mode = ft.ThemeMode.LIGHT          # fond clair lisible
        p.bgcolor = _BG
        try:
            p.window.width, p.window.height = 1000, 700
        except Exception:
            pass

        # En-tête : logo CHU + titre sur bandeau bleu.
        try:
            logo = ft.Image(src=_resource("assets/logo_chu.png"), height=40,
                            fit=ft.ImageFit.CONTAIN)
        except Exception:
            logo = ft.Container(width=0)
        header = ft.Container(
            content=ft.Row([
                ft.Row([logo, ft.Container(width=12),
                        ft.Column([
                            ft.Text("WinGhost Monitor", size=22,
                                    weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                            ft.Text("Supervision de la performance applicative — "
                                    "CHU Toulouse", size=12, color="#E6F4FB"),
                        ], spacing=0)],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text(f"v{__version__}", size=12, color="#E6F4FB"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=_BLUE, padding=14, border_radius=10,
        )

        # Barre de transport (boutons explicites REC / STOP / REPLAY / AUTO).
        self._rec_btn = ft.ElevatedButton(
            "🔴  REC", on_click=self._on_rec, height=64, expand=True)
        self._stop_btn = ft.ElevatedButton(
            "⏹  STOP", on_click=self._on_stop, height=64, expand=True)
        self._replay_btn = ft.ElevatedButton(
            "▶️  REPLAY", on_click=self._on_replay, height=64, expand=True)
        self._auto_btn = ft.ElevatedButton(
            "⏱  AUTO", on_click=self._on_auto, height=64, expand=True)
        transport = ft.Row(
            [self._rec_btn, self._stop_btn, self._replay_btn, self._auto_btn],
            spacing=10)

        self._report_btn = ft.ElevatedButton(
            "📊  RAPPORT KPI", on_click=self._on_report, bgcolor=_BLUE_DARK,
            color="#FFFFFF", height=44, expand=True)

        # Nom du scénario (pour l'enregistrement).
        self._name_field = ft.TextField(
            label="Nom du scénario à enregistrer", dense=True,
            hint_text="ex. ouverture_dossier_patient",
        )

        # Mode automatique : intervalle (minutes).
        self._interval_field = ft.TextField(
            label="Intervalle auto (min)", dense=True, width=160,
            value=str(config.AUTO_REPLAY_INTERVAL_MIN),
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        # Accordéon « Sessions » (scénarios) repliable.
        self._scen_open = True
        self._scen_toggle = ft.TextButton(
            "📂  Sessions enregistrées  ▲", on_click=self._toggle_scenarios)
        self._scen_radio = ft.RadioGroup(content=ft.Column([], tight=True),
                                         on_change=lambda e: None)
        self._scen_panel = ft.Container(content=self._scen_radio, visible=True)

        left = ft.Column([
            transport,
            ft.Divider(height=6, color="transparent"),
            ft.Row([self._report_btn]),
            ft.Divider(height=8, color="transparent"),
            self._name_field,
            ft.Row([self._interval_field]),
            ft.Divider(height=8, color="transparent"),
            self._scen_toggle,
            self._scen_panel,
        ], width=400, scroll=ft.ScrollMode.AUTO)

        # Journal « Replay live ».
        self._status = ft.Text("Prêt.", size=13, color=_DARK,
                               weight=ft.FontWeight.BOLD)
        self._live = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        right = ft.Column([
            ft.Text("Replay live", size=15, weight=ft.FontWeight.BOLD,
                    color=_DARK),
            self._status,
            ft.Container(content=self._live, expand=True, border_radius=8,
                         bgcolor=_PANEL, padding=10,
                         border=_thin_border()),
        ], expand=True)

        p.add(header, ft.Divider(height=10, color="transparent"),
              ft.Row([left, ft.VerticalDivider(width=16, color="transparent"),
                      right], expand=True))
        self._apply_buttons()

    # ─── État visuel des boutons (machine à états) ────────────────────────────
    def _apply_buttons(self) -> None:
        busy = self._recording or self._replaying or self._auto

        # REC : rouge en attente ; grisé pendant toute activité.
        if self._recording:
            dot = "🔴" if self._blink_on else "⚪"
            self._rec_btn.text = f"{dot}  REC…"
            self._rec_btn.bgcolor, self._rec_btn.color = _GREY, _GREY_TXT
            self._rec_btn.disabled = True
        else:
            self._rec_btn.text = "🔴  REC"
            if busy:
                self._rec_btn.bgcolor, self._rec_btn.color = _GREY, _GREY_TXT
                self._rec_btn.disabled = True
            else:
                self._rec_btn.bgcolor, self._rec_btn.color = _RED, "#FFFFFF"
                self._rec_btn.disabled = False

        # STOP : rouge dès qu'une activité tourne, sinon grisé/inactif.
        if busy:
            self._stop_btn.text = "⏹  STOP"
            self._stop_btn.bgcolor, self._stop_btn.color = _RED, "#FFFFFF"
            self._stop_btn.disabled = False
        else:
            self._stop_btn.text = "⏹  STOP"
            self._stop_btn.bgcolor, self._stop_btn.color = _GREY, _GREY_TXT
            self._stop_btn.disabled = True

        # REPLAY : vert disponible au repos ; grisé pendant l'activité.
        if self._replaying:
            self._replay_btn.text = "⏹  rejeu en cours"
            self._replay_btn.bgcolor, self._replay_btn.color = _GREY, _GREY_TXT
            self._replay_btn.disabled = True
        elif busy:
            self._replay_btn.text = "▶️  REPLAY"
            self._replay_btn.bgcolor, self._replay_btn.color = _GREY, _GREY_TXT
            self._replay_btn.disabled = True
        else:
            self._replay_btn.text = "▶️  REPLAY"
            self._replay_btn.bgcolor, self._replay_btn.color = _GREEN, _DARK
            self._replay_btn.disabled = False

        # AUTO : actif (vert) quand enclenché ; indisponible pendant un REC.
        if self._auto:
            self._auto_btn.text = "⏱  AUTO ● ON"
            self._auto_btn.bgcolor, self._auto_btn.color = _GREEN, _DARK
            self._auto_btn.disabled = False
        else:
            self._auto_btn.text = "⏱  AUTO"
            if self._recording:
                self._auto_btn.bgcolor, self._auto_btn.color = _GREY, _GREY_TXT
                self._auto_btn.disabled = True
            else:
                self._auto_btn.bgcolor, self._auto_btn.color = _BLUE, "#FFFFFF"
                self._auto_btn.disabled = False

        self._safe_update()

    def _safe_update(self) -> None:
        try:
            self.page.update()
        except Exception:
            pass

    # ─── Scénarios / sessions ─────────────────────────────────────────────────
    def _discover(self) -> list[str]:
        base = config.SCENARIOS_DIR
        if not base.exists():
            return []
        return sorted(d.name for d in base.iterdir()
                      if (d / "scenario.json").exists())

    def _refresh_scenarios(self) -> None:
        names = self._discover()
        rows: list = []
        for n in names:
            rows.append(ft.Row([
                ft.Radio(value=n, label=n, expand=True),
                ft.IconButton(icon=_ICONS.DRIVE_FILE_RENAME_OUTLINE,
                              tooltip="Renommer la session", icon_color=_BLUE,
                              on_click=lambda e, name=n: self._ask_rename(name)),
                ft.IconButton(icon=_ICONS.DELETE_OUTLINE,
                              tooltip="Supprimer la session", icon_color=_RED,
                              on_click=lambda e, name=n: self._ask_delete(name)),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
        self._scen_radio.content.controls = rows or [
            ft.Text("Aucune session enregistrée.", italic=True, color=_GREY_TXT)]
        if names and self._scen_radio.value not in names:
            self._scen_radio.value = names[0]
        elif not names:
            self._scen_radio.value = None
        self._safe_update()

    def _toggle_scenarios(self, _e) -> None:
        self._scen_open = not self._scen_open
        self._scen_panel.visible = self._scen_open
        self._scen_toggle.text = (
            f"📂  Sessions enregistrées  {'▲' if self._scen_open else '▼'}")
        self._safe_update()

    # ─── Dialogues (renommer / supprimer une session) ─────────────────────────
    def _open_dialog(self, dlg: ft.AlertDialog) -> None:
        # Flet ≥ 0.23 : page.open(dlg) ; antérieurs : page.dialog + open.
        opener = getattr(self.page, "open", None)
        if callable(opener):
            opener(dlg)
        else:
            self.page.dialog = dlg
            dlg.open = True
            self._safe_update()

    def _close_dialog(self, dlg: ft.AlertDialog) -> None:
        closer = getattr(self.page, "close", None)
        if callable(closer):
            closer(dlg)
        else:
            dlg.open = False
            self._safe_update()

    def _ask_rename(self, name: str) -> None:
        field = ft.TextField(label="Nouveau nom", value=name, autofocus=True)

        def do_rename(_e):
            from winmonitor.recorder.scenario import Scenario
            try:
                Scenario.rename(config.SCENARIOS_DIR, name, field.value or "")
                self._close_dialog(dlg)
                self._refresh_scenarios()
                self._set_status(f"Session renommée : « {name} » → "
                                 f"« {field.value} ».", _GREEN)
            except Exception as exc:
                field.error_text = str(exc)
                self._safe_update()

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Renommer la session"), content=field,
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("Renommer", on_click=do_rename, bgcolor=_BLUE,
                                  color="#FFFFFF"),
            ])
        self._open_dialog(dlg)

    def _ask_delete(self, name: str) -> None:
        def do_delete(_e):
            from winmonitor.recorder.scenario import Scenario
            try:
                Scenario.delete(config.SCENARIOS_DIR, name)
                self._close_dialog(dlg)
                self._refresh_scenarios()
                self._set_status(f"Session supprimée : « {name} ».", _AMBER)
            except Exception as exc:
                self._close_dialog(dlg)
                self._set_status(f"Erreur de suppression : {exc}", _RED)

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text("Supprimer la session"),
            content=ft.Text(f"Supprimer définitivement « {name} » et toutes "
                            f"ses ancres ? Cette action est irréversible."),
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("Supprimer", on_click=do_delete, bgcolor=_RED,
                                  color="#FFFFFF"),
            ])
        self._open_dialog(dlg)

    # ─── Journal ──────────────────────────────────────────────────────────────
    def _log(self, text: str, color: str = _DARK) -> None:
        self._live.controls.append(ft.Text(text, size=12, color=color,
                                           font_family="Consolas"))
        self._safe_update()

    def _set_status(self, text: str, color: str = _DARK) -> None:
        self._status.value = text
        self._status.color = color
        self._safe_update()

    # ─── Clignotement du point REC ────────────────────────────────────────────
    def _blink_worker(self) -> None:
        while self._recording:
            self._blink_on = not self._blink_on
            self._apply_buttons()
            time.sleep(0.5)
        self._blink_on = False
        self._apply_buttons()

    # ─── REC ──────────────────────────────────────────────────────────────────
    def _on_rec(self, _e) -> None:
        if not self._recording:
            self._start_recording()

    def _start_recording(self) -> None:
        if self._replaying or self._auto:
            self._set_status("Une autre opération tourne — arrêtez-la (STOP) "
                             "avant d'enregistrer.", _RED)
            return
        name = (self._name_field.value or "").strip()
        if not name:
            self._set_status("Saisissez un nom de scénario avant d'enregistrer.",
                             _RED)
            return

        from winmonitor.recorder.listener import Recorder

        self._recorder = Recorder(name)
        self._recording = True
        self._set_status(f"Enregistrement de « {name} » — agissez, "
                         f"puis ÉCHAP ou STOP.", _RED)
        self._apply_buttons()
        threading.Thread(target=self._blink_worker, daemon=True).start()

        def worker():
            try:
                self._recorder.start(config.SCENARIOS_DIR)   # bloque jusqu'à stop/ÉCHAP
                path = self._recorder.save(config.SCENARIOS_DIR)
                self._set_status(f"Scénario enregistré : {path.name}", _GREEN)
            except Exception as exc:                          # pragma: no cover
                self._set_status(f"Erreur d'enregistrement : {exc}", _RED)
            finally:
                self._recording = False
                self._apply_buttons()
                self._refresh_scenarios()

        self._rec_thread = threading.Thread(target=worker, daemon=True)
        self._rec_thread.start()
        self._safe_update()

    def _stop_recording(self) -> None:
        if self._recorder is not None:
            self._recorder.stop()

    # ─── STOP : arrête l'action courante (REC / REPLAY / AUTO) ─────────────────
    def _on_stop(self, _e) -> None:
        if self._auto:
            self._auto_off()
        if self._recording:
            self._set_status("Arrêt de l'enregistrement demandé…", _RED)
            self._stop_recording()
        if self._replaying:
            self._set_status("Arrêt du rejeu demandé…", _RED)
            self._stop_event.set()

    # ─── REPLAY ───────────────────────────────────────────────────────────────
    def _on_replay(self, _e) -> None:
        if self._replaying or self._recording or self._auto:
            return
        name = self._scen_radio.value
        if not name:
            self._set_status("Sélectionnez une session à rejouer.", _RED)
            return
        self._replay_thread = threading.Thread(
            target=self._replay_once, args=(name,), daemon=True)
        self._replay_thread.start()

    def _replay_once(self, name: str) -> None:
        """Rejoue une fois `name` (Couche 2) + mesure/persistance (Couche 3).

        Bloquant : appelé depuis un thread (REPLAY manuel ou cycle AUTO)."""
        from winmonitor.kpi.dashboard import build_dashboard
        from winmonitor.kpi.store import MetricsStore
        from winmonitor.recorder.scenario import Scenario
        from winmonitor.replayer.replayer import Replayer

        self._replaying = True
        self._stop_event = threading.Event()
        self._live.controls.clear()
        self._set_status(f"Rejeu de « {name} »…", _BLUE)
        self._apply_buttons()

        def on_action(action, outcome):
            self._log(human_description(action, outcome),
                      _status_color(outcome.status))

        try:
            folder = Scenario.folder_for(config.SCENARIOS_DIR, name)
            scenario = Scenario.load(folder)
            result = Replayer().run(scenario, folder, on_action=on_action,
                                    stop_event=self._stop_event)
            store = MetricsStore()
            store.insert_run(result)
            build_dashboard(store)
            total = result.total_response_ms
            self._set_status(
                f"Rejeu terminé [{result.status}] — {total:.0f} ms "
                f"sur {len(result.outcomes)} action(s).",
                _status_color(result.status))
        except Exception as exc:                              # pragma: no cover
            self._set_status(f"Erreur de rejeu : {exc}", _RED)
        finally:
            self._replaying = False
            self._apply_buttons()

    # ─── AUTO : rejeu en boucle à intervalle régulier (Couche 4) ──────────────
    def _on_auto(self, _e) -> None:
        if self._auto:
            self._auto_off()
        else:
            self._auto_on()

    def _interval_minutes(self) -> int:
        try:
            return max(1, int(self._interval_field.value or
                              config.AUTO_REPLAY_INTERVAL_MIN))
        except (TypeError, ValueError):
            return config.AUTO_REPLAY_INTERVAL_MIN

    def _auto_on(self) -> None:
        if self._recording:
            self._set_status("Enregistrement en cours — arrêtez-le d'abord.", _RED)
            return
        if not self._scen_radio.value:
            self._set_status("Sélectionnez une session pour le mode auto.", _RED)
            return
        self._auto = True
        self._auto_cancel = threading.Event()
        self._auto_thread = threading.Thread(target=self._auto_worker, daemon=True)
        self._auto_thread.start()
        self._apply_buttons()

    def _auto_off(self) -> None:
        self._auto = False
        self._auto_cancel.set()
        self._stop_event.set()       # interrompt un cycle de rejeu en cours
        self._apply_buttons()

    def _auto_worker(self) -> None:
        while not self._auto_cancel.is_set():
            name = self._scen_radio.value
            if name and not self._recording:
                self._replay_once(name)
            if self._auto_cancel.is_set():
                break
            mins = self._interval_minutes()
            self._set_status(
                f"Mode auto actif — prochain rejeu de « {name} » dans "
                f"{mins} min.", _BLUE)
            self._apply_buttons()
            if self._auto_cancel.wait(mins * 60):
                break
        self._set_status("Mode auto arrêté.", _DARK)
        self._apply_buttons()

    # ─── RAPPORT KPI ──────────────────────────────────────────────────────────
    def _on_report(self, _e) -> None:
        from winmonitor.kpi.dashboard import build_dashboard

        try:
            path = build_dashboard()
            webbrowser.open(Path(path).resolve().as_uri())
            self._set_status(f"Rapport KPI ouvert : {path}", _GREEN)
        except Exception as exc:                              # pragma: no cover
            self._set_status(f"Erreur rapport KPI : {exc}", _RED)


def main(page: ft.Page) -> None:
    MonitorGUI(page)


def run() -> None:
    """Lance l'application Flet (fenêtre desktop)."""
    ft.app(target=main)


if __name__ == "__main__":
    run()
