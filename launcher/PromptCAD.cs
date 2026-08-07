// PromptCAD launcher.
//
// A rebrand needs an executable users can pin, search for and see in Task
// Manager under our own name. Renaming FreeCAD's own binary would break its
// path discovery, so this is a separate ~10KB shim that starts the bundled
// freecad.exe with the working directory set to bin\ - which is what makes
// the relative image paths in branding.xml resolve.
//
// Built by launcher/build_launcher.ps1 with the in-box csc.exe, so the build
// needs no toolchain beyond what ships with Windows.

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("PromptCAD")]
[assembly: AssemblyProduct("PromptCAD")]
[assembly: AssemblyDescription("Natural-language parametric CAD")]
[assembly: AssemblyCompany("Alpha Intel Labs")]
[assembly: AssemblyCopyright("Copyright (c) 2026 Alpha Intel Labs. Built on FreeCAD.")]
// AssemblyVersion / AssemblyFileVersion are generated from the VERSION file
// by build_launcher.ps1, so the exe, the installer and Add/Remove Programs
// can never disagree about what version this is.

internal static class PromptCadLauncher
{
    private const string Title = "PromptCAD";

    // Where FreeCAD keeps this product's profile. The name comes from
    // <ExeName> in branding.xml and the folder from BuildVersionMajor/Minor,
    // which that file pins deliberately - see the comment there before
    // changing either of these.
    private const string ProfileName = "PromptCAD";
    private const string ProfileVersion = "v1-0";

    // The theme a fresh profile starts on. Stock FreeCAD with no theme set
    // draws with whatever palette Windows hands Qt and *no* stylesheet, so its
    // tab bars, scroll bars and combo boxes fall back to raw Qt chrome and its
    // greys do not match the rest of the app. Preference packs are ordinary
    // FCParameters documents - the same shape as user.cfg - so a pack file
    // simply *is* a valid starting profile.
    private const string ThemePack =
        @"data\Gui\PreferencePacks\FreeCAD Dark\FreeCAD Dark.cfg";

    [STAThread]
    private static int Main(string[] args)
    {
        string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string bin = Path.Combine(root, "bin");
        string target = Path.Combine(bin, "freecad.exe");

        if (!File.Exists(target))
        {
            MessageBox.Show(
                "PromptCAD could not find its application files.\n\n" +
                "Expected:\n" + target + "\n\n" +
                "Reinstalling PromptCAD should repair this.",
                Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        SeedProfile(root);

        var startInfo = new ProcessStartInfo(target)
        {
            Arguments = BuildArguments(args),
            WorkingDirectory = bin,
            UseShellExecute = false,
        };

        // The addon looks for llama-server in MACHINE_LLAMA_SERVER first, then
        // in ~/.machine, then on PATH - and downloads one from GitHub if it
        // finds none. We ship the binary, so point at it and skip that
        // download entirely: a local model should work on a machine that has
        // never been online. Guarded by File.Exists so a build without the
        // backend still starts and just falls back to fetching one.
        string backend = Path.Combine(root, "backend", "llama-server.exe");
        if (File.Exists(backend))
        {
            startInfo.EnvironmentVariables["MACHINE_LLAMA_SERVER"] = backend;
        }

        try
        {
            Process.Start(startInfo);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "PromptCAD could not start.\n\n" + ex.Message,
                Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        // Exit rather than wait: the child owns the UI from here, and leaving
        // this shim resident would just park a second process in the tree.
        return 0;
    }

    // Give a brand-new profile the bundled theme, by writing it as the initial
    // user.cfg before FreeCAD has one to read. Doing it here rather than from
    // the addon is what makes it seamless: applying a theme after startup
    // means the user watches the whole window repaint, and applying it from
    // the installer would be wrong because the profile is per-user and the
    // installer is not.
    //
    // Only ever for a profile that does not exist yet. Once there is a
    // user.cfg it is the user's - they may have deliberately chosen the light
    // theme, and an upgrade that overrode that would be a bug.
    private static void SeedProfile(string root)
    {
        try
        {
            string profile = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                ProfileName, ProfileVersion);
            string userCfg = Path.Combine(profile, "user.cfg");
            if (File.Exists(userCfg))
            {
                return;
            }

            string pack = Path.Combine(root, ThemePack);
            if (!File.Exists(pack))
            {
                return;
            }

            Directory.CreateDirectory(profile);
            File.Copy(pack, userCfg);
        }
        catch (Exception)
        {
            // Purely cosmetic. A profile we could not seed is a first run in
            // the stock theme, which is a far better outcome than refusing to
            // start over a colour scheme.
        }
    }

    // No --user-cfg here on purpose. Setting <ExeName> in branding.xml already
    // moves the entire user profile to %APPDATA%\PromptCAD\ - config, Mod,
    // Macro and cache - so PromptCAD and a coexisting FreeCAD install never
    // touch each other's settings. Passing --user-cfg as well would be worse
    // than doing nothing: it would relocate user.cfg alone and split the
    // profile across two directories.
    private static string BuildArguments(string[] args)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < args.Length; i++)
        {
            if (i > 0)
            {
                sb.Append(' ');
            }
            sb.Append(Quote(args[i]));
        }
        return sb.ToString();
    }

    // Re-quote an argument the way CommandLineToArgvW will take it apart
    // again, so paths with spaces (or trailing backslashes) survive the hop.
    private static string Quote(string arg)
    {
        if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
        {
            return arg;
        }

        var sb = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char c in arg)
        {
            if (c == '\\')
            {
                backslashes++;
                continue;
            }

            if (c == '"')
            {
                // Escape the run of backslashes, then the quote itself.
                sb.Append('\\', (backslashes * 2) + 1).Append('"');
            }
            else
            {
                sb.Append('\\', backslashes).Append(c);
            }
            backslashes = 0;
        }
        // Trailing backslashes must be doubled so they don't escape the close quote.
        sb.Append('\\', backslashes * 2).Append('"');
        return sb.ToString();
    }
}
