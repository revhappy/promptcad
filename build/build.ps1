<#
.SYNOPSIS
    Build the PromptCAD distribution: a staged application tree and a Windows
    installer.

.DESCRIPTION
    PromptCAD is a rebranded bundle, not a fork. This script:

      1. renders the icon set,
      2. compiles the PromptCAD.exe launcher,
      3. mirrors an *unmodified* FreeCAD install into the staging tree,
      4. rebrands a copy of the GPT4FreeCAD addon into stage\Mod\PromptCAD,
      5. drops branding.xml, artwork, the launcher and the licence files in,
      6. compiles the whole thing into one installer with Inno Setup.

    Nothing here modifies the FreeCAD install or the GPT4FreeCAD checkout;
    both are read-only inputs. That is what keeps the bundle on the right
    side of LGPL-2.1 - we redistribute FreeCAD verbatim and add our own
    files alongside it.

.PARAMETER SkipPayload
    Reuse the FreeCAD copy already in staging. The mirror step moves ~2GB,
    so skip it when you are only iterating on branding or the addon.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -SkipPayload -NoInstaller
#>
[CmdletBinding()]
param(
    [string] $FreeCAD = 'C:\Program Files\FreeCAD 1.1',
    [string] $Addon,
    [string] $Out,
    [string[]] $ExcludeMod = @(),
    [switch] $SkipPayload,
    [switch] $NoInstaller,
    [switch] $MaxCompression
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
if (-not $Addon) { $Addon = Join-Path (Split-Path -Parent $root) 'GPT4FreeCAD' }
if (-not $Out) { $Out = Join-Path $root 'dist' }

$stage = Join-Path $Out 'stage'
$branding = Join-Path $root 'branding'
$launcher = Join-Path $root 'launcher'
$legal = Join-Path $root 'legal'
$python = Join-Path $FreeCAD 'bin\python.exe'

function Write-Step([string] $Text) {
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
}

# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
Write-Step 'Checking inputs'

if (-not (Test-Path $FreeCAD)) { throw "FreeCAD not found: $FreeCAD" }
if (-not (Test-Path $python)) { throw "FreeCAD's python not found: $python" }
if (-not (Test-Path (Join-Path $Addon 'InitGui.py'))) {
    throw "GPT4FreeCAD checkout not found: $Addon`nPass -Addon <path>."
}

# PromptCAD versions itself. It is a distribution, not a re-release of the
# addon, and inheriting the addon's number would put "2.8.0" in Add/Remove
# Programs while the app's own title bar said something else. The addon
# version is read too, but only to print it.
$version = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
if (-not $version) { throw "VERSION file is empty: $root\VERSION" }

$packageXml = Join-Path $Addon 'package.xml'
$addonVersion = $null
try {
    [xml] $pkg = Get-Content $packageXml -Raw
    $addonVersion = $pkg.package.version
} catch { }
if (-not $addonVersion) {
    $match = Select-String -Path $packageXml -Pattern '<version>([^<]+)</version>' |
        Select-Object -First 1
    if ($match) { $addonVersion = $match.Matches[0].Groups[1].Value }
}
if (-not $addonVersion) { $addonVersion = 'unknown' }

Write-Host "  FreeCAD   : $FreeCAD"
Write-Host "  Addon     : $Addon (v$addonVersion)"
Write-Host "  PromptCAD : v$version"
Write-Host "  Staging   : $stage"

New-Item -ItemType Directory -Path $Out -Force | Out-Null

# --------------------------------------------------------------------------
# 1. Artwork
# --------------------------------------------------------------------------
Write-Step 'Rendering icons'
& $python (Join-Path $branding 'build_icons.py')
if ($LASTEXITCODE -ne 0) { throw "build_icons.py failed ($LASTEXITCODE)" }

# --------------------------------------------------------------------------
# 2. Launcher
# --------------------------------------------------------------------------
Write-Step 'Compiling launcher'
& (Join-Path $launcher 'build_launcher.ps1') -Version $version

# --------------------------------------------------------------------------
# 3. FreeCAD payload (verbatim)
# --------------------------------------------------------------------------
# Workbenches that ship with stock FreeCAD 1.1. Anything else under Mod\ is
# something the build machine installed locally, and must not end up in the
# bundle: a developer's own copy of the upstream addon would install a second,
# unbranded workbench next to PromptCAD.
$stockMod = @(
    'AddonManager', 'Assembly', 'BIM', 'CAM', 'Draft', 'Fem', 'Help', 'Idf',
    'Import', 'Inspection', 'Material', 'Measure', 'Mesh', 'MeshPart',
    'OpenSCAD', 'Part', 'PartDesign', 'Plot', 'Points', 'ReverseEngineering',
    'Robot', 'Show', 'Sketcher', 'Spreadsheet', 'Start', 'Surface',
    'TechDraw', 'Test', 'Tux', 'Web'
)

# Always drop the addon we are rebranding; PromptCAD supplies its own copy.
$dropMod = @($ExcludeMod) + @(Split-Path $Addon -Leaf)
foreach ($dir in Get-ChildItem (Join-Path $FreeCAD 'Mod') -Directory) {
    if ($stockMod -notcontains $dir.Name -and $dropMod -notcontains $dir.Name) {
        Write-Warning ("Mod\{0} is not part of stock FreeCAD and will be " +
                       "bundled. Pass -ExcludeMod {0} to leave it out." -f $dir.Name)
    }
}
$dropMod = $dropMod | Sort-Object -Unique

# Artefacts of the build machine's own FreeCAD installation. Uninstall-FreeCAD
# is FreeCAD-branded and would run against FreeCAD's install log rather than
# ours, and install.log is a ~12MB record of local paths on this machine.
# Neither belongs in a redistributable.
$dropFiles = @('install.log', 'Uninstall-FreeCAD.exe')

if ($SkipPayload -and (Test-Path (Join-Path $stage 'bin\freecad.exe'))) {
    Write-Step 'Reusing staged FreeCAD payload (-SkipPayload)'
} else {
    Write-Step 'Mirroring FreeCAD into staging (this moves ~2GB)'
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    $excludeDirs = @()
    foreach ($name in $dropMod) { $excludeDirs += (Join-Path $FreeCAD "Mod\$name") }
    Write-Host ("  excluding Mod: {0}" -f ($dropMod -join ', '))
    Write-Host ("  excluding files: {0}" -f ($dropFiles -join ', '))

    # /MIR so a rebuild cannot inherit stale files from an earlier layout.
    # /XJD so a junctioned dev checkout is not silently pulled in by value.
    robocopy $FreeCAD $stage /MIR /XJD /XD $excludeDirs /XF $dropFiles `
        /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    # Robocopy uses a bit field: < 8 means success, possibly with copies made.
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

# /XD also exempts these from /MIR's purge, so an earlier build's copy would
# survive. Remove them explicitly rather than trusting the mirror.
foreach ($name in $dropMod) {
    $stale = Join-Path $stage "Mod\$name"
    if (Test-Path $stale) {
        Remove-Item $stale -Recurse -Force
        Write-Host "  removed stale Mod\$name from staging"
    }
}
foreach ($name in $dropFiles) {
    $stale = Join-Path $stage $name
    if (Test-Path $stale) {
        Remove-Item $stale -Force
        Write-Host "  removed stale $name from staging"
    }
}

# --------------------------------------------------------------------------
# 4. Rebranded addon
# --------------------------------------------------------------------------
Write-Step 'Rebranding the addon into stage\Mod\PromptCAD'
& $python (Join-Path $PSScriptRoot 'rebrand.py') `
    --source $Addon `
    --dest (Join-Path $stage 'Mod\PromptCAD') `
    --branding $branding `
    --overlay (Join-Path $root 'overlay')
if ($LASTEXITCODE -ne 0) { throw "rebrand.py failed ($LASTEXITCODE)" }

# --------------------------------------------------------------------------
# 4b. Inference backend
# --------------------------------------------------------------------------
Write-Step 'Staging the inference backend'

# Without this the first local-model run downloads llama-server from GitHub.
# It is ~30MB against a 432MB installer, and it buys "works offline".
$cache = Join-Path $root '.cache'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$backendDir = Join-Path $stage 'backend'

if (Test-Path (Join-Path $backendDir 'llama-server.exe')) {
    Write-Host '  already staged'
} else {
    $cachedZip = Get-ChildItem (Join-Path $cache 'llama-*-bin-win-cpu-x64.zip') `
        -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1

    if (-not $cachedZip) {
        Write-Host '  querying llama.cpp releases'
        try {
            $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest' `
                -Headers @{ 'User-Agent' = 'promptcad-build' }
            $asset = $release.assets | Where-Object { $_.name -match '^llama-b\d+-bin-win-cpu-x64\.zip$' } |
                Select-Object -First 1
            if (-not $asset) { throw "no win-cpu-x64 asset in release $($release.tag_name)" }

            $cachedZip = Join-Path $cache $asset.name
            Write-Host ("  downloading {0} ({1:N0} MB)" -f $asset.name, ($asset.size / 1MB))
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $cachedZip -UseBasicParsing
            $cachedZip = Get-Item $cachedZip
        } catch {
            Write-Warning @"
Could not obtain llama-server: $($_.Exception.Message)
The build continues without a bundled backend - PromptCAD will download one
on first use of a local model instead.
"@
            $cachedZip = $null
        }
    } else {
        Write-Host "  using cached $($cachedZip.Name)"
    }

    if ($cachedZip) {
        $unpack = Join-Path $cache 'backend-unpacked'
        if (Test-Path $unpack) { Remove-Item $unpack -Recurse -Force }
        Expand-Archive -Path $cachedZip.FullName -DestinationPath $unpack -Force

        # The archive layout has moved between releases, so find the binary
        # rather than assuming it sits at a fixed depth.
        $exe = Get-ChildItem $unpack -Recurse -Filter 'llama-server.exe' |
            Select-Object -First 1
        if (-not $exe) { throw "llama-server.exe not found inside $($cachedZip.Name)" }

        New-Item -ItemType Directory -Path $backendDir -Force | Out-Null
        # Take everything beside the exe: it needs its DLLs.
        Copy-Item (Join-Path $exe.Directory.FullName '*') $backendDir -Recurse -Force
        Write-Host "  staged backend from $($cachedZip.Name)"
    }
}

# --------------------------------------------------------------------------
# 5. Branding, launcher and licences
# --------------------------------------------------------------------------
Write-Step 'Applying branding'

$bin = Join-Path $stage 'bin'
Copy-Item (Join-Path $branding 'branding.xml') $bin -Force
foreach ($asset in 'promptcad-window.png', 'promptcad-logo.png', 'promptcad-splash.png') {
    Copy-Item (Join-Path $branding "generated\$asset") $bin -Force
}
Copy-Item (Join-Path $launcher 'generated\PromptCAD.exe') $stage -Force
Copy-Item (Join-Path $branding 'generated\PromptCAD.ico') $stage -Force

# An obvious place to drop a .gguf. The discovery scan checks this first, so a
# model landing here is picked up without the user touching preferences.
$modelsDir = Join-Path $stage 'models'
New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
Copy-Item (Join-Path $root 'assets\models-README.txt') (Join-Path $modelsDir 'README.txt') -Force

$stagedLegal = Join-Path $stage 'legal'
New-Item -ItemType Directory -Path $stagedLegal -Force | Out-Null
Copy-Item (Join-Path $legal '*') $stagedLegal -Recurse -Force

# FreeCAD ships its own licence text; carry it into legal\ so the LGPL
# notices sit in one obvious place rather than only under doc\.
$freecadLicense = Join-Path $stage 'doc\LICENSE.html'
if (Test-Path $freecadLicense) {
    Copy-Item $freecadLicense (Join-Path $stagedLegal 'FreeCAD-LICENSE.html') -Force
}
$thirdParty = Join-Path $stage 'doc\ThirdPartyLibraries.html'
if (Test-Path $thirdParty) {
    Copy-Item $thirdParty (Join-Path $stagedLegal 'FreeCAD-ThirdPartyLibraries.html') -Force
}

Write-Host "  branding.xml + artwork -> bin\"
Write-Host "  PromptCAD.exe -> stage root"
Write-Host "  licences -> legal\"

# --------------------------------------------------------------------------
# 6. Installer
# --------------------------------------------------------------------------
if ($NoInstaller) {
    Write-Step 'Skipping installer (-NoInstaller)'
} else {
    Write-Step 'Compiling installer'

    # winget installs Inno Setup per-user by default, so LOCALAPPDATA has to be
    # searched too - a machine-wide install is only one of three likely homes.
    $iscc = Get-ChildItem @(
        "${env:ProgramFiles(x86)}\Inno Setup*\ISCC.exe"
        "$env:ProgramFiles\Inno Setup*\ISCC.exe"
        "$env:LOCALAPPDATA\Programs\Inno Setup*\ISCC.exe"
    ) -ErrorAction SilentlyContinue | Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $iscc) {
        Write-Warning @"
Inno Setup is not installed, so no installer was produced.
The staged app in $stage is complete and runnable - launch it with:
    $stage\PromptCAD.exe

Install Inno Setup and re-run to get the installer:
    winget install --id JRSoftware.InnoSetup
"@
    } else {
        # lzma2/max costs roughly three times the compile time for a few
        # percent of size on this payload, so it is opt-in for release builds.
        $mode = 'lzma2/normal'
        if ($MaxCompression) { $mode = 'lzma2/max' }
        Write-Host "  compression: $mode"

        & $iscc "/DAppVersion=$version" "/DStageDir=$stage" `
            "/DCompressionMode=$mode" "/O$Out" `
            (Join-Path $root 'installer\PromptCAD.iss')
        if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
    }
}

Write-Step 'Done'
Write-Host "  Staged app : $stage\PromptCAD.exe"
Get-ChildItem (Join-Path $Out '*.exe') -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host ("  Installer  : {0} ({1:N0} MB)" -f $_.FullName, ($_.Length / 1MB)) }
