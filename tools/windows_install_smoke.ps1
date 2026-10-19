#requires -Version 7.2
<#
Dedicated Windows CI smoke test, without ROM or game assets. Never adopts an
existing installation. WorkRoot and reports remain after success/failure.
Same installer is deliberately used twice: this is same-version reinstallation,
not migration between releases, a clean-machine test, or a valid game save test.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][string]$InstallerBuild,
    [Parameter(Mandatory)][string]$Payload,
    [Parameter(Mandatory)][string]$ReportPath,
    [string]$Python = 'python',
    [string]$WorkRoot,
    [ValidateRange(30, 600)][int]$ProcessTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or -not [Environment]::Is64BitProcess) {
    throw 'Este teste exige PowerShell 7 x64 no Windows.'
}
$appId = 'org.khcom.ptbr.experimental'
$registryPath = "Software\Microsoft\Windows\CurrentVersion\Uninstall\${appId}_is1"
$utf8 = [Text.UTF8Encoding]::new($false)
$runId = [Guid]::NewGuid().ToString('D')
$script:processUnresolved = $false
$script:installAttempted = $false
$script:removed = $false
$script:events = [Collections.Generic.List[object]]::new()
$script:failure = $null
$script:cleanupFailure = $null
$script:uninstallFiles = @{}
# Drain both streams even after the evidence cap, preventing pipe deadlocks.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Threading.Tasks;
public sealed class KHComSmokeOutput {
    public string Text;
    public bool Truncated;
    public static async Task<KHComSmokeOutput> Read(StreamReader reader) {
        var result = new KHComSmokeOutput();
        var text = new StringBuilder();
        var buffer = new char[4096];
        int count;
        while ((count = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) > 0) {
            int keep = Math.Min(count, 1048576 - text.Length);
            text.Append(buffer, 0, keep);
            if (keep < count) result.Truncated = true;
        }
        result.Text = text.ToString();
        return result;
    }
}
'@

function Full-Path([string]$Value) { return [IO.Path]::GetFullPath($Value).TrimEnd('\') }
function Same-Path([string]$A, [string]$B) {
    return [string]::Equals((Full-Path $A), (Full-Path $B), [StringComparison]::OrdinalIgnoreCase)
}
function Hash-File([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Write-NewText([string]$Path, [string]$Text) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $bytes = $utf8.GetBytes($Text); $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}
function Write-NewJson([string]$Path, $Value) { Write-NewText $Path ($Value | ConvertTo-Json -Depth 30) }
function Assert-NoReparse([string]$Path) {
    $cursor = Full-Path $Path
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if (((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Link/junção recusado: $cursor"
            }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        $cursor = if ($null -eq $parent) { $null } else { $parent.FullName }
    }
}
function Assert-Owner {
    Assert-NoReparse $root
    $owner = Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
    if ($owner.run_id -ne $runId -or -not (Same-Path $owner.root $root)) { throw 'Identidade da raiz mudou.' }
}
function Read-AppRegistrations {
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                $key = $base.OpenSubKey($registryPath, $false)
                if ($null -ne $key) {
                    try {
                        [pscustomobject]@{ hive = "$hive"; view = "$view"; key = $registryPath
                            install_location = $key.GetValue('InstallLocation', '')
                            uninstall_string = $key.GetValue('UninstallString', '')
                            display_name = $key.GetValue('DisplayName', '')
                            display_version = $key.GetValue('DisplayVersion', '') }
                    } finally { $key.Dispose() }
                }
            } finally { $base.Dispose() }
        }
    }
}
function Assert-OwnedInstallation {
    Assert-Owner
    Assert-NoReparse $installDir
    $keys = @(Read-AppRegistrations)
    if (-not $keys.Count) { throw 'Registro da instalação não encontrado.' }
    foreach ($key in $keys) {
        if ($key.hive -ne 'CurrentUser' -or -not $key.install_location -or
            -not (Same-Path $key.install_location $installDir)) { throw 'Registro não pertence à instalação deste teste.' }
        # Do not execute a registry command line. Validate its exact fixed target.
        if ($key.uninstall_string -ne ('"' + $uninstaller + '"') -and $key.uninstall_string -ne $uninstaller) {
            throw 'Desinstalador do registro diverge do caminho fixo possuído.'
        }
    }
    Assert-NoReparse $uninstaller
    if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) { throw 'Desinstalador possuído ausente.' }
    return $keys
}
function Seal-Uninstaller {
    [void](Assert-OwnedInstallation)
    $next = @{}
    foreach ($path in @($uninstaller, (Join-Path $installDir 'unins000.dat'))) {
        Assert-NoReparse $path
        $next[$path] = Hash-File $path
    }
    $script:uninstallFiles = $next
}
function Assert-UninstallerSeal {
    if ($script:uninstallFiles.Count -ne 2) { throw 'Identidade dos dois arquivos do desinstalador não foi estabelecida.' }
    foreach ($path in $script:uninstallFiles.Keys) {
        Assert-NoReparse $path
        if ((Hash-File $path) -ne $script:uninstallFiles[$path]) { throw 'Desinstalador ou log de operações mudou fora da atualização possuída.' }
    }
}
function Invoke-OwnedProcess([string]$Executable, [string[]]$Arguments, [string]$Label, [bool]$Restricted = $false) {
    Assert-Owner
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.WorkingDirectory = $root
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $restrictedPath = $null
    if ($Restricted) {
        # ProcessStartInfo avoids Start-Process -Environment appending host PATH.
        $restrictedPath = "$installDir;$env:SystemRoot\System32;$env:SystemRoot"
        $info.Environment['PATH'] = $restrictedPath
        foreach ($name in @('SDL_VIDEO_DRIVER', 'SDL_AUDIO_DRIVER', 'SDL_RENDER_DRIVER', 'SDL_GPU_DRIVER',
                             'SDL_VIDEODRIVER', 'SDL_AUDIODRIVER')) { [void]$info.Environment.Remove($name) }
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $modules = @{}
    $sampleErrors = [Collections.Generic.List[string]]::new()
    try {
        if (-not $process.Start()) { throw "Falha ao iniciar $Label" }
        $stdout = [KHComSmokeOutput]::Read($process.StandardOutput)
        $stderr = [KHComSmokeOutput]::Read($process.StandardError)
        while (-not $process.WaitForExit(100)) {
            if ($watch.Elapsed.TotalSeconds -ge $ProcessTimeoutSeconds) {
                $script:processUnresolved = $true
                throw "Timeout em $Label; não matar por PID nem desinstalar enquanto o processo pode estar ativo. Raiz retida para teardown do runner."
            }
            if ($Restricted) {
                try {
                    $process.Refresh()
                    foreach ($module in $process.Modules) { $modules[$module.FileName] = $true }
                } catch { if ($sampleErrors.Count -lt 8) { $sampleErrors.Add($_.Exception.Message) } }
            }
        }
        $process.WaitForExit()
        if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdout, $stderr), 5000)) {
            $script:processUnresolved = $true
            throw 'Processo pai terminou mas pipes continuam abertos; descendente não resolvido, sem cleanup automático.'
        }
        $out = $stdout.GetAwaiter().GetResult()
        $err = $stderr.GetAwaiter().GetResult()
        Write-NewText (Join-Path $root "$Label.stdout.txt") $out.Text
        Write-NewText (Join-Path $root "$Label.stderr.txt") $err.Text
        if ($out.Truncated -or $err.Truncated) { throw 'Saída de processo excedeu o limite de evidência; prefixos retidos.' }
        $observed = @()
        foreach ($path in ($modules.Keys | Sort-Object)) {
            $location = if ((Full-Path $path).StartsWith($installDir + '\', [StringComparison]::OrdinalIgnoreCase)) {
                'owned-install'
            } elseif ((Full-Path $path).StartsWith((Full-Path $env:SystemRoot) + '\', [StringComparison]::OrdinalIgnoreCase)) {
                'windows-directory'
            } else { 'outside-windows-and-install' }
            $observed += @{ path = $path; location = $location; sha256 = Hash-File $path }
        }
        $event = @{ stage = $Label; executable = $Executable; executable_sha256 = $null
            exit_code = $process.ExitCode; elapsed_seconds = $watch.Elapsed.TotalSeconds
            restricted_path = $restrictedPath; observed_modules = $observed; module_sample_errors = @($sampleErrors.ToArray()) }
        if (Test-Path -LiteralPath $Executable -PathType Leaf) { $event.executable_sha256 = Hash-File $Executable }
        $script:events.Add($event)
        if ($process.ExitCode -ne 0) { throw "$Label retornou $($process.ExitCode)." }
        if ($Restricted) {
            if (-not $observed.Count) { throw 'Nenhuma amostra de módulos; ensaio incompleto.' }
            if (@($observed | Where-Object { $_.location -eq 'outside-windows-and-install' }).Count) {
                throw 'Módulo observado fora do Windows/instalação: revisar relatório.'
            }
        }
    } finally { $watch.Stop(); $process.Dispose() }
}
function Assert-PayloadInstalled {
    [void](Assert-OwnedInstallation)
    if ((Hash-File (Join-Path $installDir 'package-manifest.json')) -ne $manifestHash) { throw 'Manifesto instalado diverge.' }
    foreach ($entry in $manifest.files) {
        $path = Join-Path $installDir $entry.path
        Assert-NoReparse $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-Item -LiteralPath $path).Length -ne $entry.size -or (Hash-File $path) -ne $entry.sha256) {
            throw "Arquivo instalado diverge: $($entry.path)"
        }
    }
}
function Invoke-Install([string]$Label) {
    if ((Hash-File $installerPath) -ne $installerHash) { throw 'Instalador mudou após validação.' }
    if ($Label -eq 'install') {
        if (@(Read-AppRegistrations).Count) { throw 'AppId apareceu após preflight; instalação recusada.' }
    } else {
        [void](Assert-OwnedInstallation)
        Assert-UninstallerSeal
    }
    $script:installAttempted = $true
    Invoke-OwnedProcess $installerPath @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART',
        '/RESTARTEXITCODE=3010', '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/NOICONS',
        "/GROUP=KHCoM smoke $runId", "/DIR=$installDir", "/LOG=$(Join-Path $root "$Label.inno.log")") $Label
    Assert-PayloadInstalled
    Seal-Uninstaller
}
function Invoke-Uninstall([string]$Label) {
    $registration = @(Assert-OwnedInstallation)
    Assert-UninstallerSeal
    Write-NewJson (Join-Path $root "$Label.registration.json") $registration
    $uninstallerHash = Hash-File $uninstaller
    Invoke-OwnedProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        "/LOG=$(Join-Path $root "$Label.inno.log")") $Label
    # Inno may finish deferred self-deletion just after its parent returns.
    for ($attempt = 0; $attempt -lt 100 -and (Test-Path -LiteralPath $uninstaller); $attempt++) {
        Start-Sleep -Milliseconds 100
    }
    if (@(Read-AppRegistrations).Count -or (Test-Path -LiteralPath $appExe) -or
        (Test-Path -LiteralPath $uninstaller)) { throw 'Desinstalação incompleta: arquivos/registro ainda presentes.' }
    if (Test-Path -LiteralPath $installDir) {
        if (@(Get-ChildItem -LiteralPath $installDir -Recurse -Force).Count) { throw 'Resíduos inesperados na instalação.' }
    }
    $script:removed = $true
    $script:events.Add(@{ stage = "$Label-verified"; uninstaller_input_sha256 = $uninstallerHash; appid_absent = $true })
}
function Assert-ConfigAndFixture {
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($config.schema_version -ne 1 -or $config.volume -ne 37 -or $config.scale -ne 2) {
        throw 'Configuração escolhida não foi preservada.'
    }
    if ((Hash-File $saveFixture) -ne $fixtureHash) { throw 'Fixture de arquivo em saves mudou.' }
}
function Invoke-App([string]$Label) {
    $appReport = Join-Path $root "$Label.app.json"
    Invoke-OwnedProcess $appExe @('--hidden', '--mute', '--ui-frames', '300', '--data-dir', $dataDir,
        '--report', $appReport) $Label $true
    $result = Get-Content -LiteralPath $appReport -Raw | ConvertFrom-Json
    if ($result.schema_version -ne 1 -or $result.simulated_frames -ne 0 -or $result.presented_frames -ne 300 -or
        $result.headless_dummy_devices -or -not $result.hidden_hardware_window -or $result.save_error -or
        $result.PSObject.Properties.Name -contains 'target_sha256' -or -not $result.renderer) {
        throw 'Relatório do aplicativo não comprova o ensaio sem ROM de 300 apresentações.'
    }
}

$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$buildPath = (Resolve-Path -LiteralPath $InstallerBuild).Path
$payloadPath = (Resolve-Path -LiteralPath $Payload).Path
$pythonPath = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source
$reportFile = Full-Path $ReportPath
if (Test-Path -LiteralPath $reportFile) { throw 'Relatório de saída já existe; escolha outro.' }
Assert-NoReparse $reportFile
foreach ($path in @($installerPath, $buildPath, $payloadPath)) { Assert-NoReparse $path }
$build = Get-Content -LiteralPath $buildPath -Raw | ConvertFrom-Json
$installerHash = Hash-File $installerPath
if ($build.schema_version -ne 1 -or $build.installer_sha256 -ne $installerHash -or
    $build.installer_size -ne (Get-Item -LiteralPath $installerPath).Length -or $build.compiler_engine -notmatch '\b6\.7\.1\b') {
    throw 'Identidade do instalador/compilador diverge do recibo do CI.'
}
$manifestPath = Join-Path $payloadPath 'package-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$manifestHash = Hash-File $manifestPath
$existing = @(Read-AppRegistrations)
if ($existing.Count) { throw 'AppId já instalado: teste recusado sem modificar a instalação existente.' }
$tempBase = Full-Path ([IO.Path]::GetTempPath())
$root = if ($WorkRoot) { Full-Path $WorkRoot } else { Join-Path $tempBase "KHCoM smoke ação $runId" }
if (-not $root.StartsWith($tempBase + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $root -notmatch ' ' -or $root -notmatch '[^\x00-\x7f]') { throw 'WorkRoot deve estar sob TEMP e conter espaço e acento.' }
Assert-NoReparse $root
# New-Item (without -Force) fails if someone already created this directory.
[void](New-Item -ItemType Directory -Path $root -ErrorAction Stop)
$ownerPath = Join-Path $root 'ownership.json'
Write-NewJson $ownerPath @{ schema_version = 1; run_id = $runId; root = $root; app_id = $appId; preexisting_appid = $false }
$installDir = Join-Path $root 'Aplicativo ação'
$dataDir = Join-Path $root 'Dados próprios'
$appExe = Join-Path $installDir 'khcom-desktop.exe'
$uninstaller = Join-Path $installDir 'unins000.exe'
$configPath = Join-Path $dataDir 'config.json'
$saveFixture = Join-Path $dataDir 'saves\B8CE\B8CE-sram-v1\perfil-1.khcs'
$fixtureHash = $null
try {
    $peReport = Join-Path $root 'pe-imports.json'
    Invoke-OwnedProcess $pythonPath @((Join-Path $PSScriptRoot 'audit_windows_pe.py'), '--package', $payloadPath,
        '--system32', (Join-Path $env:SystemRoot 'System32'), '--report', $peReport) 'pe-audit'
    Invoke-Install 'install'
    Invoke-App 'start'
    # Only this owned fixture is changed. It intentionally is NOT a valid save.
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $config.volume = 37; $config.scale = 2
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 10), $utf8)
    [void](New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($saveFixture)) -Force)
    Write-NewText $saveFixture "KHCOM SYNTHETIC FILE PRESERVATION FIXTURE - NOT A GAME SAVE`n$runId`n"
    $fixtureHash = Hash-File $saveFixture
    Write-NewJson (Join-Path $root 'fixtures.json') @{ save = $saveFixture; sha256 = $fixtureHash
        game_save_validated = $false; config_volume = 37; config_scale = 2; data_directory_is_explicit = $true }
    $beforeUpdateConfig = Hash-File $configPath
    Invoke-Install 'same-version-reinstall'
    if ((Hash-File $configPath) -ne $beforeUpdateConfig) { throw 'Reinstalação alterou bytes da configuração.' }
    Assert-ConfigAndFixture
    Invoke-App 'restart-after-reinstall'
    Assert-ConfigAndFixture
    $beforeUninstallConfig = Hash-File $configPath
    Invoke-Uninstall 'uninstall'
    Assert-ConfigAndFixture
    if ((Hash-File $configPath) -ne $beforeUninstallConfig) { throw 'Desinstalação alterou bytes da configuração.' }
} catch {
    $script:failure = $_.Exception.Message
} finally {
    if ($script:installAttempted -and -not $script:removed -and -not $script:processUnresolved) {
        try { Invoke-Uninstall 'failure-cleanup' }
        catch { $script:cleanupFailure = $_.Exception.Message }
    }
    $files = @()
    foreach ($file in (Get-ChildItem -LiteralPath $root -File -Recurse -Force | Sort-Object FullName)) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
        $files += @{ path = [IO.Path]::GetRelativePath($root, $file.FullName); size = $file.Length; sha256 = Hash-File $file.FullName }
    }
    $report = @{ schema_version = 1; kind = 'windows-installer-smoke'; run_id = $runId; root = $root
        installer_sha256 = $installerHash; installer_build_sha256 = Hash-File $buildPath
        payload_manifest_sha256 = $manifestHash; update_kind = 'same-artifact-same-version-reinstall'
        producer_sha256 = @{ script = Hash-File $PSCommandPath
            pe_parser = Hash-File (Join-Path $PSScriptRoot 'khcom/windows_pe.py')
            pe_cli = Hash-File (Join-Path $PSScriptRoot 'audit_windows_pe.py')
            installer_definition = Hash-File (Join-Path $PSScriptRoot '../packaging/windows.iss') }
        smoke_passed = ($null -eq $script:failure -and $script:removed); failure = $script:failure
        cleanup_failure = $script:cleanupFailure; process_completion_unresolved = $script:processUnresolved
        uninstalled = $script:removed; events = @($script:events.ToArray()); retained_files = $files
        clean_machine_verified = $false; real_game_save_verified = $false; release_approved = $false
        limitations = @('Hosted runner already has SDKs/runtimes; restricted PATH is not a clean machine.',
            'No ROM, gameplay, audible audio, controller, first-run patch or full translation tested.',
            'Synthetic save-directory file and explicit --data-dir; default SDL profile path not exercised.',
            'No version-to-version migration or default shortcut/UI interaction tested.',
            'PE imports plus sampled modules do not cover every dynamic load path or attest system provenance.') }
    Write-NewJson (Join-Path $root 'result.json') $report
    Write-NewJson $reportFile $report
    Write-Output "KHCOM_SMOKE_ROOT=$root"
    Write-Output "KHCOM_SMOKE_PASSED=$($report.smoke_passed)"
}
if ($null -ne $script:failure -or -not $script:removed) { throw "Smoke incompleto: $($script:failure); cleanup: $($script:cleanupFailure). Evidência: $reportFile" }
