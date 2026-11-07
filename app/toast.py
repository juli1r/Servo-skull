"""Notification Windows (toast natif) à chaque capture, sans nouvelle dépendance pip : le XML
du template est poussé via un appel `powershell.exe` en sous-processus, sous l'identité
PowerShell elle-même (ce qui évite d'avoir à enregistrer Servo-Skull comme application Windows
juste pour avoir le droit d'afficher un toast — limitation des exe non empaquetés)."""
import subprocess
import sys

_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_xml(title: str, message: str) -> str:
    return (f'<toast><visual><binding template="ToastGeneric">'
            f'<text>{_esc(title)}</text><text>{_esc(message)}</text>'
            f'</binding></visual></toast>')


def show(title: str, message: str) -> None:
    """Non bloquant : lance le toast dans un processus à part et ne lève jamais d'exception
    (une notification manquée ne doit jamais interrompre une capture)."""
    if sys.platform != "win32":
        return
    xml = build_xml(title, message)
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f"$x.LoadXml('{xml}'); "
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_AUMID}')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
