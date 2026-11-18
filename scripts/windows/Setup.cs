using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

internal static class Setup
{
    private const string Release = "@VERSION@";
    private const string PayloadUrl = "@URL@";
    private const string PayloadHash = "@SHA256@";
    private static string root;
    private static string localArchive;
    private static bool autostart = true;
    private static bool testMode;

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
            File.WriteAllText(marker, "VoxPad");
            string next = Path.Combine(root, "current.next");
            File.WriteAllText(next, Release);
            string current = Path.Combine(root, "current.txt");
            if (File.Exists(current)) File.Replace(next, current, null);
            else File.Move(next, current);
            SavePreferences();
            report("Установка завершена.", 100);
        }
        finally { if (Directory.Exists(temporary)) Directory.Delete(Extended(temporary), true); }
    }

    private static void SavePreferences()
    {
        string directory = Path.Combine(root, "data");
        Directory.CreateDirectory(directory);
        string path = Path.Combine(directory, "settings.json");
        var json = new JavaScriptSerializer();
        var settings = File.Exists(path)
            ? json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path))
            : new Dictionary<string, object>();
        if (settings == null) throw new IOException("Некорректный файл настроек: " + path);
        settings["autostart"] = autostart;
        string next = path + ".setup-next";
        File.WriteAllText(next, json.Serialize(settings), new UTF8Encoding(false));
        if (File.Exists(path)) File.Replace(next, path, null);
        else File.Move(next, path);
    }

    private static void Uninstall()
    {
        CheckRunning();
        if (!File.Exists(Path.Combine(root, ".voxpad-install")))
            throw new IOException("Папка установки VoxPad не найдена.");
        string versions = Path.Combine(root, "versions");
        if (Directory.Exists(versions)) Directory.Delete(Extended(versions), true);
        foreach (string name in new[] { "VoxPad.exe", "current.txt", ".voxpad-install" })
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
        Console.OutputEncoding = Encoding.GetEncoding(System.Globalization.CultureInfo.CurrentCulture.TextInfo.OEMCodePage);
        root = null;
        foreach (string arg in args)
        {
            if (arg.StartsWith("--target=")) root = Path.GetFullPath(arg.Substring(9));
            if (arg.StartsWith("--archive=")) localArchive = Path.GetFullPath(arg.Substring(10));
            if (arg == "--autostart=0") autostart = false;
            if (arg == "--test-mode") testMode = true;
        }
        try
        {
            if (root == null) throw new ArgumentException("Папка установки не указана.");
            if (Array.IndexOf(args, "--remove-files") >= 0) { Uninstall(); return 0; }
            if (!Environment.Is64BitOperatingSystem) throw new PlatformNotSupportedException("Нужна 64-битная Windows 10/11.");
            string last = null;
            int lastPercent = -1;
            InstallFiles((text, percent) =>
            {
                if (percent != lastPercent || (percent == 0 && last == null))
                {
                    Console.WriteLine(text);
                    last = text;
                    lastPercent = percent;
                }
            }, CancellationToken.None);
            return 0;
        }
        catch (Exception error)
        {
            string log = Path.Combine(Path.GetTempPath(), "VoxPad-setup-error.log");
            File.WriteAllText(log, error.ToString());
            Console.WriteLine(error.Message + " — " + log);
            return 1;
        }
    }
}
