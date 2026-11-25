$ErrorActionPreference = 'Stop'
# Exit code 2 is expected for a scan with detected dependencies.
$PSNativeCommandUseErrorActionPreference = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    function Invoke-CheckedProcess([string]$Executable, [string[]]$Arguments) {
        $p = Start-Process -FilePath $Executable -ArgumentList $Arguments -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "$Executable failed (exit $($p.ExitCode))" }
    }
    $version = (python -c "from breakcheck import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Version lookup failed' }
    $cli = (Resolve-Path dist\BreakCheckCLI.exe).Path
    $reported = & $cli --version
    if ($LASTEXITCODE -ne 0 -or $reported.Trim() -ne $version) { throw 'CLI version check failed' }
    $json = & $cli check examples/demo assets/logo.svg --json
    $scanExit = $LASTEXITCODE
    $report = ($json -join [Environment]::NewLine) | ConvertFrom-Json
    if ($scanExit -ne 2 -or $report.direct.Count -ne 3) { throw 'Bundled CLI scan failed' }
    $global:LASTEXITCODE = 0
    Invoke-CheckedProcess (Resolve-Path dist\BreakCheck.exe).Path @('--self-test')
    $setup = (Resolve-Path "release\BreakCheck-$version-windows-x64-setup.exe").Path
    $install = Join-Path $env:TEMP ("BreakCheck Smoke " + [guid]::NewGuid().ToString('N'))
    $keys = @('Software\Classes\*\shell\BreakCheck.Inspect', 'Software\Classes\Directory\shell\BreakCheck.Inspect')
    try {
        Invoke-CheckedProcess $setup @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=""$install""", '/TASKS=explorer')
        $app = Join-Path $install 'BreakCheck.exe'
        if (-not (Test-Path -LiteralPath $app)) { throw 'Installed application missing' }
        foreach ($key in $keys) {
            $reg = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("$key\command")
            if ($null -eq $reg) { throw "Explorer registration missing: $key" }
            try {
                $expected = '"' + $app + '" --inspect="%1"'
                if ($reg.GetValue('') -ne $expected) { throw "Incorrect Explorer command: $key" }
            } finally { $reg.Dispose() }
        }
        Invoke-CheckedProcess $app @('--self-test')
    } finally {
        $uninstaller = Join-Path $install 'unins000.exe'
        if (Test-Path -LiteralPath $uninstaller) {
            Invoke-CheckedProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
        }
    }
    if (Test-Path -LiteralPath (Join-Path $install 'BreakCheck.exe')) { throw 'Uninstall left application behind' }
    foreach ($key in $keys) {
        $reg = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($key)
        if ($null -ne $reg) { $reg.Dispose(); throw "Uninstall left Explorer registration: $key" }
    }
    Write-Host 'Windows package smoke tests passed.'
} finally {
    Pop-Location
}
