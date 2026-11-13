# 打包插件 ZIP：根目录直接放文件，不多套一层
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$zip = Join-Path $dist "market_data.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
$files = @("plugin.yaml", "provider.py", "quote_client.py", "finance_client.py", "finance_mapper.py", "README.md") |
    ForEach-Object { Join-Path $root $_ }
Compress-Archive -Path $files -DestinationPath $zip -CompressionLevel Optimal
Write-Output "built: $zip"
Get-Item $zip | Select-Object Name, Length | Format-Table -AutoSize
