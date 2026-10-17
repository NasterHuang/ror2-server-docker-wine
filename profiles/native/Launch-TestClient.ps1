param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$gameRoot = $PSScriptRoot
$cleanGame = '48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c'
$gameDll = Join-Path $gameRoot 'Risk of Rain 2_Data/Managed/RoR2.dll'
if (!(Test-Path -LiteralPath $gameDll) -or (Get-FileHash -LiteralPath $gameDll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $cleanGame) {
    throw 'Use a clean Steam build 25921972 copy. This launcher does not patch or update game files.'
}
$profilePath = Join-Path $gameRoot 'BepInEx/patchers/Rains.NativeCompatibility.json'
$profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
if ($profile.schema -ne 1 -or !$profile.requiredFiles.'UnityPlayer.dll') { throw 'Native compatibility profile is incomplete' }
foreach ($entry in $profile.requiredFiles.PSObject.Properties) {
    $path = Join-Path $gameRoot $entry.Name
    if (!(Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw ('Native compatibility check failed: ' + $entry.Name)
    }
}
$actual = [System.Collections.Generic.Dictionary[string,string]]::new([System.StringComparer]::Ordinal)
$section = ''
foreach ($line in (Get-Content -LiteralPath (Join-Path $gameRoot $profile.configPath))) {
    $text = $line.Trim()
    if ($text.StartsWith('#') -or $text.StartsWith(';') -or !$text) { continue }
    if ($text -match '^\[(.+)\]$') { $section = $Matches[1]; continue }
    if ($text -match '^([^=]+?)\s*=\s*(.*?)\s*$') {
        $key = $section + '/' + $Matches[1].Trim()
        if ($actual.ContainsKey($key)) { throw 'Duplicate native config entry' }
        $actual[$key] = $Matches[2]
    }
}
foreach ($sectionEntry in $profile.configValues.PSObject.Properties) {
    foreach ($entry in $sectionEntry.Value.PSObject.Properties) {
        $key = $sectionEntry.Name + '/' + $entry.Name
        if (!$actual.ContainsKey($key) -or $actual[$key] -cne $entry.Value) { throw ('Native config differs: ' + $key) }
    }
}
if (!(Get-Process -Name steam -ErrorAction SilentlyContinue)) {
    throw 'Open Steam, sign in and enter Library before starting this client.'
}
if ($CheckOnly) { Write-Output 'Pinned game, native DLLs and config match; no game launched.'; return }
# These variables affect only this launcher and its child, not saved system settings.
$env:RAINS_SERVER_TOOLS = '0'
$env:RAINS_RESTORE_CLIENT_WWISE = '0'
$env:RAINS_CLIENT_PROBE = '0'
Start-Process -FilePath (Join-Path $gameRoot 'Risk of Rain 2.exe') -WorkingDirectory $gameRoot
