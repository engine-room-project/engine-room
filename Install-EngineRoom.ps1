param([string]$Destination,[string]$ShortcutDirectory,[switch]$NoShortcut)
# Per-user source installation. Does not launch, authenticate, rent or edit runtime state.
$ErrorActionPreference='Stop'
$manifestPath=Join-Path $PSScriptRoot 'SOURCE_MANIFEST.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {throw 'Install from an inspected source package with its manifest.'}
if ((Get-Item -LiteralPath $manifestPath).Length -gt 1048576) {throw 'Source manifest is too large.'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.source_commit -cnotmatch '^[a-f0-9]{40}$') {throw 'Invalid source revision.'}
$revision=$manifest.source_commit.Substring(0,12)
$python=Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
& $python.Source -I -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'
if ($LASTEXITCODE -ne 0) {throw 'Install Python 3.12 or newer and reopen this installer.'}
if (-not $Destination) {
 if (-not $env:LOCALAPPDATA) {throw 'The per-user application directory is unavailable.'}
 $Destination=Join-Path $env:LOCALAPPDATA ('Programs/EngineRoom/'+$revision)
}
$shortcutPath=$null
if (-not $NoShortcut) {
 if (-not $ShortcutDirectory) {$ShortcutDirectory=[Environment]::GetFolderPath('Desktop')}
 if (-not (Test-Path -LiteralPath $ShortcutDirectory -PathType Container)) {throw 'The selected shortcut directory is unavailable.'}
 $shortcutPath=Join-Path $ShortcutDirectory ('Engine Room '+$revision+'.lnk')
 if (Test-Path -LiteralPath $shortcutPath) {throw 'A shortcut for this revision already exists. Preserve it or choose a new shortcut directory.'}
}
$result=& $python.Source -I (Join-Path $PSScriptRoot 'engine_room/install.py') --source $PSScriptRoot --destination $Destination
if ($LASTEXITCODE -ne 0) {throw 'Installation was not completed. Preserve any partial new directory for inspection; existing state was not changed.'}
$receipt=$result | ConvertFrom-Json
if (-not $NoShortcut) {
 $shell=New-Object -ComObject WScript.Shell
 $shortcut=$shell.CreateShortcut($shortcutPath)
 $shortcut.TargetPath=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
 $entry=Join-Path $receipt.destination 'EngineRoom.ps1'
 if ($entry.Contains('"')) {throw 'Invalid installation path.'}
 $shortcut.Arguments='-NoProfile -STA -File "'+$entry+'"'
 $shortcut.WorkingDirectory=$receipt.destination
 $shortcut.Description='Engine Room unpublished candidate - no provider configured automatically'
 $shortcut.Save()
}
Write-Output ('Installed source revision '+$receipt.source_commit+' at '+$receipt.destination)
Write-Output 'No provider was configured. Opening Engine Room does not rent a GPU. Runtime state was preserved.'
