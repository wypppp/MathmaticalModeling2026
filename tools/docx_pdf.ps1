# 用本机 Word/WPS 把 paper/build/论文.docx 导出 PDF，并报告页数（摘要 1 页、正文 ≤ 30 页的检查）。
# 用法：powershell -File tools/docx_pdf.ps1 [docx 路径]
param([string]$Docx = "paper\build\论文.docx")
$src = (Resolve-Path $Docx).Path
$pdf = $src -replace '\.docx$', '.pdf'
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$d = $w.Documents.Open($src, $false, $true)
$d.Repaginate()
function Get-PageOf([string]$key) {
    $r = $d.Content; $f = $r.Find; $f.ClearFormatting()
    if ($f.Execute($key)) { return $r.Information(3) } else { return $null }
}
$total = $d.ComputeStatistics(2)
$body = Get-PageOf "一、问题重述"
$appx = Get-PageOf "附录 A"
"总页数 $total；正文起于第 $body 页；附录起于第 $appx 页"
if ($body -ne 2) { "警告：摘要不是恰好 1 页（正文应从第 2 页开始）" }
if ($appx) { "正文页数（含参考文献等，不含附录）约 $($appx - $body) 页（上限 30）" }
$d.ExportAsFixedFormat($pdf, 17)
$d.Close($false)
try { $w.Quit() } catch {}
"PDF：$pdf，{0:N1} MB（上限 20 MB）" -f ((Get-Item $pdf).Length / 1MB)
