$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../models.ps1"
$script:checks = 0
function Check($name, $condition) { if (-not $condition) { throw "FAIL: $name" }; $script:checks++ }
function Reject($action) { $bad = $false; try { & $action | Out-Null } catch { $bad = $true }; Check 'Expected rejection' $bad }
$config = [pscustomobject]@{ model_type='qwen3'; torch_dtype='bfloat16'; max_position_embeddings=262144; num_hidden_layers=32; num_key_value_heads=8; head_dim=128 }
$info = [pscustomobject]@{ sha=('a'*40); siblings=@([pscustomobject]@{rfilename='model.safetensors';size=14GB}) }
$plan = ModelPlan 'example/model' $info $config
Check 'Published precision preserved' ($plan.weightBytes -eq 14GB -and $plan.dtype -eq 'bfloat16')
Check 'Safetensors sizes reach the remote storage plan' ($plan.fileSizes['model.safetensors'] -eq 14GB)
Check 'Native context preserved' ($plan.nativeContext -eq 262144)
Reject { ModelPlan 'example/model' ([pscustomobject]@{sha=('a'*40);siblings=@([pscustomobject]@{rfilename='model unsafe.safetensors';size=100})}) $config }
Check 'GPU planning is independent of provider' ((GpuPlan $plan 80).context -eq 262144)
$gguf = [pscustomobject]@{sha=('b'*40);pipeline_tag='text-generation';siblings=@([pscustomobject]@{rfilename='m-00002-of-00002.gguf';size=10},[pscustomobject]@{rfilename='m-00003-of-00002.gguf';size=10})}
Check 'Bad shard count cannot masquerade as completeness' (-not (DescribeCheckpoint $gguf).variants[0].complete)
Reject { GgufPlan 'example/gguf' $gguf $config }
$gguf.siblings[0].rfilename = 'm-00001-of-00002.gguf'; $gguf.siblings[1].rfilename = 'm-00002-of-00002.gguf'
Check 'Complete shard set accepted' ((DescribeCheckpoint $gguf).variants[0].complete)
$checked = GgufPlan 'example/gguf' $gguf $config
Check 'Published file sizes reach remote plan' ($checked.fileSizes.Count -eq 2 -and $checked.weightBytes -eq 20)
$gguf.siblings = @([pscustomobject]@{rfilename='model Q4.gguf';size=20})
Reject { GgufPlan 'example/gguf' $gguf $config }
Reject { ValidateGgufFiles @('model.gguf') 'projector bad.gguf' }
Reject { ValidateGgufFiles @('../model.gguf') }
Check 'Untested model explicitly experimental' ($checked.warning -like 'Experimental:*')
. "$PSScriptRoot/../tools.ps1"
$testTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$toolFixture = Join-Path $testTempRoot ('engine-room-tools-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $toolFixture) { throw 'Temporary fixture unexpectedly exists.' }
try {
    [void][IO.Directory]::CreateDirectory($toolFixture)
    $nativeTool = Join-Path $toolFixture 'native synthetic.exe'
    $scriptTool = Join-Path $toolFixture 'do not execute.ps1'
    [IO.File]::WriteAllText($nativeTool, 'synthetic fixture, not executable')
    [IO.File]::WriteAllText($scriptTool, 'throw "Discovery executed a script"')
    $found = @(FindTools $toolFixture $toolFixture @{opencode=$nativeTool;codex=$scriptTool})
    Check 'Discovery reads candidates without executing them' ($found.Count -eq 2)
    Check 'Detection never claims connection registration' (@($found | Where-Object registered).Count -eq 0)
    Check 'Script launcher is detected but not automatically launched' (-not ($found | Where-Object id -eq 'codex').automatic)
    Check 'Native candidate is eligible for explicit connection checks' (($found | Where-Object id -eq 'opencode').automatic)
} finally {
    $checkedFixture = [IO.Path]::GetFullPath($toolFixture)
    if (-not $checkedFixture.StartsWith($testTempRoot, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($checkedFixture) -notlike 'engine-room-tools-*') { throw 'Unsafe temporary cleanup target.' }
    if (Test-Path -LiteralPath $checkedFixture) { Remove-Item -LiteralPath $checkedFixture -Recurse -Force }
}
Write-Output "$script:checks planning checks passed. No provider requests or rentals."
