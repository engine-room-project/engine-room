import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name=="nt","Actual Windows WPF and PowerShell 5.1")
class DesktopUiTests(unittest.TestCase):
    def test_native_controls_and_bounded_child(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(["powershell.exe","-NoProfile","-STA","-File",str(root/"tests/test-desktop-ui.ps1")],cwd=root,capture_output=True,text=True,timeout=45)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertIn("cancellation checks passed",result.stdout)

    def test_persistent_session_duplex_and_limits(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="engine room session ") as folder:
            fixture=Path(folder)
            package=fixture/"engine_room"
            package.mkdir()
            (package/"__init__.py").write_text("")
            (package/"session_host.py").write_text("""import json, sys

def main():
    sys.stdout.reconfigure(encoding="utf-8",newline="\\n")
    first=json.loads(sys.stdin.buffer.readline())
    mode=first.get('mode')
    if mode=='oversize':
        sys.stdout.write('x'*262145+'\\n'); sys.stdout.flush(); return 0
    if mode=='flood':
        for _ in range(17):
            print('{}',flush=True)
        return 0
    print(json.dumps({'event':'ready','marker':first['marker']},ensure_ascii=False),flush=True)
    for line in sys.stdin.buffer:
        action=json.loads(line)['action']
        print(json.dumps({'event':action}),flush=True)
        if action=='stop': return 0
    return 0
""",encoding="utf-8")
            script=fixture/"exercise.ps1"
            script.write_text(r'''param($SourceRoot,$FixtureRoot,$Python)
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $SourceRoot 'desktop/BridgeJob.cs')
function Check($ok,$message) {if(-not $ok){throw $message}}
function Frame($session) {
 $until=[DateTime]::UtcNow.AddSeconds(10)
 do {$value=$session.Take(); if($value){return ($value|ConvertFrom-Json)}; Start-Sleep -Milliseconds 10} while([DateTime]::UtcNow -lt $until)
 throw 'No session frame'
}
function Done($session) {
 $until=[DateTime]::UtcNow.AddSeconds(10)
 while(-not $session.Complete -and [DateTime]::UtcNow -lt $until){Start-Sleep -Milliseconds 10}
 Check $session.Complete 'Owned helper did not finish'
}
$begin=(@{marker=[string][char]0x03bb}|ConvertTo-Json -Compress)+"`n"
$session=New-Object EngineRoom.SessionProcess($Python,$FixtureRoot,$begin,20)
try {
 $ready=Frame $session
 Check ($ready.event -eq 'ready' -and $ready.marker -eq [string][char]0x03bb) 'UTF8 duplex or spaced path failed'
 Start-Sleep -Milliseconds 300
 Check ($null -eq $session.Take()) 'Helper must not invent UI pulses'
 $session.Pulse(); Check ((Frame $session).event -eq 'pulse') 'Explicit UI pulse missing'
 $session.Close(); Check ((Frame $session).event -eq 'stop') 'Close must send stop'
 Done $session; Check (-not $session.Error) 'Clean close failed'
} finally {$session.Close()}
foreach($mode in @('oversize','flood')) {
 $begin=(@{mode=$mode}|ConvertTo-Json -Compress)+"`n"
 $session=New-Object EngineRoom.SessionProcess($Python,$FixtureRoot,$begin,20)
 try {Done $session; Check ([bool]$session.Error) 'Unbounded output must fail safely'} finally {$session.Close()}
}
$refused=$false
try {[void](New-Object EngineRoom.SessionProcess($Python,$FixtureRoot,'{}',20))} catch {$refused=$true}
Check $refused 'Unframed input must be refused before launch'
Write-Output 'Persistent session checks passed'
''',encoding="utf-8")
            result=subprocess.run(["powershell.exe","-NoProfile","-File",str(script),str(root),str(fixture),os.sys.executable],capture_output=True,text=True,timeout=50)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            self.assertIn("Persistent session checks passed",result.stdout)
