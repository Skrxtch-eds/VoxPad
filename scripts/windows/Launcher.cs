using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class Launcher
{
    internal static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char character in value)
        {
            if (character == '\\') { slashes++; continue; }
            result.Append('\\', character == '"' ? slashes * 2 + 1 : slashes);
            result.Append(character);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string versionFile = Path.Combine(root, "current.txt");
            string folder = root;
            if (File.Exists(versionFile))
            {
                string version = File.ReadAllText(versionFile).Trim();
                Version.Parse(version);
                folder = Path.Combine(root, "versions", version);
            }
            string arguments = "-I " + Quote(Path.Combine(folder, "launch.py"));
            foreach (string argument in args)
                arguments += " " + Quote(argument);
            Process child = Process.Start(new ProcessStartInfo(Path.Combine(folder, "runtime", "pythonw.exe"), arguments)
            {
                UseShellExecute = false,
                WorkingDirectory = folder,
                CreateNoWindow = true
            });
            if (Array.IndexOf(args, "--smoke-test") >= 0)
            {
                child.WaitForExit();
                return child.ExitCode;
            }
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show("Не удалось запустить VoxPad. Повторите установку.\n\n" + error.Message,
                            "VoxPad", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
