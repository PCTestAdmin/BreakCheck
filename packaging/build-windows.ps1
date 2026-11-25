param([string]$Iscc)
$ErrorActionPreference = 'Stop'
# ProgramFiles(x86) requires braced syntax in PowerShell.
if (-not $PSBoundParameters.ContainsKey('Iscc')) {
    $Iscc = Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'
    if (-not (Test-Path -LiteralPath $Iscc)) {
        $Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    }
}
if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit PowerShell and Python.' }
if (-not (Test-Path -LiteralPath $Iscc)) { throw 'Inno Setup 6 ISCC.exe was not found. Pass -Iscc with its full path.' }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $version = (python -c "from breakcheck import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
    python -m pip install -r packaging/requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed' }
    python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }
    python packaging/build-icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    python -m PyInstaller --noconfirm --clean --onefile --icon packaging/BreakCheck.ico --windowed --noupx --name BreakCheck --paths . --hidden-import pystray._win32 --hidden-import watchdog.observers.read_directory_changes packaging/gui_entry.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
    python -m PyInstaller --noconfirm --clean --onefile --icon packaging/BreakCheck.ico --console --noupx --name BreakCheckCLI --paths . --hidden-import pystray._win32 --hidden-import watchdog.observers.read_directory_changes packaging/cli_entry.py
    if ($LASTEXITCODE -ne 0) { throw 'CLI build failed' }
    New-Item -ItemType Directory -Force release | Out-Null
    # Remove only known previous outputs, not unrelated user files.
    @('release\BreakCheck-Setup.exe', 'release\BreakCheck-Portable.zip', 'release\SHA256SUMS.txt') | ForEach-Object {
        if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Force }
    }
    & $Iscc "/DAppVersion=$version" packaging/BreakCheck.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    $portable = "release\BreakCheck-Portable.zip"
    Compress-Archive -Path dist\BreakCheck.exe,dist\BreakCheckCLI.exe,LICENSE,README.md -DestinationPath $portable -Force
    $setup = "release\BreakCheck-Setup.exe"
    $lines = @($setup, $portable) | ForEach-Object {
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_
        '{0}  {1}' -f $hash.Hash.ToLowerInvariant(), (Split-Path $_ -Leaf)
    }
    $lines | Set-Content -Encoding ascii release\SHA256SUMS.txt
    Write-Host "Build outputs: $setup, $portable, release\SHA256SUMS.txt"
} finally {
    Pop-Location
}
