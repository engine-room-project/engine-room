$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'desktop/ui.ps1')
function Assert-Ui($condition,[string]$message) { if (-not $condition) { throw $message } }
$window=New-EngineRoomWindow
try {
 Show-DesktopStartup ([pscustomobject]@{python_ready=$true;ssh_ready=$true;controller_state='missing';message='Synthetic missing controller'})
 Assert-Ui ($script:ui.Fields.Count -eq 0) 'First start must not select a provider'
 $button=@($script:ui.Content.Children | Where-Object { $_ -is [Windows.Controls.Button] -and $_.Content -eq 'Set up controller' })[0]
 $button.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)))
 Assert-Ui ($script:ui.Fields.ContainsKey('host_key')) 'Setup button must open actual enrollment fields'
 Assert-Ui (-not $script:ui.Fields.independent_host_confirmed.IsChecked) 'Independence must never be preconfirmed'
 Reset-DesktopPage 'Synthetic form'
 [void](Add-DesktopField ([pscustomobject]@{name='flag';label='Flag';kind='boolean';required=$true}))
 [void](Add-DesktopField ([pscustomobject]@{name='choice';label='<do not parse as markup>';kind='choice';required=$true;choices=@([pscustomobject]@{value='example';label='Example'})}))
 [void](Add-DesktopField ([pscustomobject]@{name='optional';label='Optional';kind='text';required=$false}))
 $script:ui.Fields.choice.SelectedIndex=0
 $values=Get-DesktopValues
 Assert-Ui ($values.ContainsKey('flag') -and $values.flag -eq $false) 'False is a valid boolean selection'
 Assert-Ui ($values.choice -eq 'example') 'Choice must retain its stable value'
 Assert-Ui (-not $values.ContainsKey('optional')) 'Blank optional values must be omitted'
 $script:ui.Info=[pscustomobject]@{connectors=@([pscustomobject]@{id='synthetic';name='Example'});protection_healthy=$false}
 $script:ui.Connections=@(); Show-DesktopConnections
 Assert-Ui ($script:ui.Fields.connector_id.SelectedIndex -eq -1) 'Connector must not be preselected'
 Assert-Ui ($script:ui.Status.Text -like '*not healthy*') 'Unhealthy protection must be explicit'
 $session=[pscustomobject]@{Complete=$false;Closed=$false;Pulses=0;Frames=(New-Object 'System.Collections.Generic.Queue[string]');Commands=(New-Object 'System.Collections.Generic.Queue[string]')}
 $session|Add-Member ScriptMethod Command {param($frame) $this.Commands.Enqueue($frame); return $true}
 $session|Add-Member ScriptMethod Pulse {$this.Pulses++}
 $session|Add-Member ScriptMethod Close {$this.Closed=$true}
 $session|Add-Member ScriptMethod Take {if($this.Frames.Count){return $this.Frames.Dequeue()}; return $null}
 $clock=[pscustomobject]@{Elapsed=[pscustomobject]@{TotalSeconds=16.0};Stopped=$false}
 $clock|Add-Member ScriptMethod Stop {$this.Stopped=$true}
 $script:ui.Session=$session; $script:ui.SessionClock=$clock
 Update-DesktopSession
 Assert-Ui ($session.Pulses -eq 1) 'Live dispatcher must pulse the retained helper'
 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"state":"active"},"shutdown_confirmed":true}')
 Update-DesktopSession
 Assert-Ui (-not $script:ui.SessionConfirmed) 'Active receipt must never be described as off'
 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"state":"off"},"shutdown_confirmed":"true"}')
 Update-DesktopSession
 Assert-Ui (-not $script:ui.SessionConfirmed) 'String true must not prove shutdown'
 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"state":"active"},"shutdown_confirmed":false,"view":{"phase":"ready","ready":true}}')
 Update-DesktopSession
 Assert-Ui ($script:ui.Status.Text -like '*model is ready*' -and -not $script:ui.SessionConfirmed) 'Fresh readiness must not imply shutdown'
 Show-DesktopTool
 Assert-Ui ($script:ui.EmergencyStop.Visibility -eq 'Visible' -and -not $script:ui.Content.Children.Contains($script:ui.EmergencyStop)) 'Stop must remain outside the scrolling tool form'
 Assert-Ui ($script:ui.Fields.tool.SelectedIndex -eq -1 -and -not $script:ui.Fields.confirmed.IsChecked -and -not $script:ui.Fields.desktop_idle.IsChecked) 'Tool and approvals must have no defaults'
 $open=@($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.Button] -and $_.Content -eq 'Open selected tool'})[0]
 $clickTool=New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)
 $script:ui.Fields.tool.SelectedValue='codex'; $script:ui.Fields.executable.Text='C:/synthetic/codex.exe'; $script:ui.Fields.working_directory.Text='C:/synthetic/project'
 $open.RaiseEvent($clickTool); Assert-Ui ($session.Commands.Count -eq 0) 'Unchecked tool confirmation cannot send a command'
 $script:ui.Fields.confirmed.IsChecked=$true; $script:ui.Fields.desktop_idle.IsChecked=$true
 $open.RaiseEvent($clickTool); $open.RaiseEvent($clickTool)
 Assert-Ui ($session.Commands.Count -eq 1 -and -not $open.IsEnabled) 'Only one pending tool command is permitted'
 $command=$session.Commands.Dequeue()|ConvertFrom-Json
 Assert-Ui ($command.action -eq 'tool_launch' -and $command.confirmed -and $command.desktop_idle -and $command.tool -eq 'codex' -and -not $command.PSObject.Properties['token']) 'Command must carry explicit tool choices without relay secret'
 $session.Frames.Enqueue((@{event='tool_result';request_id=$command.request_id;opened=$true}|ConvertTo-Json -Compress))
 Update-DesktopSession
 Assert-Ui ($null -eq $script:ui.ToolPending -and $script:ui.ToolResult.Text -like '*session-only*') 'Matched tool result must reach UI without stopping rental'
 $clock.Elapsed.TotalSeconds=27; Update-DesktopSession
 Assert-Ui (-not $open.IsEnabled -and -not $script:ui.SessionReady) 'Stale readiness must disable tool launch'

 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"state":"active"},"shutdown_confirmed":false,"view":{"phase":"starting","ready":false}}')
 Update-DesktopSession
 Assert-Ui ($script:ui.Status.Text -like '*startup*') 'Starting must remain distinct from ready'
 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"state":"off"},"shutdown_confirmed":true}')
 Update-DesktopSession
 Assert-Ui ($script:ui.SessionConfirmed -and $script:ui.Status.Text -like '*confirmed*this rental is off*') 'Confirmed receipt must be displayed'
 $script:ui.SessionConfirmed=$false; $clock.Elapsed.TotalSeconds=80
 Update-DesktopSession
 Assert-Ui ($session.Closed -and $session.Pulses -eq 1) 'Stalled dispatcher must close instead of revive the lease'
 $session.Complete=$true; Update-DesktopSession
 Assert-Ui ($null -eq $script:ui.Session -and $clock.Stopped -and $script:ui.Status.Text -like '*not confirmed*') 'Helper exit must remain uncertain'
 $session.Complete=$false; $session.Closed=$false; $script:ui.Session=$session
 Show-DesktopCancellation 'synthetic-request'
 Assert-Ui (-not $script:ui.Fields.cancel_confirmed.IsChecked) 'Recovery cancellation must never be preconfirmed'
 $button=@($script:ui.Content.Children | Where-Object { $_ -is [Windows.Controls.Button] })[0]
 $button.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)))
 Assert-Ui ($script:ui.Status.Text -eq 'Confirm this cancellation first.' -and $null -eq $script:ui.Job) 'Unchecked cancellation must never contact a controller'
 $script:ui.Session=$null
 $script:ui.Info=[pscustomobject]@{connectors=@([pscustomobject]@{id='third';modes=@('rental')},[pscustomobject]@{id='existing';modes=@('attachment')})}
 $script:ui.Connections=@([pscustomobject]@{id='named';name='Synthetic connection';connector_id='third';account_id='synthetic-account'},[pscustomobject]@{id='attached';name='Existing machine';connector_id='existing'})
 Show-RentalConnections
 Assert-Ui ($script:ui.Fields.connection_id.SelectedIndex -eq -1 -and $script:ui.Fields.connection_id.Items.Count -eq 1) 'Rental connections must be capability filtered without defaults or provider IDs'
 $script:ui.RentalConnection=$script:ui.Connections[0]
 Show-RentalOffer ([pscustomobject]@{account_id='synthetic-account';price=$null;unit='CCU';rate_scope='account';balance=10;available=$null;storage_available_bytes=$null;install_bytes=1024;cost_details=[pscustomobject]@{storage_validation='before-installation'}})
 $text=($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.TextBlock]}|ForEach-Object {$_.Text}) -join ' '
 Assert-Ui ($text -like '*entire provider account*' -and $text -like '*before installation*' -and $text -like '*not publish a verified advance*') 'Offer must explain unknown rate, account scope and deferred storage'
 Assert-Ui (@($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.Button] -and $_.Content -like '*Start*'}).Count -eq 0) 'Offer browsing must not start a rental'
 $session.Complete=$false; $session.Closed=$false; $script:ui.Session=$session
 $script:ui.Session=$null; $script:ui.RentalSelection=@{engine='llama.cpp'}
 $script:ui.ModelDiscovery=[pscustomobject]@{model_id='example/model';info=[pscustomobject]@{sha=('a'*40)}}
 Show-RentalModelChoices ([pscustomobject]@{variants=@([pscustomobject]@{name='complete.gguf';label='Complete';complete=$true;sizesKnown=$true},[pscustomobject]@{name='broken.gguf';label='Incomplete';complete=$false;sizesKnown=$true})})
 Assert-Ui ($script:ui.Fields.variant.SelectedIndex -eq -1 -and $script:ui.Fields.variant.Items.Count -eq 1) 'Only complete GGUF variants are offered with no default'
 Assert-Ui ($script:ui.Fields.context.Text -eq '') 'Conversation capacity must be explicit'
 $session.Complete=$false; $session.Closed=$false; $script:ui.Session=$session
 $script:ui.Session=$null
 $script:ui.RentalConnection=[pscustomobject]@{id='named';name='Synthetic';account_id='synthetic-account'}
 $script:ui.RentalSelection=@{engine='llama.cpp';region='original'}
 $script:ui.RentalModelPlan=[pscustomobject]@{plan=[pscustomobject]@{id='example/model';revision=('a'*40);engine='llama.cpp';context=8192};warning='Experimental synthetic model'}
 $script:ui.RentalQuote=[pscustomobject]@{account_id='synthetic-account';price=1.0;unit='USD';rate_scope='account';balance=10;observed_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds();cost_details=$null}
 $script:ui.RentalCapacity=[pscustomobject]@{required_gpu_bytes=1000;required_storage_bytes=2000;gpu_check_deferred=$true;storage_check_deferred=$true}
 $savedStart=${function:Start-DesktopSession}; $script:RentalCaptured=$null; $script:RentalStarts=0
 try {
  function Start-DesktopSession($request,[bool]$confirmed) { $script:RentalCaptured=$request; $script:RentalStarts++ }
  Show-RentalConfirmation
  Assert-Ui (-not $script:ui.Fields.spending_confirmed.IsChecked -and $script:ui.Fields.rate_ceiling.Text -eq '' -and $script:ui.Fields.duration_minutes.Text -eq '') 'Spending approval and limits must have no defaults'
  $startButton=@($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.Button] -and $_.Content -eq 'Start protected rental'})[0]
  $click=New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)
  $startButton.RaiseEvent($click); Assert-Ui ($script:RentalStarts -eq 0) 'Unchecked approval must not start'
  foreach($key in @('spending_confirmed','protection_confirmed','experimental_confirmed')) {$script:ui.Fields[$key].IsChecked=$true}
  $script:ui.Fields.duration_minutes.Text='5'; $script:ui.Fields.rate_ceiling.Text='NaN'
  $startButton.RaiseEvent($click); Assert-Ui ($script:RentalStarts -eq 0) 'Nonfinite rate must not start'
  $script:ui.Fields.rate_ceiling.Text='0.5'
  $startButton.RaiseEvent($click); Assert-Ui ($script:RentalStarts -eq 0) 'Below offered rate must not start'
  $script:ui.Fields.rate_ceiling.Text='2'
  $script:ui.Confirmation.approved_quote.observed_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-121
  $startButton.RaiseEvent($click); Assert-Ui ($script:RentalStarts -eq 0 -and $script:ui.Status.Text -like '*expired*') 'Expired quote requires new review'
  $script:ui.Confirmation.approved_quote.observed_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $script:ui.RentalSelection.region='changed-after-review'
  $startButton.RaiseEvent($click)
  Assert-Ui ($script:RentalStarts -eq 1 -and $script:RentalCaptured.duration_seconds -eq 300 -and $script:RentalCaptured.rate_ceiling -eq 2 -and $script:RentalCaptured.selection.region -eq 'original') 'Confirmed exact snapshot must reach persistent session once'
  $startButton.RaiseEvent($click); Assert-Ui ($script:RentalStarts -eq 1) 'The reviewed confirmation must submit at most once'
 } finally { Set-Item Function:Start-DesktopSession $savedStart }
 $script:ui.Session=$session

 $script:ui.Session=$null; $script:ui.Job=$null
 Show-AttachmentConnections
 Assert-Ui ($script:ui.Fields.connection_id.SelectedIndex -eq -1 -and $script:ui.Fields.connection_id.Items.Count -eq 1) 'Existing-machine selection must filter capabilities without defaults'
 $script:ui.AttachmentConnection=$script:ui.Connections[1]
 $target=[pscustomobject]@{account_id='existing-account';resource_id='existing-resource';model_id='chosen-model'}
 $savedStart=${function:Start-DesktopSession}; $script:AttachmentStarts=0; $script:AttachmentCaptured=$null
 try {
  function Start-DesktopSession($request,[bool]$confirmed,[string]$mode) {Assert-Ui ($mode -eq 'attachment') 'Attachment must use distinct helper mode'; $script:AttachmentCaptured=$request; $script:AttachmentStarts++}
  Show-AttachmentConfirmation $target
  Assert-Ui (-not $script:ui.Fields.access_confirmed.IsChecked -and -not $script:ui.Fields.costs_confirmed.IsChecked) 'Existing-machine access and continued costs require explicit approval'
  $button=@($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.Button] -and $_.Content -eq 'Connect existing model'})[0]
  $button.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)))
  Assert-Ui ($script:AttachmentStarts -eq 0) 'Unchecked existing-model review cannot connect'
  $script:ui.Fields.access_confirmed.IsChecked=$true; $script:ui.Fields.costs_confirmed.IsChecked=$true
  Assert-Ui ($script:ui.Fields.context.Text -eq '') 'Existing-model conversation limit must be explicit'
  $script:ui.Fields.context.Text='8192'
  $target.model_id='changed-after-review'
  $button.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)))
  $button.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)))
  Assert-Ui ($script:AttachmentStarts -eq 1 -and $script:AttachmentCaptured.approved_target.model_id -eq 'chosen-model') 'Existing-model review must freeze exact target and submit once'
 } finally {Set-Item Function:Start-DesktopSession $savedStart}
 $script:ui.Session=$session; $session.Complete=$false; $session.Closed=$false
 $script:ui.SessionMode='attachment'; $script:ui.SessionConfirmed=$false; $script:ui.SessionStopping=$false
 $clock.Elapsed.TotalSeconds=16; $script:ui.SessionPulse=16
 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"mode":"attachment","state":"off"},"shutdown_confirmed":true}')
 Update-DesktopSession
 Assert-Ui (-not $script:ui.SessionConfirmed -and $session.Closed) 'An attachment cannot assert machine shutdown'
 $script:ui.SessionStopping=$false
 $session.Frames.Enqueue('{"event":"snapshot","receipt":{"mode":"attachment","state":"detached"},"shutdown_confirmed":false}')
 Update-DesktopSession
 Assert-Ui ($script:ui.SessionConfirmed -and $script:ui.Status.Text -like '*billing remain running*') 'Confirmed attachment disconnect must explain continued machine billing'
 Show-DesktopCancellation 'existing-request' 'attachment'
 $text=($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.TextBlock]}|ForEach-Object {$_.Text}) -join ' '
 Assert-Ui ($text -like '*closes only Engine Room access*' -and -not $script:ui.Fields.cancel_confirmed.IsChecked) 'Attachment recovery must be explicit and local-only'
 $script:ui.SessionMode='rental'
 $owned=[pscustomobject]@{Stopped=$false}; $owned | Add-Member ScriptMethod Stop { $this.Stopped=$true }
 $script:ui.Job=$owned; $window.Close(); Assert-Ui $owned.Stopped 'Closing must cancel the retained owned job'
 Assert-Ui $session.Closed 'Closing must close the retained persistent helper'
 $script:ui.Session=$null; $script:ui.Job=$null
 $script:ui.Info=[pscustomobject]@{connectors=@([pscustomobject]@{id='storage-capable';capabilities=@('persistent_storage')},[pscustomobject]@{id='other';capabilities=@()})}
 $script:ui.Connections=@([pscustomobject]@{id='storage-connection';name='Synthetic storage';connector_id='storage-capable'},[pscustomobject]@{id='other-connection';name='Other';connector_id='other'})
 Show-StorageConnections
 Assert-Ui ($script:ui.Fields.connection_id.Items.Count -eq 1 -and $script:ui.Fields.connection_id.SelectedIndex -eq -1) 'Storage uses capabilities and never selects a connection automatically'
 $script:ui.StorageConnection=$script:ui.Connections[0]
 $script:ui.StorageSelection=@{size_gb=50;data_center='TEST-1';storage_type='STANDARD'}
 $quote=[pscustomobject]@{account_id='synthetic-account';size_gb=50;data_center='TEST-1';storage_type='STANDARD';monthly_usd=3.5;observed_at=1000;source='https://storage.invalid/pricing'}
 Show-StorageConfirmation $quote
 Assert-Ui (-not $script:ui.Fields.creation_confirmed.IsChecked -and -not $script:ui.Fields.costs_confirmed.IsChecked) 'Storage approvals must be unchecked'
 $originalRequest=(Get-Item Function:Start-DesktopRequest).ScriptBlock
 $script:StorageCalls=New-Object 'System.Collections.Generic.List[object]'
 function Start-DesktopRequest($request,[scriptblock]$callback) {$script:StorageCalls.Add($request)}
 try {
  $create=@($script:ui.Content.Children|Where-Object {$_ -is [Windows.Controls.Button] -and $_.Content -eq 'Create reviewed storage once'})[0]
  $click=New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent)
  $create.RaiseEvent($click)
  Assert-Ui ($script:StorageCalls.Count -eq 0) 'Unchecked storage approvals cannot submit'
  $script:ui.Fields.creation_confirmed.IsChecked=$true; $script:ui.Fields.costs_confirmed.IsChecked=$true
  $quote.monthly_usd=999; $script:ui.StorageSelection.size_gb=999
  $create.RaiseEvent($click); $create.RaiseEvent($click)
  Assert-Ui ($script:StorageCalls.Count -eq 1) 'Storage creation must submit only once per review'
  Assert-Ui ($script:StorageCalls[0].action -eq 'storage_begin' -and $script:StorageCalls[0].params.request.approved_quote.monthly_usd -eq 3.5 -and $script:StorageCalls[0].params.request.selection.size_gb -eq 50) 'Submission must retain frozen reviewed quote and target'
  Show-StorageRecord 'storage-synthetic' $null
  Assert-Ui (-not $script:ui.Fields.identity_confirmed.IsChecked -and -not $script:ui.Fields.cancel_confirmed.IsChecked) 'Manual identity and delayed cancellation need separate unchecked approvals'
  $saved=[pscustomobject]@{operation_id='storage-synthetic';state='known';resource_id='saved-volume'}
  Show-StorageObservation ([pscustomobject]@{record=$saved;observation=[pscustomobject]@{status='absent';resource_id='saved-volume';candidates=@()}})
  Assert-Ui ($script:ui.Status.Text -like '*absent*' -and $script:ui.Status.Text -like '*does not verify your bill*') 'Absent observation must not claim billing closure'
  Show-StorageObservation ([pscustomobject]@{record=$saved;observation=[pscustomobject]@{status='unresolved';resource_id=$null;candidates=@([pscustomobject]@{id='candidate-volume'})}})
  Assert-Ui ($script:ui.Status.Text -like '*do not prove ownership*' -and $script:ui.Fields.resource_id.Text -eq '') 'Candidates must not be selected or adopted automatically'

 } finally {Set-Item Function:Start-DesktopRequest $originalRequest}
} finally { $window.Close(); $script:ui.Timer.Stop() }

$oldData=$env:ENGINE_ROOM_DATA_DIR; $folder=Join-Path ([IO.Path]::GetTempPath()) ('engine-room-ui-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($folder)
try {
 $env:ENGINE_ROOM_DATA_DIR=$folder
 $python=(Get-Command python -CommandType Application | Select-Object -First 1).Source
 $request='{"action":"startup"}'+[Environment]::NewLine
 $job=New-Object EngineRoom.DesktopJob($python,$root,$request,10000)
 $until=[DateTime]::UtcNow.AddSeconds(15)
 while (-not $job.Complete -and [DateTime]::UtcNow -lt $until) { Start-Sleep -Milliseconds 20 }
 Assert-Ui $job.Complete 'Actual bridge job must finish'
 Assert-Ui (-not $job.Error) 'Actual bridge startup failed'
 $response=$job.Output | ConvertFrom-Json
 Assert-Ui ($response.ok -and $response.result.controller_state -eq 'missing') 'Actual child must use isolated first-run state'
 Assert-Ui (@(Get-ChildItem -LiteralPath $folder).Count -eq 0) 'First run must create no provider state'
 $window=New-EngineRoomWindow; $script:SmokeResult=$null
 Start-DesktopRequest @{action='startup'} { param($result) $script:SmokeResult=$result }
 $script:SmokeFrame=New-Object Windows.Threading.DispatcherFrame
 $script:SmokeUntil=[DateTime]::UtcNow.AddSeconds(15)
 $pump=New-Object Windows.Threading.DispatcherTimer; $pump.Interval=[TimeSpan]::FromMilliseconds(20)
 $pump.Add_Tick({ if ($script:SmokeResult -or [DateTime]::UtcNow -gt $script:SmokeUntil) { $script:SmokeFrame.Continue=$false } })
 $pump.Start(); [Windows.Threading.Dispatcher]::PushFrame($script:SmokeFrame); $pump.Stop()
 Assert-Ui ($script:SmokeResult.controller_state -eq 'missing') 'UI dispatcher must deliver real child completion'
 $window.Close(); Assert-Ui (-not $script:ui.Timer.IsEnabled) 'Closing must stop the owned UI timer'
 $job=New-Object EngineRoom.DesktopJob($python,$root,$request,10000); $job.Stop()
 $until=[DateTime]::UtcNow.AddSeconds(15)
 while (-not $job.Complete -and [DateTime]::UtcNow -lt $until) { Start-Sleep -Milliseconds 20 }
 Assert-Ui ($job.Complete -and $job.Error) 'Owned child cancellation must finish with a safe error'
} finally {
 $env:ENGINE_ROOM_DATA_DIR=$oldData
 # Only the exact newly created temporary directory, nonrecursive and expected empty.
 if (@(Get-ChildItem -LiteralPath $folder).Count -eq 0) { [IO.Directory]::Delete($folder) }
}
Write-Output 'Windows WPF controls, first-run child process and cancellation checks passed.'
