# Crée les raccourcis Servo-Skull (Bureau + menu Démarrer) avec la bonne icône ET le même
# identifiant d'application (AppUserModelID) que la fenêtre de l'overlay. C'est ce qui permet à
# Windows d'afficher l'icône Servo-Skull dans la barre des tâches et d'épingler correctement.
param([string]$Root, [string]$AppId = "Servo-Skull.Overlay")
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices; using System.Text;
[ComImport, Guid("00021401-0000-0000-C000-000000000046")] class CShellLink {}
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
interface IShellLinkW {
  void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr p, int fl);
  void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
  void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder n, int c);
  void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string n);
  void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder d, int c);
  void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string d);
  void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder a, int c);
  void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
  void GetHotkey(out short h); void SetHotkey(short h); void GetShowCmd(out int s); void SetShowCmd(int s);
  void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int c, out int i);
  void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string p, int i);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string p, int r);
  void Resolve(IntPtr h, int f); void SetPath([MarshalAs(UnmanagedType.LPWStr)] string f);
}
[StructLayout(LayoutKind.Sequential, Pack = 4)] public struct PKEY { public Guid fmtid; public uint pid; }
[StructLayout(LayoutKind.Explicit)] public struct PVAR { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; [FieldOffset(16)] public IntPtr pad; }
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
interface IPropertyStore { void GetCount(out uint c); void GetAt(uint i, out PKEY k); void GetValue(ref PKEY k, out PVAR v); void SetValue(ref PKEY k, ref PVAR v); void Commit(); }
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("0000010b-0000-0000-C000-000000000046")]
interface IPersistFile { void GetClassID(out Guid g); [PreserveSig] int IsDirty(); void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint m);
  void Save([MarshalAs(UnmanagedType.LPWStr)] string f, bool r); void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f); }
public static class ServoSkullLnk {
  public static void Make(string lnk, string target, string args, string wd, string icon, string appId, string desc) {
    var l = (IShellLinkW)new CShellLink();
    l.SetPath(target); l.SetArguments(args); l.SetWorkingDirectory(wd); l.SetIconLocation(icon, 0); l.SetDescription(desc);
    var ps = (IPropertyStore)l;
    var k = new PKEY { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 }; // System.AppUserModel.ID
    var v = new PVAR { vt = 31, p = Marshal.StringToCoTaskMemUni(appId) };                      // VT_LPWSTR
    ps.SetValue(ref k, ref v); ps.Commit();
    ((IPersistFile)l).Save(lnk, true);
  }
}
"@
$Root = (Resolve-Path $Root).Path
$py = Join-Path $Root ".venv\Scripts\pythonw.exe"
$main = Join-Path $Root "app\main.py"
$ico = Join-Path $Root "app\assets\servo-skull.ico"
$desc = "Servo-Skull : capture et film de tes parties 40K sur TTS"
$targets = @(
  (Join-Path ([Environment]::GetFolderPath("Desktop")) "Servo-Skull.lnk"),
  (Join-Path ([Environment]::GetFolderPath("Programs")) "Servo-Skull.lnk")
)
foreach ($t in $targets) {
  [ServoSkullLnk]::Make($t, $py, "`"$main`"", $Root, $ico, $AppId, $desc)
  Write-Output "OK $t"
}
