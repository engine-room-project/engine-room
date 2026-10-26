# Read-only tool discovery. Never execute a candidate or scan a user's drive.
function FindTools([string]$userHome = $env:USERPROFILE, [string]$localData = $env:LOCALAPPDATA, [hashtable]$commands = $null) {
    if ([string]::IsNullOrWhiteSpace($userHome) -or [string]::IsNullOrWhiteSpace($localData)) {
        throw 'Your Windows user folders could not be found. Choose a tool executable explicitly.'
    }
    $catalog = @(
        @{ id='opencode'; label='OpenCode'; candidates=@((Join-Path $localData 'Programs/@opencode-aidesktop/OpenCode.exe'), (Join-Path $userHome 'AppData/Roaming/npm/opencode.cmd')); command='opencode'; supported=$true }
        @{ id='codex'; label='Codex CLI'; candidates=@((Join-Path $localData 'Programs/OpenAI/Codex/bin/codex.exe')); command='codex'; supported=$true }
        @{ id='claude'; label='Claude Code'; candidates=@((Join-Path $userHome '.local/bin/claude.exe')); command='claude'; supported=$false }
        @{ id='comfyui'; label='ComfyUI'; candidates=@((Join-Path $localData 'Programs/Comfy Desktop/Comfy Desktop.exe')); command='comfyui'; supported=$false }
        @{ id='cursor'; label='Cursor'; candidates=@((Join-Path $localData 'Programs/cursor/Cursor.exe')); command='cursor'; supported=$false }
        @{ id='antigravity'; label='Antigravity'; candidates=@((Join-Path $localData 'Programs/antigravity/Antigravity.exe')); command='antigravity'; supported=$false }
    )
    foreach ($tool in $catalog) {
        $path = $tool.candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $path) {
            if ($null -ne $commands) { $path = $commands[$tool.command] }
            else {
                $found = Get-Command ($tool.command + '.exe'),($tool.command + '.cmd'),($tool.command + '.ps1') -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($found) { $path = $found.Source }
            }
        }
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            $native = [IO.Path]::GetExtension($path) -ieq '.exe'
            $automatic = [bool]$tool.supported -and $native
            $status = if (-not $tool.supported) { 'Detected. Automatic connection has not been validated for this tool.' }
                elseif (-not $native) { 'Detected. Choose a native executable; script launchers are not validated yet.' }
                else { 'Detected. The session connection and tool compatibility still need checking.' }
            [pscustomobject]@{id=$tool.id; label=$tool.label; path=[IO.Path]::GetFullPath($path); automatic=$automatic; registered=$false; status=$status}
        }
    }
}
