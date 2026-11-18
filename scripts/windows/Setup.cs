using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

internal sealed class Setup : Form
{
    private const string Release = "@VERSION@";
    private const string PayloadUrl = "@URL@";
    private const string PayloadHash = "@SHA256@";
    private static string root;
    private static string localArchive;
    private static bool testMode;
    private static bool silent;
    private readonly Label status = new Label { Left = 24, Top = 24, Width = 455, Height = 60 };
    private readonly ProgressBar progress = new ProgressBar { Left = 24, Top = 92, Width = 450 };
    private readonly Button action = new Button { Left = 324, Top = 135, Width = 150, Height = 32, Text = "Установить" };
    private readonly CancellationTokenSource cancellation = new CancellationTokenSource();
    private bool running;
    private bool completed;

    private Setup()
    {
        Text = "Установка VoxPad " + Release;
        ClientSize = new System.Drawing.Size(500, 190);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        status.Text = "Установщик скачает приложение и модель Parakeet.\nПосле установки диктовка работает без интернета.";
        Controls.AddRange(new Control[] { status, progress, action });
        action.Click += async (sender, args) =>
        {
            if (completed) { Close(); return; }
            if (running) { cancellation.Cancel(); return; }
            running = true;
            action.Text = "Отменить";
            try
            {
                await Install();
                status.Text = "VoxPad установлен. Запустите приложение из меню «Пуск».";
                progress.Value = 100;
                completed = true;
                action.Text = "Готово";
            }
            catch (OperationCanceledException) { status.Text = "Установка отменена."; action.Text = "Закрыть"; completed = true; }
            catch (Exception error) { status.Text = "Установка не завершена. " + error.Message; action.Text = "Закрыть"; completed = true; }
            finally { running = false; }
        };
        FormClosing += (sender, args) => { if (running) { cancellation.Cancel(); args.Cancel = true; } };
    }

    private void Report(string text, int value)
    {
        if (IsHandleCreated && InvokeRequired)
            BeginInvoke((Action)(() => Report(text, value)));
        else { status.Text = text; progress.Value = Math.Max(0, Math.Min(100, value)); }
    }

    private async Task Install()
    {
        await Task.Run(() => InstallFiles(Report, cancellation.Token));
    }

    private static string Hash(string filename)
    {
        using (SHA256 algorithm = SHA256.Create())
        using (FileStream stream = File.OpenRead(filename))
            return BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }

    private static string Extended(string path)
    {
        string full = Path.GetFullPath(path);
        if (full.StartsWith(@"\\?\")) return full;
        if (full.StartsWith(@"\\")) return @"\\?\UNC\" + full.Substring(2);
        return @"\\?\" + full;
    }

    private static void CheckRunning()
    {
        if (testMode) return;
        Mutex mutex;
        if (Mutex.TryOpenExisting("Local\\ParakeetTranscriber", out mutex))
        {
            mutex.Dispose();
            throw new IOException("Закройте VoxPad через значок в трее и повторите установку.");
        }
    }

    private static void InstallFiles(Action<string, int> report, CancellationToken token)
    {
        using (var guard = new Mutex(false, "Local\\VoxPadSetup"))
        {
            bool acquired;
            try { acquired = guard.WaitOne(0); }
            catch (AbandonedMutexException) { acquired = true; }
            if (!acquired) throw new IOException("Другой установщик VoxPad уже работает.");
            try { InstallLocked(report, token); }
            finally { guard.ReleaseMutex(); }
        }
    }

    private static void InstallLocked(Action<string, int> report, CancellationToken token)
    {
        CheckRunning();
        Directory.CreateDirectory(root);
        string marker = Path.Combine(root, ".voxpad-install");
        if (Directory.GetFiles(root).Length > 0 && !File.Exists(marker))
            throw new IOException("Выбранная папка уже содержит файлы. Выберите отдельную папку для VoxPad.");
        File.WriteAllText(marker, "VoxPad");
        string temporary = Path.Combine(root, ".setup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try
        {
            string archive = localArchive ?? Path.Combine(temporary, "payload.zip");
            if (localArchive == null)
            {
                report("Скачивание приложения и модели…", 0);
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(PayloadUrl);
                request.UserAgent = "VoxPad-Setup/" + Release;
                request.Timeout = 30000;
                request.ReadWriteTimeout = 30000;
                using (token.Register(() => request.Abort()))
                using (WebResponse response = request.GetResponse())
                using (Stream source = response.GetResponseStream())
                using (FileStream destination = File.Create(archive))
                {
                    byte[] buffer = new byte[262144];
                    long received = 0;
                    int count;
                    while ((count = source.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        token.ThrowIfCancellationRequested();
                        destination.Write(buffer, 0, count);
                        received += count;
                        int percent = response.ContentLength > 0 ? (int)(received * 70 / response.ContentLength) : 0;
                        report("Скачано " + (received / 1048576) + " МБ", percent);
                    }
                }
            }
            token.ThrowIfCancellationRequested();
            report("Проверка SHA-256…", 72);
            if (Hash(archive) != PayloadHash)
                throw new IOException("Контрольная сумма не совпала. Повторите установку.");
            string extracted = Path.Combine(temporary, "extracted");
            Directory.CreateDirectory(extracted);
            string prefix = Path.GetFullPath(extracted) + Path.DirectorySeparatorChar;
            report("Распаковка компонентов…", 77);
            using (ZipArchive package = ZipFile.OpenRead(archive))
            {
                foreach (ZipArchiveEntry entry in package.Entries)
                {
                    token.ThrowIfCancellationRequested();
                    string path = Path.GetFullPath(Path.Combine(extracted, entry.FullName));
                    if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                        throw new IOException("Недопустимый путь в архиве.");
                    if (entry.Name.Length == 0) { Directory.CreateDirectory(Extended(path)); continue; }
                    Directory.CreateDirectory(Extended(Path.GetDirectoryName(path)));
                    using (Stream source = entry.Open())
                    using (FileStream destination = File.Create(Extended(path)))
                        source.CopyTo(destination);
                }
            }
            string bundle = Path.Combine(extracted, "VoxPad");
            foreach (string file in new[] { "runtime/pythonw.exe", "launch.py", "VoxPad.exe", "BUILD-MANIFEST.json" })
                if (!File.Exists(Path.Combine(bundle, file)))
                    throw new IOException("В архиве отсутствует компонент " + file);
            token.ThrowIfCancellationRequested();
            CheckRunning();
            report("Завершение установки…", 95);
            string versions = Path.Combine(root, "versions");
            Directory.CreateDirectory(versions);
            string target = Path.Combine(versions, Release);
            // A verified, already installed version can be reused on retry.
            if (!Directory.Exists(target))
            {
                File.WriteAllText(Path.Combine(bundle, "installed.flag"), Release);
                Directory.Move(bundle, target);
            }
            string launcher = Path.Combine(root, "VoxPad.exe");
            File.Copy(Path.Combine(target, "VoxPad.exe"), launcher, true);
            if (!String.Equals(Application.ExecutablePath, Path.Combine(root, "Uninstall.exe"), StringComparison.OrdinalIgnoreCase))
                File.Copy(Application.ExecutablePath, Path.Combine(root, "Uninstall.exe"), true);
            File.WriteAllText(marker, "VoxPad");
            string next = Path.Combine(root, "current.next");
            File.WriteAllText(next, Release);
            string current = Path.Combine(root, "current.txt");
            if (File.Exists(current)) File.Replace(next, current, null);
            else File.Move(next, current);
            if (!testMode)
            {
                Shortcuts(false);
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\VoxPad"))
                {
                    key.SetValue("DisplayName", "VoxPad");
                    key.SetValue("DisplayVersion", Release);
                    key.SetValue("InstallLocation", root);
                    key.SetValue("DisplayIcon", launcher);
                    key.SetValue("UninstallString", "\"" + Path.Combine(root, "Uninstall.exe") + "\" --uninstall");
                    key.SetValue("NoModify", 1);
                    key.SetValue("NoRepair", 1);
                }
            }
            report("Установка завершена.", 100);
        }
        finally { if (Directory.Exists(temporary)) Directory.Delete(Extended(temporary), true); }
    }

    private static void Shortcuts(bool remove)
    {
        string menu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "VoxPad.lnk");
        string desktop = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "VoxPad.lnk");
        foreach (string path in new[] { menu, desktop })
        {
            if (remove) { if (File.Exists(path)) File.Delete(path); continue; }
            Type type = Type.GetTypeFromProgID("WScript.Shell");
            dynamic shell = Activator.CreateInstance(type);
            dynamic shortcut = shell.CreateShortcut(path);
            shortcut.TargetPath = Path.Combine(root, "VoxPad.exe");
            shortcut.WorkingDirectory = root;
            shortcut.IconLocation = shortcut.TargetPath;
            shortcut.Save();
        }
    }

    private static void Uninstall()
    {
        CheckRunning();
        if (!File.Exists(Path.Combine(root, ".voxpad-install")))
            throw new IOException("Папка установки VoxPad не найдена.");
        if (!testMode)
        {
            Shortcuts(true);
            Registry.CurrentUser.DeleteSubKeyTree("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\VoxPad", false);
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run", true))
                if (key != null && Convert.ToString(key.GetValue("ParakeetTranscriber")).IndexOf(root, StringComparison.OrdinalIgnoreCase) >= 0)
                    key.DeleteValue("ParakeetTranscriber", false);
        }
        string versions = Path.Combine(root, "versions");
        if (Directory.Exists(versions)) Directory.Delete(Extended(versions), true);
        foreach (string name in new[] { "VoxPad.exe", "current.txt", ".voxpad-install", "Uninstall.exe" })
        {
            string path = Path.Combine(root, name);
            for (int attempt = 0; attempt < 20; attempt++)
            {
                try { File.Delete(path); break; }
                catch (IOException) { Thread.Sleep(250); if (attempt == 19) throw; }
            }
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        Application.EnableVisualStyles();
        root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "VoxPad");
        foreach (string arg in args)
        {
            if (arg.StartsWith("--target=")) root = Path.GetFullPath(arg.Substring(9));
            if (arg.StartsWith("--archive=")) localArchive = Path.GetFullPath(arg.Substring(10));
            if (arg == "--test-mode") testMode = true;
            if (arg == "--silent") silent = true;
        }
        try
        {
            if (Array.IndexOf(args, "--uninstall") >= 0)
            {
                if (!silent && MessageBox.Show("Удалить VoxPad? История и настройки останутся в папке data.",
                    "VoxPad", MessageBoxButtons.YesNo) != DialogResult.Yes) return 0;
                string worker = Path.Combine(Path.GetTempPath(), "VoxPad-uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
                File.Copy(Application.ExecutablePath, worker);
                Process.Start(worker, "--uninstall-worker --target=\"" + root + "\" " + (testMode ? "--test-mode " : "") + (silent ? "--silent" : ""));
                return 0;
            }
            if (Array.IndexOf(args, "--uninstall-worker") >= 0) { Uninstall(); return 0; }
            if (!Environment.Is64BitOperatingSystem) throw new PlatformNotSupportedException("Нужна 64-битная Windows 10/11.");
            if (silent) { InstallFiles((text, percent) => { }, CancellationToken.None); return 0; }
            Application.Run(new Setup());
            return 0;
        }
        catch (Exception error)
        {
            string log = Path.Combine(Path.GetTempPath(), "VoxPad-setup-error.log");
            File.WriteAllText(log, error.ToString());
            if (!silent) MessageBox.Show(error.Message + "\n\nОтчёт: " + log, "VoxPad", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
