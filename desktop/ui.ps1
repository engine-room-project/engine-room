Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
if (-not ('EngineRoom.DesktopJob' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'BridgeJob.cs') }
$script:ReleaseRoot=Split-Path $PSScriptRoot -Parent
function New-EngineRoomWindow {
 [xml]$xaml=@'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="Engine Room" Width="1080" Height="780" MinWidth="820" MinHeight="640" Background="#F7FAFC" FontFamily="Segoe UI" FontSize="14" Foreground="#12324A" WindowStartupLocation="CenterScreen">
 <Window.Resources>
  <Style TargetType="Button"><Setter Property="Padding" Value="16,9"/><Setter Property="Margin" Value="0,6,10,6"/><Setter Property="MinHeight" Value="38"/></Style>
  <Style TargetType="TextBox"><Setter Property="Padding" Value="8,6"/><Setter Property="MinHeight" Value="34"/></Style>
  <Style TargetType="ComboBox"><Setter Property="Padding" Value="8,6"/><Setter Property="MinHeight" Value="34"/></Style>
 </Window.Resources>
 <Grid Margin="28"><Grid.ColumnDefinitions><ColumnDefinition Width="190"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
  <StackPanel Margin="0,0,24,0"><TextBlock Text="Engine Room" FontSize="25" FontWeight="SemiBold" Margin="0,0,0,28"/><TextBlock Text="Your controller" FontWeight="SemiBold" Margin="0,0,0,10"/><TextBlock Text="Named connections" Margin="0,0,0,10"/><Separator Margin="0,10,0,18"/><TextBlock Text="Rent a GPU" Margin="0,0,0,10"/><TextBlock Text="Connect an existing machine" TextWrapping="Wrap"/><TextBlock Text="Existing machines are never shut down by rental cleanup." TextWrapping="Wrap" Foreground="#526876" Margin="0,28,0,0"/></StackPanel>
  <Grid Grid.Column="1"><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
   <StackPanel><TextBlock x:Name="Heading" Text="Connect your controller" FontSize="29" FontWeight="SemiBold"/><TextBlock Text="Keep model access private and shutdown protection independent of this computer." TextWrapping="Wrap" Margin="0,8,0,18"/></StackPanel>
   <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto"><StackPanel x:Name="Content" Margin="0,0,16,0"/></ScrollViewer>
   <Border Grid.Row="2" BorderBrush="#DCE5EA" BorderThickness="0,1,0,0" Padding="0,14,0,0"><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><TextBlock x:Name="Status" Text="Checking local prerequisites..." TextWrapping="Wrap" VerticalAlignment="Center"/><Button x:Name="EmergencyStop" Grid.Column="1" Content="Stop rental" Visibility="Collapsed" Margin="16,0,0,0" VerticalAlignment="Center"/></Grid></Border>
  </Grid>
 </Grid>
</Window>
'@
 $window=[Windows.Markup.XamlReader]::Load((New-Object Xml.XmlNodeReader $xaml))
 $script:ui=@{ Window=$window; Content=$window.FindName('Content'); Heading=$window.FindName('Heading'); Status=$window.FindName('Status'); EmergencyStop=$window.FindName('EmergencyStop'); Job=$null; Callback=$null; Fields=@{}; Info=$null; Connections=@(); Session=$null; SessionMode='rental'; SessionClock=$null; SessionPulse=0.0; SessionConfirmed=$false; SessionStopping=$false; SessionReady=$false; ReadyUntil=0.0; ToolPending=$null; ToolLaunchButton=$null; ToolFormButton=$null; ToolResult=$null }
 $script:ui.EmergencyStop.Add_Click({ Stop-DesktopSession })
 $timer=New-Object Windows.Threading.DispatcherTimer; $timer.Interval=[TimeSpan]::FromMilliseconds(100)
 $timer.Add_Tick({
  Update-DesktopSession
  if ($null -eq $script:ui.Job -or -not $script:ui.Job.Complete) { return }
  $job=$script:ui.Job; $callback=$script:ui.Callback; $script:ui.Job=$null; $script:ui.Callback=$null; $script:ui.Content.IsEnabled=$true
  try {
   if ($job.Error) { $script:ui.Status.Text=$job.Error; return }
   $response=$job.Output | ConvertFrom-Json -ErrorAction Stop
   if (-not $response.ok) { $script:ui.Status.Text=$response.error; return }
   & $callback $response.result
  } catch { $script:ui.Status.Text='The request could not be verified. Check controller access and preserve recovery records.' }
 })
 $script:ui.Timer=$timer; $timer.Start(); $window.Add_Closed({ if ($script:ui.Session) { $script:ui.Session.Close() }; if ($script:ui.Job) { $script:ui.Job.Stop() }; $script:ui.Timer.Stop() })
 return $window
}
function Reset-DesktopPage([string]$heading) {
 $script:ui.Content.Children.Clear(); $script:ui.Fields=@{}; $script:ui.Heading.Text=$heading
}
function Add-DesktopText([string]$text,[bool]$heading=$false) {
 $control=New-Object Windows.Controls.TextBlock; $control.Text=$text; $control.TextWrapping='Wrap'; $control.Margin='0,8,0,8'
 if ($heading) { $control.FontSize=20; $control.FontWeight='SemiBold' }
 [void]$script:ui.Content.Children.Add($control); return $control
}
function Add-DesktopButton([string]$text,[scriptblock]$action) {
 $button=New-Object Windows.Controls.Button; $button.Content=$text; $button.HorizontalAlignment='Left'; $button.Add_Click($action)
 [void]$script:ui.Content.Children.Add($button); return $button
}
function Add-DesktopField($field,$value=$null) {
 $panel=New-Object Windows.Controls.StackPanel; $panel.Margin='0,7,0,7'
 $label=New-Object Windows.Controls.Label; $label.Content=$field.label; $label.Padding='0,0,0,5'
 if ($field.kind -eq 'choice') {
  $control=New-Object Windows.Controls.ComboBox; $control.DisplayMemberPath='label'; $control.SelectedValuePath='value'
  foreach ($choice in $field.choices) { [void]$control.Items.Add($choice) }; if ($null -ne $value) { $control.SelectedValue=$value }
 } elseif ($field.kind -eq 'boolean') {
  $control=New-Object Windows.Controls.CheckBox; $control.Content='Yes'; $control.IsChecked=($value -eq $true); $control.MinHeight=30
 } else { $control=New-Object Windows.Controls.TextBox; if ($null -ne $value) { $control.Text=[string]$value } }
 $control.Tag=$field; $label.Target=$control
 [void]$panel.Children.Add($label); [void]$panel.Children.Add($control); [void]$script:ui.Content.Children.Add($panel)
 $script:ui.Fields[$field.name]=$control; return $control
}
function Get-DesktopValues([switch]$Partial) {
 $values=@{}
 foreach ($name in $script:ui.Fields.Keys) {
  $control=$script:ui.Fields[$name]; $field=$control.Tag; $value=$null
  if ($field.kind -eq 'choice') { $value=$control.SelectedValue }
  elseif ($field.kind -eq 'boolean') { $value=($control.IsChecked -eq $true) }
  else { $value=$control.Text.Trim() }
  if ($null -eq $value -or ($value -is [string] -and $value.Length -eq 0)) { if ($field.required -and -not $Partial) { throw 'Required field missing' }; continue }
  if ($field.kind -eq 'integer') {
   $number=0L; if (-not [long]::TryParse([string]$value,[ref]$number)) { throw 'Whole number required' }
   if (($null -ne $field.minimum -and $number -lt $field.minimum) -or ($null -ne $field.maximum -and $number -gt $field.maximum)) { throw 'Number out of range' }; $value=$number
  }
  $values[$name]=$value
 }; return $values
}
function Start-DesktopRequest($request,[scriptblock]$callback) {
 if ($script:ui.Job) { return }
 $python=Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
 if (-not $python) { $script:ui.Status.Text='Install Python 3.12 or newer, then reopen Engine Room.'; return }
 $json=($request | ConvertTo-Json -Depth 20 -Compress)+[Environment]::NewLine
 $script:ui.Job=New-Object EngineRoom.DesktopJob($python.Source,$script:ReleaseRoot,$json,190000)
 $script:ui.Callback=$callback; $script:ui.Content.IsEnabled=$false; $script:ui.Status.Text='Checking. You can still close this window.'
}
function Invoke-DesktopController([string]$method,$arguments,[scriptblock]$callback) {
 Start-DesktopRequest @{ action='controller'; params=@{ method=$method; arguments=$arguments } } $callback
}
function Show-DesktopStartup($state) {
 Reset-DesktopPage 'Connect your controller'
 if (-not $state.python_ready) { [void](Add-DesktopText 'Install Python 3.12 or newer before continuing.'); return }
 [void](Add-DesktopButton 'Recover saved access or rentals' { Show-DesktopRecovery })
 if (-not $state.ssh_ready) { [void](Add-DesktopText 'Install the Windows OpenSSH Client before connecting a controller.'); return }
 $script:ui.Status.Text=$state.message
 if ($state.controller_state -eq 'missing') {
  [void](Add-DesktopText 'No provider is configured.' $true)
  [void](Add-DesktopText 'Use a separate, independently powered Linux computer for shutdown protection. Verify its private address and SSH host key separately. Provider credentials stay on that controller.')
  [void](Add-DesktopButton 'Set up controller' { Show-ControllerEnrollment })
 } elseif ($state.controller_state -eq 'configured') {
  [void](Add-DesktopText 'Verify your saved controller' $true); [void](Add-DesktopButton 'Connect controller' { Connect-DesktopController })
 } else { [void](Add-DesktopText 'Controller settings need recovery. Existing enrollment was preserved; do not overwrite it while rentals may be outstanding.' $true) }
}
function Show-ControllerEnrollment {
 Reset-DesktopPage 'Verify an independent controller'
 foreach ($item in @(@('address','Private IP address','text'),@('port','SSH port','integer'),@('username','Dedicated SSH username','text'),@('host_key','Verified Ed25519 host public key','text'),@('identity_file','Dedicated private SSH identity file','text'),@('controller_id','Controller enrollment ID','text'),@('controller_host_id','Controller host identity','text'),@('independent_host_confirmed','I confirm this controller stays available when this computer is off','boolean'))) {
  [void](Add-DesktopField ([pscustomobject]@{ name=$item[0]; label=$item[1]; kind=$item[2]; required=$true }))
 }
 [void](Add-DesktopButton 'Verify and save controller' {
  try { $values=Get-DesktopValues; Start-DesktopRequest @{ action='enroll_controller'; params=@{ endpoint=$values } } { param($result) Connect-DesktopController } }
  catch { $script:ui.Status.Text='Complete the controller details and confirm its independent availability.' }
 })
}
function Connect-DesktopController {
 Invoke-DesktopController 'info' @{} { param($info) $script:ui.Info=$info
  Invoke-DesktopController 'connections' @{} { param($connections) $script:ui.Connections=@($connections); Show-DesktopConnections }
 }
}
function Show-DesktopConnections {
 Reset-DesktopPage 'Named connections'
 [void](Add-DesktopButton 'Recover saved access or rentals' { Show-DesktopRecovery })
 [void](Add-DesktopButton 'Plan a GPU rental' { Show-RentalConnections })
 [void](Add-DesktopButton 'Connect an existing machine' { Show-AttachmentConnections })
 [void](Add-DesktopButton 'Saved storage' { Show-StorageConnections })
 if ($script:ui.Connections.Count -eq 0) { [void](Add-DesktopText 'No connections yet. Choose a connector and an explicitly saved credential reference to add one.') }
 foreach ($connection in $script:ui.Connections) { [void](Add-DesktopText ($connection.name+' ('+$connection.connector_id+')')) }
 [void](Add-DesktopText 'Add a connection' $true)
 $choices=@($script:ui.Info.connectors | ForEach-Object { [pscustomobject]@{ value=$_.id; label=$_.name } })
 [void](Add-DesktopField ([pscustomobject]@{ name='connector_id'; label='Connector'; kind='choice'; required=$true; choices=$choices }))
 [void](Add-DesktopButton 'Continue' {
  try { $values=Get-DesktopValues; $script:ui.ConnectorId=$values.connector_id
   Invoke-DesktopController 'connector_form' @{ connector_id=$values.connector_id; purpose='connection' } { param($form) Show-AddConnection $form }
  } catch { $script:ui.Status.Text='Choose a connector first.' }
 })
 $script:ui.Status.Text=if ($script:ui.Info.protection_healthy) { 'Controller protection is healthy. Review a fresh offer before renting.' } else { 'Controller protection is not healthy. Rentals must remain stopped.' }
}
function Show-AddConnection($form) {
 Reset-DesktopPage 'Name this connection'; [void](Add-DesktopText $form.help)
 [void](Add-DesktopField ([pscustomobject]@{ name='name'; label='Connection name'; kind='text'; required=$true }))
 [void](Add-DesktopField ([pscustomobject]@{ name='credential_ref'; label='Saved provider credential reference on the controller'; kind='credential_ref'; required=$true }))
 foreach ($field in $form.fields) { [void](Add-DesktopField $field) }
 [void](Add-DesktopButton 'Verify and add connection' {
  try { $values=Get-DesktopValues; $settings=@{}; foreach ($key in $values.Keys) { if ($key -notin @('name','credential_ref')) { $settings[$key]=$values[$key] } }
   Invoke-DesktopController 'add_connection' @{ name=$values.name; connector_id=$script:ui.ConnectorId; credential_ref=$values.credential_ref; settings=$settings } { param($connection) Connect-DesktopController }
  } catch { $script:ui.Status.Text='Enter a name and saved credential reference. Do not enter credential values here.' }
 })
}

function Start-DesktopSession($request,[bool]$confirmed,[ValidateSet('rental','attachment')][string]$mode='rental') {
 if (-not $confirmed -or $script:ui.Session -or $script:ui.Job) { throw 'A confirmed idle window is required' }
 $seconds=86400L
 if ($mode -eq 'rental' -and (-not [long]::TryParse([string]$request.duration_seconds,[ref]$seconds) -or $seconds -lt 1 -or $seconds -gt 86400)) { throw 'A bounded rental duration is required' }
 $python=Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
 $frame=(@{action='begin';mode=$mode;request=$request;confirmed=$true}|ConvertTo-Json -Depth 20 -Compress)+"`n"
 $script:ui.Session=New-Object EngineRoom.SessionProcess($python.Source,$script:ReleaseRoot,$frame,([int]$seconds+300))
 $script:ui.SessionMode=$mode
 $script:ui.EmergencyStop.Content=if ($mode -eq 'attachment') {'Disconnect access'} else {'Stop rental'}
 $script:ui.SessionClock=[Diagnostics.Stopwatch]::StartNew(); $script:ui.SessionPulse=0.0
 $script:ui.SessionConfirmed=$false; $script:ui.SessionStopping=$false; $script:ui.SessionReady=$false; $script:ui.ReadyUntil=0.0; $script:ui.ToolPending=$null
 Reset-DesktopPage $(if ($mode -eq 'attachment') {'Your existing machine connection'} else {'Your rental'})
 if ($mode -eq 'attachment') { [void](Add-DesktopText 'Keep this window open for local access. Disconnecting leaves the existing machine, model and outside billing running.') }
 else { [void](Add-DesktopText 'Waiting for the controller. Closing this window stops renewal and requests recovery. Keep the controller available.') }
 $script:ui.EmergencyStop.Visibility='Visible'
 $script:ui.ToolFormButton=$null
 $script:ui.ToolFormButton=Add-DesktopButton 'Open a coding tool' { Show-DesktopTool }; $script:ui.ToolFormButton.IsEnabled=$false
 $script:ui.Status.Text=if ($mode -eq 'attachment') {'Connection pending. The machine will remain running after disconnect.'} else {'Request pending. Shutdown is not confirmed.'}
}
function Stop-DesktopSession {
 $script:ui.SessionReady=$false
 if ($script:ui.Session) { $script:ui.SessionStopping=$true; $script:ui.Session.Close() }
 if (-not $script:ui.SessionConfirmed) { $script:ui.Status.Text=if ($script:ui.SessionMode -eq 'attachment') {'Disconnect requested. Waiting for local access closure; the existing machine stays running.'} else {'Stop requested. Waiting for provider confirmation; keep recovery records.'} }
 Update-DesktopToolButtons
}
function Update-DesktopSession {
 $session=$script:ui.Session
 if ($null -eq $session) { return }
 try {
  $elapsed=$script:ui.SessionClock.Elapsed.TotalSeconds
  if ($script:ui.SessionReady -and $elapsed -gt $script:ui.ReadyUntil) {
   $script:ui.SessionReady=$false
   if (-not $script:ui.SessionStopping) { $script:ui.Status.Text='Model readiness is stale. Waiting for a fresh controller reading.' }
  }
  # A delayed dispatcher must not revive a lease after its UI liveness expired.
  if (-not $script:ui.SessionStopping -and -not $session.Complete) {
   if ($elapsed-$script:ui.SessionPulse -ge 60) { Stop-DesktopSession }
   elseif ($elapsed-$script:ui.SessionPulse -ge 15) { $session.Pulse(); $script:ui.SessionPulse=$elapsed }
  }
  for ($index=0; $index -lt 16; $index++) {
   $raw=$session.Take(); if ($null -eq $raw) { break }
   $frame=$raw|ConvertFrom-Json -ErrorAction Stop
   if ($frame.event -ceq 'tool_result') {
    if ($frame.request_id -ceq $script:ui.ToolPending -and $frame.opened -is [bool]) {
     $script:ui.ToolPending=$null
     $message=if ($frame.opened) {'The tool was opened with session-only settings. Compatibility is experimental. Keep this window open.'} else {'The tool could not open. Check readiness, native executable and project folder. Existing settings were preserved.'}
     if ($script:ui.ToolResult) { $script:ui.ToolResult.Text=$message }; $script:ui.Status.Text=$message
    }
    continue
   }
   $script:ui.SessionReady=($frame.event -ceq 'snapshot' -and $frame.receipt.state -ceq 'active' -and -not $frame.receipt.cancel_requested -and -not $script:ui.SessionStopping -and $frame.view.phase -ceq 'ready' -and $frame.view.ready -is [bool] -and $frame.view.ready)
   if ($script:ui.SessionReady) { $script:ui.ReadyUntil=$elapsed+10 }
   if ($script:ui.SessionMode -eq 'attachment') {
    if ($frame.event -ceq 'snapshot' -and $frame.receipt.mode -cne 'attachment') { throw 'Unexpected attachment receipt' }
    $detached=($frame.event -ceq 'snapshot' -and $frame.receipt.state -ceq 'detached' -and $frame.shutdown_confirmed -is [bool] -and -not $frame.shutdown_confirmed)
    if ($detached) { $script:ui.SessionConfirmed=$true; $script:ui.SessionReady=$false; $script:ui.Status.Text='Disconnected from the existing model. The machine and outside billing remain running.' }
    elseif (-not $script:ui.SessionConfirmed) {
     if ($frame.event -ceq 'snapshot' -and $frame.receipt.state -ceq 'off') { throw 'Attachments cannot assert shutdown' }
     $script:ui.Status.Text=if ($script:ui.SessionStopping) {'Waiting for local disconnection. The existing machine stays running.'} elseif ($script:ui.SessionReady) {'The selected existing model is ready. Keep this window open; outside billing continues.'} elseif ($frame.event -ceq 'cancelled') {'This connection was cancelled before submission. The existing machine was not shut down.'} else {'Existing-model access is not confirmed. Preserve recovery records; the machine stays running.'}
    }
    continue
   }
   $off=($frame.event -ceq 'snapshot' -and $frame.receipt.state -ceq 'off' -and $frame.shutdown_confirmed -is [bool] -and $frame.shutdown_confirmed)
   if ($off) { $script:ui.SessionConfirmed=$true; $script:ui.Status.Text='The provider confirmed this rental is off.' }
   elseif (-not $script:ui.SessionConfirmed) {
    switch -CaseSensitive ($frame.event) {
     'pending' { $script:ui.Status.Text='Request pending. Shutdown is not confirmed.' }
     'cancelled' { $script:ui.Status.Text='The request was cancelled before submission. No provider shutdown is claimed.' }
     'snapshot' {
      $phase=if ($script:ui.SessionStopping -or $frame.receipt.cancel_requested) {'stopping'} elseif ($frame.view) {$frame.view.phase} else {$frame.receipt.state}
      $script:ui.Status.Text=switch -CaseSensitive ($phase) {
       'intent' {'The controller recorded the request. Allocation is pending.'}
       'allocating' {'The provider allocation is in progress. Shutdown is not confirmed.'}
       'starting' {'The rental is allocated. Capacity checks, installation or model startup are in progress.'}
       'ready' {if ($frame.receipt.state -ceq 'active' -and $frame.view.ready -is [bool] -and $frame.view.ready) {'The controller reports the model is ready. Keep this window and the independent controller available.'} else {'Model readiness could not be verified.'}}
       'unresolved' {'The controller cannot confirm model readiness. Keep it and the recovery records available; shutdown is not confirmed.'}
       'stopping' {'Shutdown was requested. Waiting for provider confirmation.'}
       'cancelled' {'The allocation was cancelled before submission. No provider shutdown is claimed.'}
       default {'Controller status received. Shutdown is not confirmed.'}
      }
     }
     'uncertain' { $script:ui.Status.Text='Status is uncertain. Keep the controller and recovery records available.' }
     'error' { $script:ui.Status.Text='The session could not be verified. Use recovery; shutdown is not confirmed.' }
     default { throw 'Unsupported session event' }
    }
   }
  }
  if ($session.Complete) {
   $script:ui.SessionReady=$false
   if (-not $script:ui.SessionConfirmed) { $script:ui.Status.Text=if ($script:ui.SessionMode -eq 'attachment') {'The access helper ended. Use recovery to confirm local disconnection; the machine stays running.'} else {'The session helper ended. Use recovery; shutdown is not confirmed.'} }
   $script:ui.SessionClock.Stop(); $script:ui.Session=$null
   [void](Add-DesktopButton 'Open saved-request recovery' { Show-DesktopRecovery })
  }
  Update-DesktopToolButtons
 } catch {
  Stop-DesktopSession
  $script:ui.Status.Text=if ($script:ui.SessionMode -eq 'attachment') {'Local access could not be verified. Use recovery; the existing machine stays running.'} else {'The session response could not be verified. Use recovery; shutdown is not confirmed.'}
 }
}

function Show-DesktopRecovery {
 if ($script:ui.Session) { $script:ui.Status.Text='Stop the current session and wait for its helper to finish before opening recovery.'; return }
 Start-DesktopRequest @{action='recovery_list'} { param($result)
  Reset-DesktopPage 'Recover saved access or rentals'
  [void](Add-DesktopText 'Saved records are history. Check with the original controller for current status. Recovery never starts another rental.')
  if ($result.damaged_records -gt 0) { [void](Add-DesktopText 'Some recovery records are damaged. Preserve them and the controller state for reconciliation.' $true) }
  if (@($result.records).Count -eq 0) { [void](Add-DesktopText 'No saved requests were found. This does not check provider accounts for unrelated resources.') }
  foreach ($record in $result.records) {
   [void](Add-DesktopText ('Saved request: '+$record.operation_id) $true)
   if ($record.can_recover) {
    $button=Add-DesktopButton 'Check current status' { param($sender,$eventArgs) Invoke-DesktopRecovery $sender.Tag.operation_id $false $sender.Tag.mode }; $button.Tag=@{operation_id=$record.operation_id;mode=$record.mode}
    $button=Add-DesktopButton 'Review cancellation' { param($sender,$eventArgs) Show-DesktopCancellation $sender.Tag.operation_id $sender.Tag.mode }; $button.Tag=@{operation_id=$record.operation_id;mode=$record.mode}
   } else { [void](Add-DesktopText 'Saved history only. No pending request is available for these recovery controls.') }
  }
  $script:ui.Status.Text='Local records loaded. Current provider state has not been checked.'
 }
}
function Show-DesktopCancellation([string]$operation,[string]$mode='rental') {
 Reset-DesktopPage $(if ($mode -eq 'attachment') {'Disconnect this saved existing-machine request'} else {'Cancel this saved rental request'})
 $script:ui.RecoveryOperation=$operation; $script:ui.RecoveryMode=$mode
 [void](Add-DesktopText ('Request: '+$operation))
 if ($mode -eq 'attachment') { [void](Add-DesktopText 'This forbids a delayed connection and closes only Engine Room access. The existing machine, model and outside billing stay running.') }
 else { [void](Add-DesktopText 'This asks the original controller to forbid a delayed start and stop this managed rental if it was submitted. An uncertain allocation may take time to reconcile. Keep the controller and recovery records available.') }
 [void](Add-DesktopField ([pscustomobject]@{name='cancel_confirmed';label=$(if ($mode -eq 'attachment') {'I want to disconnect only this saved model access'} else {'I want to cancel this saved managed rental request'});kind='boolean';required=$true}))
 [void](Add-DesktopButton 'Request cancellation' {
  if (-not $script:ui.Fields.cancel_confirmed.IsChecked) { $script:ui.Status.Text='Confirm this cancellation first.'; return }
  Invoke-DesktopRecovery $script:ui.RecoveryOperation $true $script:ui.RecoveryMode
 })
}
function Invoke-DesktopRecovery([string]$operation,[bool]$cancel,[string]$mode='rental') {
 if ($script:ui.Session) { $script:ui.Status.Text='Wait for the current session helper to finish before using recovery.'; return }
 Start-DesktopRequest @{action='recover';params=@{operation_id=$operation;mode=$mode;cancel=$cancel;confirmed=$true}} { param($result)
  Reset-DesktopPage 'Saved-request recovery'
  [void](Add-DesktopButton 'Check saved requests again' { Show-DesktopRecovery })
  if ($result.mode -ceq 'attachment' -and $result.state -ceq 'detached' -and $result.disconnected_confirmed -is [bool] -and $result.disconnected_confirmed -and -not $result.shutdown_confirmed) {
   $script:ui.Status.Text='Local access is disconnected. The existing machine and outside billing remain running.'
  } elseif ($result.mode -cne 'attachment' -and $result.state -ceq 'off' -and $result.shutdown_confirmed -is [bool] -and $result.shutdown_confirmed) {
   $script:ui.Status.Text='The provider confirmed this rental is off.'
  } elseif ($result.state -ceq 'cancelled-before-submission') {
   $script:ui.Status.Text='The controller forbids this request from starting. No provider shutdown is claimed.'
  } else { $script:ui.Status.Text='Recovery is still pending. Shutdown is not confirmed; check again with the original controller.' }
 }
}

function Show-AttachmentConnections {
 if ($script:ui.Session -or $script:ui.Job) { $script:ui.Status.Text='Finish the current session or request before connecting.'; return }
 Reset-DesktopPage 'Connect an existing machine'
 [void](Add-DesktopText 'Use a named connection to a model that is already running. Engine Room does not install, rent or stop this machine. Outside compute and storage charges continue after disconnect.')
 $ids=@($script:ui.Info.connectors | Where-Object { 'attachment' -in $_.modes } | ForEach-Object {$_.id})
 $choices=@($script:ui.Connections | Where-Object {$_.connector_id -in $ids} | ForEach-Object {[pscustomobject]@{value=$_.id;label=$_.name}})
 [void](Add-DesktopField ([pscustomobject]@{name='connection_id';label='Named existing-machine connection';kind='choice';required=$true;choices=$choices}))
 [void](Add-DesktopButton 'Review existing model' {
  try {
   $values=Get-DesktopValues
   $script:ui.AttachmentConnection=@($script:ui.Connections | Where-Object id -eq $values.connection_id)[0]
   if ($null -eq $script:ui.AttachmentConnection) {throw 'Choose a connection'}
   Invoke-DesktopController 'attachment_preview' @{connection_id=$values.connection_id} {param($target) Show-AttachmentConfirmation $target}
  } catch {$script:ui.Status.Text='Choose an existing-machine connection first.'}
 })
 $script:ui.Status.Text='No machine is selected automatically. Reviewing this connection does not rent resources.'
}
function Show-AttachmentConfirmation($target) {
 Reset-DesktopPage 'Review existing-model access'
 $script:ui.AttachmentConfirmation=(@{connection_id=$script:ui.AttachmentConnection.id;approved_target=$target}|ConvertTo-Json -Depth 10|ConvertFrom-Json)
 $script:ui.AttachmentSubmitted=$false
 [void](Add-DesktopText ('Connection: '+$script:ui.AttachmentConnection.name) $true)
 [void](Add-DesktopText ('Exact served model: '+$target.model_id))
 [void](Add-DesktopText ('Verified account: '+$target.account_id+'; existing resource: '+$target.resource_id))
 [void](Add-DesktopText 'Experimental compatibility. Engine Room checks the selected model through read-only access. No software or model is installed or started. Disconnect closes local access; the existing machine and outside billing continue.')
 [void](Add-DesktopField ([pscustomobject]@{name='context';label='Coding-tool conversation limit in tokens (from this model server settings)';kind='integer';required=$true;minimum=512;maximum=1048576}))
 [void](Add-DesktopField ([pscustomobject]@{name='access_confirmed';label='I authorize connecting to this exact existing model';kind='boolean';required=$true}))
 [void](Add-DesktopField ([pscustomobject]@{name='costs_confirmed';label='I understand disconnect leaves the machine and outside billing running';kind='boolean';required=$true}))
 [void](Add-DesktopButton 'Connect existing model' {
  try {
   if ($script:ui.Session -or $script:ui.Job -or $script:ui.AttachmentSubmitted) {throw 'Already submitted or busy'}
   $values=Get-DesktopValues
   if (-not ($values.access_confirmed -and $values.costs_confirmed)) {throw 'Explicit confirmation required'}
   $script:ui.AttachmentConfirmation|Add-Member NoteProperty context ([long]$values.context) -Force
   $script:ui.AttachmentSubmitted=$true
   Start-DesktopSession $script:ui.AttachmentConfirmation $true 'attachment'
  } catch {$script:ui.Status.Text='Confirm this exact model and continued outside billing before connecting.'}
 })
 $script:ui.Status.Text='Review and confirm explicitly. A changed target requires a new review.'
}

function Show-RentalConnections {
 if ($script:ui.Session -or $script:ui.Job) { $script:ui.Status.Text='Finish the current session or request before planning another rental.'; return }
 Reset-DesktopPage 'Choose a rental connection'
 [void](Add-DesktopText 'Renting creates a disposable provider resource. Connecting an existing machine is a separate workflow and never authorizes machine shutdown.')
 $rentalIds=@($script:ui.Info.connectors | Where-Object { 'rental' -in $_.modes } | ForEach-Object { $_.id })
 $choices=@($script:ui.Connections | Where-Object { $_.connector_id -in $rentalIds } | ForEach-Object { [pscustomobject]@{value=$_.id;label=$_.name} })
 [void](Add-DesktopField ([pscustomobject]@{name='connection_id';label='Named rental connection';kind='choice';required=$true;choices=$choices}))
 [void](Add-DesktopButton 'Choose rental options' {
  try {
   $values=Get-DesktopValues
   $script:ui.RentalConnection=@($script:ui.Connections|Where-Object id -eq $values.connection_id)[0]
   if ($null -eq $script:ui.RentalConnection) { throw 'Missing connection' }
   Update-RentalOptions @{}
  } catch { $script:ui.Status.Text='Choose a named rental connection first.' }
 })
 $script:ui.Status.Text='Browsing offers does not rent a machine. No connection is selected automatically.'
}
function Update-RentalOptions($values) {
 $script:ui.RentalValues=$values
 Invoke-DesktopController 'connector_form' @{connector_id=$script:ui.RentalConnection.connector_id;purpose='selection';connection_id=$script:ui.RentalConnection.id;values=$values} { param($form)
  Reset-DesktopPage 'Choose rental options'
  [void](Add-DesktopText $form.help)
  foreach ($field in $form.fields) { [void](Add-DesktopField $field $script:ui.RentalValues[$field.name]) }
  [void](Add-DesktopButton 'Refresh available choices' {
   try { Update-RentalOptions (Get-DesktopValues -Partial) } catch { $script:ui.Status.Text='Check the selected options and whole-number disk size.' }
  })
  [void](Add-DesktopButton 'Check a fresh offer' {
   try {
    $script:ui.RentalSelection=Get-DesktopValues
    Invoke-DesktopController 'quote' @{connection_id=$script:ui.RentalConnection.id;selection=$script:ui.RentalSelection} { param($quote) Show-RentalOffer $quote }
   } catch { $script:ui.Status.Text='Complete the rental options, refreshing available choices where needed.' }
  })
  $script:ui.Status.Text='Options are supplied by the selected connector. Prices are checked separately.'
 }
}
function Show-RentalOffer($quote) {
 if ($quote.account_id -cne $script:ui.RentalConnection.account_id) { $script:ui.Status.Text='The offer account differs. Verify the original named connection.'; return }
 $script:ui.RentalQuote=$quote
 Reset-DesktopPage 'Review this fresh offer'
 [void](Add-DesktopText ('Connection: '+$script:ui.RentalConnection.name) $true)
 [void](Add-DesktopText ('Provider account: '+$quote.account_id))
 [void](Add-DesktopText ('Rate unit: '+$quote.unit+' per hour. Rate scope: '+$quote.rate_scope+'.'))
 if ($null -eq $quote.price) { [void](Add-DesktopText 'The provider does not publish a verified advance hourly rate for this selection. Any later limit uses the scope shown above; it is not a prepaid spending cap.' $true) }
 else { [void](Add-DesktopText ('Observed rate: '+$quote.price+' '+$quote.unit+' per hour.')) }
 if ($quote.rate_scope -ceq 'account') { [void](Add-DesktopText 'This rate measures the entire provider account, including other activity. It is not a price for this rental alone.') }
 if ($null -eq $quote.balance) { [void](Add-DesktopText 'A prepaid balance was not reported. Provider billing still applies.') }
 else { [void](Add-DesktopText ('Observed balance: '+$quote.balance+' '+$quote.unit+'.')) }
 if ($null -eq $quote.available) { [void](Add-DesktopText 'Availability is not guaranteed before allocation.') }
 if ($null -eq $quote.storage_available_bytes) { [void](Add-DesktopText 'Disk capacity must be verified after allocation and before installation. Setup must stop if the model and installation do not fit.') }
 else { [void](Add-DesktopText ('Reported storage capacity: '+$quote.storage_available_bytes+' bytes. Model downloads, staging and installation need separate headroom.')) }
 [void](Add-DesktopText ('Installation reserve: '+$quote.install_bytes+' bytes.'))
 if ($quote.cost_details) { [void](Add-DesktopText 'Additional billing and storage details' $true); [void](Add-DesktopText ($quote.cost_details|ConvertTo-Json -Depth 10)) }
 [void](Add-DesktopText 'Model planning and final limits must be reviewed before a rental can start. This page does not authorize spending.')
 [void](Add-DesktopButton 'Choose a model' { Show-RentalModel })
 [void](Add-DesktopButton 'Refresh this offer' { Invoke-DesktopController 'quote' @{connection_id=$script:ui.RentalConnection.id;selection=$script:ui.RentalSelection} {param($fresh) Show-RentalOffer $fresh} })
 [void](Add-DesktopButton 'Change rental options' { Update-RentalOptions $script:ui.RentalSelection })
 $script:ui.Status.Text='Fresh offer received. Offers expire after two minutes and are checked again before allocation.'
}

function Show-RentalModel {
 Reset-DesktopPage 'Choose your model'
 [void](Add-DesktopText 'Enter an owner/model identifier. Metadata is read through this named connection; only its explicitly saved model credential reference is used. No model weights are downloaded here.')
 [void](Add-DesktopField ([pscustomobject]@{name='model_id';label='Hugging Face owner/model';kind='text';required=$true}))
 [void](Add-DesktopField ([pscustomobject]@{name='base_model';label='Base owner/model for GGUF (optional override)';kind='text';required=$false}))
 [void](Add-DesktopButton 'Read pinned model metadata' {
  try {
   $values=Get-DesktopValues; $arguments=@{connection_id=$script:ui.RentalConnection.id;model_id=$values.model_id}
   if ($values.ContainsKey('base_model')) { $arguments.base_model=$values.base_model }
   Invoke-DesktopController 'model_discover' $arguments {param($data)
    $script:ui.ModelDiscovery=$data
    Start-DesktopRequest @{action='model_plan';params=@{mode='describe';discovery=$data}} {param($description) Show-RentalModelChoices $description}
   }
  } catch { $script:ui.Status.Text='Enter a model identifier, such as owner/model.' }
 })
}
function Show-RentalModelChoices($description) {
 Reset-DesktopPage 'Plan this model'
 [void](Add-DesktopText ('Model: '+$script:ui.ModelDiscovery.model_id) $true)
 [void](Add-DesktopText ('Pinned revision: '+$script:ui.ModelDiscovery.info.sha))
 [void](Add-DesktopText 'Experimental: this model and tool combination has not passed release validation. Published metadata supports planning, not an inference guarantee.')
 if ($script:ui.RentalSelection.engine -ceq 'llama.cpp') {
  $choices=@($description.variants|Where-Object {$_.complete -and $_.sizesKnown}|ForEach-Object {[pscustomobject]@{value=$_.name;label=$_.label}})
  [void](Add-DesktopField ([pscustomobject]@{name='variant';label='Complete GGUF version';kind='choice';required=$true;choices=$choices}))
 }
 [void](Add-DesktopField ([pscustomobject]@{name='context';label='Conversation capacity in tokens (at least 8192)';kind='integer';required=$true;minimum=8192;maximum=1048576}))
 [void](Add-DesktopButton 'Check model plan' {
  try {
   $values=Get-DesktopValues; $arguments=@{mode='plan';discovery=$script:ui.ModelDiscovery;engine=$script:ui.RentalSelection.engine;context=$values.context}
   if ($values.ContainsKey('variant')) { $arguments.variant=$values.variant }
   Start-DesktopRequest @{action='model_plan';params=$arguments} {param($result) Show-RentalModelPlan $result}
  } catch { $script:ui.Status.Text='Choose a complete version where applicable and enter a supported conversation capacity.' }
 })
 $script:ui.Status.Text='The shared planner checks format, complete shards, precision and published context limits.'
}
function Show-RentalModelPlan($result) {
 $script:ui.RentalModelPlan=$result
 Reset-DesktopPage 'Review the model plan'
 [void](Add-DesktopText $result.plan.id $true)
 [void](Add-DesktopText $result.warning)
 [void](Add-DesktopText ('Runtime: '+$result.plan.engine+'. Conversation capacity: '+$result.plan.context+' tokens; published limit: '+$result.native_context+'.'))
 [void](Add-DesktopText ('Published model files: '+$result.plan.weightBytes+' bytes. Estimated GPU memory required, including cache and headroom: '+$result.estimated_memory_bytes+' bytes.'))
 [void](Add-DesktopText 'This is a memory estimate. Verified GPU capacity, download and installation storage, fresh pricing and explicit duration/rate limits must pass before allocation.')
 [void](Add-DesktopButton 'Check current capacity and storage' { Check-RentalCapacity })
 [void](Add-DesktopButton 'Change model plan' { Show-RentalModel })
 $script:ui.Status.Text='Model plan checked. Rental submission remains unavailable until capacity and final confirmation are integrated.'
}

function Check-RentalCapacity {
 Invoke-DesktopController 'quote' @{connection_id=$script:ui.RentalConnection.id;selection=$script:ui.RentalSelection} {param($quote)
  $script:ui.RentalQuote=$quote
  Start-DesktopRequest @{action='offer_plan';params=@{plan=$script:ui.RentalModelPlan.plan;quote=$quote}} {param($capacity)
   $script:ui.RentalCapacity=$capacity
   Reset-DesktopPage 'Review capacity checks'
   [void](Add-DesktopText ('Estimated GPU memory required: '+$capacity.required_gpu_bytes+' bytes. Storage required including staging and installation: '+$capacity.required_storage_bytes+' bytes.'))
   if ($capacity.gpu_check_deferred) { [void](Add-DesktopText 'GPU capacity is unknown before allocation. The connector must verify the actual GPU before installation and stop setup if it cannot fit this plan.') }
   else { [void](Add-DesktopText ('Provider-reported GPU memory: '+$capacity.gpu_memory_bytes+' bytes. The model estimate fits; actual hardware is checked again during setup.')) }
   if ($capacity.storage_check_deferred) { [void](Add-DesktopText 'Actual disk capacity must be checked before installation. Unknown capacity is not assumed to fit.') }
   else { [void](Add-DesktopText ('Reported storage capacity: '+$capacity.storage_available_bytes+' bytes. No unverified cache is counted.')) }
   [void](Add-DesktopText 'These checks do not reserve capacity or authorize spending. Explicit rate and duration confirmation is still required.')
   [void](Add-DesktopButton 'Review rental limits and confirm' { Show-RentalConfirmation })
   [void](Add-DesktopButton 'Refresh capacity checks' { Check-RentalCapacity })
   $script:ui.Status.Text='Capacity plan checked. Review fresh pricing and explicit limits before starting.'
  }
 }
}

function Show-RentalConfirmation {
 if ($script:ui.Session -or $script:ui.Job) { $script:ui.Status.Text='Finish the current session or request first.'; return }
 $script:ui.Confirmation=(@{connection_id=$script:ui.RentalConnection.id;selection=$script:ui.RentalSelection;plan=$script:ui.RentalModelPlan.plan;approved_quote=$script:ui.RentalQuote}|ConvertTo-Json -Depth 20 -Compress)|ConvertFrom-Json
 $script:ui.ConfirmationSubmitted=$false
 $quote=$script:ui.Confirmation.approved_quote
 Reset-DesktopPage 'Confirm this protected rental'
 [void](Add-DesktopText ('Connection: '+$script:ui.RentalConnection.name+'; provider account: '+$quote.account_id) $true)
 [void](Add-DesktopText ('Model: '+$script:ui.Confirmation.plan.id+' at '+$script:ui.Confirmation.plan.revision+'. Runtime: '+$script:ui.Confirmation.plan.engine+'; conversation capacity: '+$script:ui.Confirmation.plan.context+' tokens.'))
 [void](Add-DesktopText $script:ui.RentalModelPlan.warning)
 [void](Add-DesktopText ('Hourly rate unit: '+$quote.unit+'. Measured scope: '+$quote.rate_scope+'.'))
 if ($null -eq $quote.price) { [void](Add-DesktopText 'The advance rental price is unknown. Setup may incur charges before a usable rate is observed. Your ceiling is a shutdown trigger, not a provider-enforced spending cap.' $true) }
 else { [void](Add-DesktopText ('Observed hourly rate: '+$quote.price+' '+$quote.unit+'. Separate storage and other provider charges may apply.')) }
 if ($quote.rate_scope -ceq 'account') { [void](Add-DesktopText 'The rate limit measures all activity in this provider account, including unrelated rentals. Cleanup affects only this managed rental.') }
 if ($null -eq $quote.balance) { [void](Add-DesktopText 'No prepaid balance was reported.') }
 else { [void](Add-DesktopText ('Observed balance: '+$quote.balance+' '+$quote.unit+'.')) }
 if ($quote.cost_details) { [void](Add-DesktopText ('Separate storage and provider details: '+($quote.cost_details|ConvertTo-Json -Depth 10 -Compress))) }
 [void](Add-DesktopText ('Required GPU memory estimate: '+$script:ui.RentalCapacity.required_gpu_bytes+' bytes; required storage including staging: '+$script:ui.RentalCapacity.required_storage_bytes+' bytes.'))
 if ($script:ui.RentalCapacity.gpu_check_deferred -or $script:ui.RentalCapacity.storage_check_deferred) { [void](Add-DesktopText 'Capacity is partly unknown before allocation. Actual GPU and disk checks must pass before installation; a failed check still requires provider-confirmed shutdown.') }
 [void](Add-DesktopText 'The independent controller must remain powered and connected. Desktop loss stops renewal, but controller or provider outages can delay shutdown and billing. Closing this window requests cancellation; it never proves the rental is off.')
 [void](Add-DesktopField ([pscustomobject]@{name='rate_ceiling';label=('Maximum observed hourly rate in '+$quote.unit+' ('+$quote.rate_scope+' scope)');kind='text';required=$true}))
 [void](Add-DesktopField ([pscustomobject]@{name='duration_minutes';label='Maximum rental duration in minutes';kind='integer';required=$true;minimum=1;maximum=1440}))
 foreach ($entry in @(@('spending_confirmed','I authorize this rental and its provider charges within the reviewed limits'),@('protection_confirmed','I will keep the independent controller available and understand shutdown can be delayed'),@('experimental_confirmed','I accept the experimental model status and any deferred capacity checks'))) {
  [void](Add-DesktopField ([pscustomobject]@{name=$entry[0];label=$entry[1];kind='boolean';required=$true}))
 }
 [void](Add-DesktopButton 'Start protected rental' { Confirm-DesktopRental })
 [void](Add-DesktopButton 'Refresh offer and capacity instead' { Check-RentalCapacity })
 $script:ui.Status.Text='Nothing has been rented. Enter limits and approve explicitly; an expired or changed offer requires review again.'
}
function Confirm-DesktopRental {
 try {
  if ($script:ui.Session -or $script:ui.Job -or $script:ui.ConfirmationSubmitted) { throw 'Busy or already submitted' }
  $values=Get-DesktopValues
  if (-not ($values.spending_confirmed -and $values.protection_confirmed -and $values.experimental_confirmed)) { throw 'Confirmation required' }
  $rate=0.0
  if (-not [double]::TryParse($values.rate_ceiling,[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$rate) -or [double]::IsNaN($rate) -or [double]::IsInfinity($rate) -or $rate -le 0) { throw 'Rate invalid' }
  $request=$script:ui.Confirmation
  $age=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-$request.approved_quote.observed_at
  if ($age -lt 0 -or $age -gt 120) { $script:ui.Status.Text='This offer expired. Refresh the offer and capacity checks, then review and confirm again.'; return }
  if ($null -ne $request.approved_quote.price -and $rate -lt $request.approved_quote.price) { throw 'Below offered rate' }
  $request|Add-Member NoteProperty rate_ceiling $rate -Force
  $request|Add-Member NoteProperty duration_seconds ([long]$values.duration_minutes*60) -Force
  $script:ui.ConfirmationSubmitted=$true
  Start-DesktopSession $request $true
 } catch { $script:ui.Status.Text='Enter a positive hourly rate at least as high as the offer, a whole-number duration, and all three confirmations.' }
}

function Test-DesktopToolReady {
 return ($null -ne $script:ui.Session -and -not $script:ui.Session.Complete -and -not $script:ui.SessionStopping -and $script:ui.SessionReady -and $script:ui.SessionClock.Elapsed.TotalSeconds -le $script:ui.ReadyUntil)
}
function Update-DesktopToolButtons {
 if ($script:ui.EmergencyStop) { $script:ui.EmergencyStop.Visibility=if ($script:ui.Session -and -not $script:ui.Session.Complete) {'Visible'} else {'Collapsed'} }
 $ready=Test-DesktopToolReady
 if ($script:ui.ToolFormButton) { $script:ui.ToolFormButton.IsEnabled=$ready }
 if ($script:ui.ToolLaunchButton) { $script:ui.ToolLaunchButton.IsEnabled=($ready -and -not $script:ui.ToolPending) }
}
function Show-DesktopTool {
 if (-not (Test-DesktopToolReady)) { $script:ui.Status.Text='Wait for fresh model readiness before opening a coding tool.'; return }
 Reset-DesktopPage 'Open a coding tool'
 $script:ui.EmergencyStop.Visibility='Visible'
 [void](Add-DesktopText 'Experimental: tool compatibility requires live validation. Only the selected new process receives this session connection. Existing settings and running applications are not changed. Close any single-instance tool first; keep this window open while using the model.')
 [void](Add-DesktopField ([pscustomobject]@{name='tool';label='Coding tool';kind='choice';required=$true;choices=@([pscustomobject]@{value='opencode';label='OpenCode'},[pscustomobject]@{value='codex';label='Codex (requires compatible Responses API)'})}))
 [void](Add-DesktopField ([pscustomobject]@{name='executable';label='Installed native executable (.exe)';kind='text';required=$true}))
 [void](Add-DesktopButton 'Choose executable' {
  $dialog=New-Object Microsoft.Win32.OpenFileDialog; $dialog.Filter='Native executable (*.exe)|*.exe'; $dialog.CheckFileExists=$true
  if ($dialog.ShowDialog($script:ui.Window)) { $script:ui.Fields.executable.Text=$dialog.FileName }
 })
 [void](Add-DesktopField ([pscustomobject]@{name='working_directory';label='Existing project folder';kind='text';required=$true}))
 [void](Add-DesktopButton 'Choose project folder' {
  Add-Type -AssemblyName System.Windows.Forms
  $dialog=New-Object Windows.Forms.FolderBrowserDialog
  try { if ($dialog.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) { $script:ui.Fields.working_directory.Text=$dialog.SelectedPath } } finally { $dialog.Dispose() }
 })
 foreach ($entry in @(@('desktop_idle','I checked that existing single-instance tool windows are closed'),@('confirmed','Open this selected tool with the experimental session connection'))) {
  [void](Add-DesktopField ([pscustomobject]@{name=$entry[0];label=$entry[1];kind='boolean';required=$true}))
 }
 $script:ui.ToolResult=Add-DesktopText 'No tool was opened.'
 $script:ui.ToolLaunchButton=Add-DesktopButton 'Open selected tool' { Open-DesktopTool }
 Update-DesktopToolButtons
}
function Open-DesktopTool {
 try {
  if (-not (Test-DesktopToolReady) -or $script:ui.ToolPending) { throw 'Session not ready or already pending' }
  $values=Get-DesktopValues
  if (-not $values.confirmed -or -not $values.desktop_idle) { throw 'Explicit confirmation required' }
  $identity=[guid]::NewGuid().ToString('N')
  $frame=(@{action='tool_launch';request_id=$identity;tool=$values.tool;executable=$values.executable;working_directory=$values.working_directory;desktop_idle=$true;confirmed=$true}|ConvertTo-Json -Compress)+"`n"
  $script:ui.ToolPending=$identity; Update-DesktopToolButtons
  if (-not $script:ui.Session.Command($frame)) { throw 'The helper could not accept the request' }
  $script:ui.ToolResult.Text='Opening the selected tool. Do not repeat the request while its result is unknown.'
 } catch { $script:ui.Status.Text='Check fresh model readiness, select a native tool and project folder, and confirm both checkboxes. No automatic retry was made.' }
}

function Show-StorageConnections {
 if ($script:ui.Session -or $script:ui.Job) { $script:ui.Status.Text='Finish the current session or request first.'; return }
 Reset-DesktopPage 'Saved storage'
 [void](Add-DesktopText 'Saved storage keeps billing after a rental stops. Engine Room never deletes volumes automatically. Remove unwanted storage in its provider account after preserving your data.')
 [void](Add-DesktopButton 'Recover saved storage requests' { Show-StorageHistory '' })
 $ids=@($script:ui.Info.connectors | Where-Object {'persistent_storage' -in $_.capabilities} | ForEach-Object {$_.id})
 $choices=@($script:ui.Connections | Where-Object {$_.connector_id -in $ids} | ForEach-Object {[pscustomobject]@{value=$_.id;label=$_.name}})
 [void](Add-DesktopField ([pscustomobject]@{name='connection_id';label='Named storage connection';kind='choice';required=$true;choices=$choices}))
 [void](Add-DesktopButton 'Choose storage options' {
  try {
   $values=Get-DesktopValues
   $script:ui.StorageConnection=@($script:ui.Connections | Where-Object id -eq $values.connection_id)[0]
   if ($null -eq $script:ui.StorageConnection) {throw 'Choose a connection'}
   Invoke-DesktopController 'connector_form' @{connector_id=$script:ui.StorageConnection.connector_id;purpose='storage';connection_id=$values.connection_id} {param($form)
    Reset-DesktopPage 'Choose saved storage'; [void](Add-DesktopText $form.help)
    foreach ($field in $form.fields) {[void](Add-DesktopField $field)}
    [void](Add-DesktopButton 'Get fresh monthly estimate' {
     try {
      $script:ui.StorageSelection=Get-DesktopValues
      Invoke-DesktopController 'storage_quote' @{connection_id=$script:ui.StorageConnection.id;selection=$script:ui.StorageSelection} {param($quote) Show-StorageConfirmation $quote}
     } catch {$script:ui.Status.Text='Complete the explicit storage options first.'}
    })
   }
  } catch {$script:ui.Status.Text='Choose a storage connection first.'}
 })
}
function Show-StorageConfirmation($quote) {
 Reset-DesktopPage 'Review storage charges'
 $script:ui.StorageRequest=(@{connection_id=$script:ui.StorageConnection.id;selection=$script:ui.StorageSelection;approved_quote=$quote;continuing_costs_confirmed=$true}|ConvertTo-Json -Depth 12|ConvertFrom-Json)
 $script:ui.StorageSubmitted=$false
 [void](Add-DesktopText ('Connection: '+$script:ui.StorageConnection.name) $true)
 [void](Add-DesktopText ('Account: '+$quote.account_id+'; size: '+$quote.size_gb+' GB; location: '+$quote.data_center+'; tier: '+$quote.storage_type))
 [void](Add-DesktopText ('Estimated USD per month: '+$quote.monthly_usd) $true)
 [void](Add-DesktopText ('Pricing source: '+$quote.source))
 [void](Add-DesktopText 'This estimate expires after two minutes. Storage charges continue after compute stops, until you remove the volume in the provider account. This is not a spending cap. A lost response must be recovered, never resubmitted.')
 [void](Add-DesktopField ([pscustomobject]@{name='creation_confirmed';label='I authorize creating this exact saved storage at this estimate';kind='boolean';required=$true}))
 [void](Add-DesktopField ([pscustomobject]@{name='costs_confirmed';label='I accept continuing storage charges and responsibility for manual removal';kind='boolean';required=$true}))
 [void](Add-DesktopButton 'Create reviewed storage once' {
  try {
   if ($script:ui.Session -or $script:ui.Job -or $script:ui.StorageSubmitted) {throw 'Already submitted or busy'}
   $values=Get-DesktopValues
   if (-not ($values.creation_confirmed -and $values.costs_confirmed)) {throw 'Explicit approval required'}
   $script:ui.StorageSubmitted=$true
   Start-DesktopRequest @{action='storage_begin';params=@{request=$script:ui.StorageRequest;confirmed=$true}} {param($record) Show-StorageRecord $record.operation_id $record}
  } catch {$script:ui.Status.Text='Confirm both approvals. If already submitted, recover the saved request instead of creating again.'}
 })
 [void](Add-DesktopButton 'Recover saved requests' {Show-StorageHistory ''})
}
function Show-StorageHistory([string]$after='') {
 Start-DesktopRequest @{action='storage_local_records';params=@{after=$after;limit=10}} {param($page)
  Reset-DesktopPage 'Saved storage requests'
  [void](Add-DesktopText 'These are local historical records, not fresh provider or billing confirmation.')
  $choices=@()
  foreach ($row in $page.records) {
   if ($row.damaged) {[void](Add-DesktopText $row.message); continue}
   $choices+=([pscustomobject]@{value=$row.operation_id;label=($row.operation_id+' - '+$row.state)})
  }
  [void](Add-DesktopField ([pscustomobject]@{name='operation_id';label='Saved request';kind='choice';required=$true;choices=$choices}))
  [void](Add-DesktopButton 'Open saved request' {try {$v=Get-DesktopValues; Show-StorageRecord $v.operation_id $null} catch {$script:ui.Status.Text='Choose a saved request.'}})
  $script:ui.StorageCursor=$page.next_cursor
  if ($page.next_cursor) {[void](Add-DesktopButton 'Next page' {Show-StorageHistory $script:ui.StorageCursor})}
 }
}
function Show-StorageRecord([string]$operation,$record) {
 Reset-DesktopPage 'Recover saved storage'
 $script:ui.StorageOperation=$operation
 [void](Add-DesktopText ('Saved request: '+$operation))
 if ($null -ne $record) {[void](Add-DesktopText ('Historical state: '+$record.state+'; volume ID: '+$record.resource_id))}
 [void](Add-DesktopText 'Refresh uses the original account and never creates another volume. Storage may continue billing. Cancelling forbids delayed submissions; an already submitted creation may still finish. No volume is deleted.')
 [void](Add-DesktopButton 'Refresh original provider record' {
  Start-DesktopRequest @{action='storage_recover_local';params=@{operation_id=$script:ui.StorageOperation}} {param($result)
   Show-StorageObservation $result
  }
 })
 [void](Add-DesktopField ([pscustomobject]@{name='resource_id';label='Exact volume ID verified in the original provider account (manual recovery only)';kind='text';required=$false}))
 [void](Add-DesktopField ([pscustomobject]@{name='identity_confirmed';label='I verified that this exact volume belongs to this creation request';kind='boolean';required=$true}))
 [void](Add-DesktopButton 'Confirm manual volume identity' {
  try {$v=Get-DesktopValues; if (-not $v.identity_confirmed -or -not $v.resource_id) {throw 'Confirm identity'}
   Start-DesktopRequest @{action='storage_recover_local';params=@{operation_id=$script:ui.StorageOperation;resource_id=$v.resource_id;confirmed=$true}} {param($result) Show-StorageObservation $result}
  } catch {$script:ui.Status.Text='Enter and explicitly verify the exact volume ID first.'}
 })
 [void](Add-DesktopField ([pscustomobject]@{name='cancel_confirmed';label='I want to forbid delayed creation and understand submitted storage may still finish and bill';kind='boolean';required=$true}))
 [void](Add-DesktopButton 'Forbid delayed creation' {
  try {$v=Get-DesktopValues; if (-not $v.cancel_confirmed) {throw 'Confirm cancellation'}
   Start-DesktopRequest @{action='storage_abandon_local';params=@{operation_id=$script:ui.StorageOperation;confirmed=$true}} {param($result)
    Show-StorageRecord $result.operation_id $result.record
    $script:ui.Status.Text=if ($result.creation_may_complete) {'New submissions are forbidden. Submitted storage may still complete and bill; no volume was deleted.'} else {'The request was closed before submission. No volume was deleted.'}
   }
  } catch {$script:ui.Status.Text='Explicitly confirm delayed-creation cancellation first.'}
 })
 [void](Add-DesktopButton 'Saved requests' {Show-StorageHistory ''})
}

function Show-StorageObservation($result) {
 Show-StorageRecord $result.record.operation_id $result.record
 $observation=$result.observation
 if ($observation.verified -is [bool] -and $observation.verified -and $observation.source -ceq 'explicit-manual-identification') {
  $script:ui.Status.Text='The provider verified the explicitly selected volume identity. Storage charges continue until manual removal.'
 } elseif ($observation.status -ceq 'observed') {
  $script:ui.Status.Text='The provider currently reports this exact volume present. Storage charges continue.'
 } elseif ($observation.status -ceq 'absent') {
  $script:ui.Status.Text='The provider currently reports the saved volume ID absent. Historical identity is preserved; this does not verify your bill or remove other resources.'
 } elseif ($observation.status -ceq 'not-submitted') {
  $script:ui.Status.Text='This request was closed before submission. No volume was deleted.'
 } else {
  $script:ui.Status.Text='Volume identity remains unresolved. Candidate matches do not prove ownership; verify the exact ID in the original provider account.'
  foreach ($candidate in $observation.candidates) {[void](Add-DesktopText ('Unconfirmed candidate volume ID: '+$candidate.id))}
 }
}
