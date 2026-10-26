param([string]$PreviewPath)
# Opening this window never rents a GPU or imports provider credentials.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'desktop/ui.ps1')
$window=New-EngineRoomWindow
if ($PreviewPath) {
 Show-DesktopStartup ([pscustomobject]@{ python_ready=$true; ssh_ready=$true; controller_state='missing'; message='No controller or provider is configured.' })
 $window.WindowStartupLocation='Manual'; $window.Left=-32000; $window.Top=-32000; $window.ShowInTaskbar=$false; $window.Show(); $window.UpdateLayout()
 $window.Measure([Windows.Size]::new(1080,780)); $window.Arrange([Windows.Rect]::new(0,0,1080,780)); $window.UpdateLayout()
 $bitmap=New-Object Windows.Media.Imaging.RenderTargetBitmap(1080,780,96,96,[Windows.Media.PixelFormats]::Pbgra32)
 $bitmap.Render($window); $encoder=New-Object Windows.Media.Imaging.PngBitmapEncoder
 $encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
 $stream=[IO.File]::Create($PreviewPath); try { $encoder.Save($stream) } finally { $stream.Dispose(); $window.Close() }
} else {
 $window.Add_ContentRendered({ Start-DesktopRequest @{ action='startup' } { param($state) Show-DesktopStartup $state } })
 [void]$window.ShowDialog()
}
