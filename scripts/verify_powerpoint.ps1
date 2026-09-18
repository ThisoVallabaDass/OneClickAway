param(
    [Parameter(Mandatory=$true)][string]$Presentation,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Optional visual QA on a Windows workstation with Microsoft PowerPoint.
# Opens this deck read-only, exports every slide, and checks generated text bounds.
$deckPath = (Resolve-Path -LiteralPath $Presentation).Path
$renderPath = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $renderPath -Force | Out-Null
$office = New-Object -ComObject PowerPoint.Application
$deck = $null
try {
    $deck = $office.Presentations.Open($deckPath, -1, 0, 0)
    $deck.Export($renderPath, 'PNG', 1600, 900)
    $issues = @()
    $checked = 0
    foreach ($slide in $deck.Slides) {
        foreach ($shape in $slide.Shapes) {
            if ($shape.AlternativeText -ne 'Generated presentation content' -or -not $shape.HasTextFrame) { continue }
            $range = $shape.TextFrame2.TextRange
            if (-not $range.Text.Trim()) { continue }
            $checked++
            if ($range.BoundHeight -gt $shape.Height + 2 -or $range.BoundWidth -gt $shape.Width + 2 -or
                $range.BoundTop + $range.BoundHeight -gt $deck.PageSetup.SlideHeight + 2 -or
                $range.BoundLeft + $range.BoundWidth -gt $deck.PageSetup.SlideWidth + 2) {
                $issues += [pscustomobject]@{slide=$slide.SlideIndex;shape=$shape.Name;text=$range.Text;boxWidth=$shape.Width;boxHeight=$shape.Height;textWidth=$range.BoundWidth;textHeight=$range.BoundHeight}
            }
        }
    }
    $report = [pscustomobject]@{presentation=$deckPath;slides=$deck.Slides.Count;checkedTextShapes=$checked;overflowCount=$issues.Count;issues=$issues}
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $renderPath 'verification.json') -Encoding utf8
    $report | Select-Object slides,checkedTextShapes,overflowCount
} finally {
    if ($null -ne $deck) { $deck.Close(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($deck) }
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($office)
}
