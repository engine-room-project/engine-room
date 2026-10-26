$ErrorActionPreference='Stop'
# This owned worker must expire even if its Python caller is closed.
Add-Type -TypeDefinition 'public static class PlannerDeadline { public static void Arm() { var worker=new System.Threading.Thread(()=>{System.Threading.Thread.Sleep(35000);System.Environment.Exit(1);}); worker.IsBackground=true; worker.Start(); } }'
[PlannerDeadline]::Arm()
[Console]::InputEncoding=New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$OutputEncoding=[Console]::OutputEncoding
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'models.ps1')
try {
 $raw=[Console]::In.ReadToEnd()
 if ([Text.Encoding]::UTF8.GetByteCount($raw) -gt 262144) { throw 'Input too large' }
 $request=$raw|ConvertFrom-Json
 $data=$request.discovery
 if ($request.mode -ceq 'describe') {
  $result=DescribeCheckpoint $data.info
 } elseif ($request.mode -ceq 'plan') {
  if ($request.engine -ceq 'llama.cpp') {
   if (-not ($request.variant -is [string]) -or -not $request.variant) { throw 'Choose a GGUF variant explicitly' }
   $plan=GgufPlan $data.model_id $data.info $data.base_config $request.variant
  } elseif ($request.engine -ceq 'vLLM') {
   $plan=ModelPlan $data.model_id $data.info $data.config
  } else { throw 'Choose a runtime explicitly' }
  if ($null -ne $request.context) {
   $context=0L
   if (-not [long]::TryParse([string]$request.context,[ref]$context) -or $context -lt 8192 -or $context -gt [Math]::Min(1048576,$plan.nativeContext)) { throw 'Conversation capacity is outside published limits' }
   $plan.context=$context
  }
  $required=[Math]::Ceiling(($plan.weightBytes+$plan.overheadBytes+$plan.kvBytesPerToken*$plan.context)/0.92)
  $result=@{plan=$plan;estimated_memory_bytes=$required}
 } else { throw 'Unsupported planning mode' }
 $response=@{ok=$true;result=$result}|ConvertTo-Json -Depth 20 -Compress
 if ([Text.Encoding]::UTF8.GetByteCount($response) -gt 262144) { throw 'Output too large' }
 [Console]::WriteLine($response)
} catch {
 [Console]::WriteLine('{"ok":false,"error":"Model planning failed. Check the chosen format, variant and published metadata. Nothing was rented."}')
 exit 1
}
