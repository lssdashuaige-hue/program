$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot "backend\.env"

function Save-DeepSeekConfiguration {
    param([Parameter(Mandatory = $true)][string]$ApiKey)

    $values = [ordered]@{
        "LLM_PROVIDER" = "deepseek"
        "DEEPSEEK_API_KEY" = $ApiKey.Trim()
        "DEEPSEEK_BASE_URL" = "https://api.deepseek.com"
        "DEEPSEEK_REFLECTION_MODEL" = "deepseek-v4-pro"
        "DEEPSEEK_REVIEW_MODEL" = "deepseek-v4-pro"
        "DEEPSEEK_REFLECTION_REASONING_EFFORT" = "high"
        "DEEPSEEK_REVIEW_REASONING_EFFORT" = "high"
    }

    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath -Encoding utf8) {
            $lines.Add($line)
        }
    }

    foreach ($entry in $values.GetEnumerator()) {
        $prefix = "$($entry.Key)="
        $replacement = "$prefix$($entry.Value)"
        $updated = $false

        for ($index = 0; $index -lt $lines.Count; $index++) {
            if ($lines[$index].StartsWith($prefix, [StringComparison]::Ordinal)) {
                $lines[$index] = $replacement
                $updated = $true
                break
            }
        }

        if (-not $updated) {
            $lines.Add($replacement)
        }
    }

    [IO.File]::WriteAllLines(
        $envPath,
        $lines,
        [Text.UTF8Encoding]::new($false)
    )
}

$form = [Windows.Forms.Form]::new()
$form.Text = "PAS DeepSeek API Setup"
$form.Size = [Drawing.Size]::new(560, 220)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = [Windows.Forms.Label]::new()
$label.Text = "Paste your DeepSeek API Key:"
$label.Location = [Drawing.Point]::new(24, 24)
$label.AutoSize = $true
$form.Controls.Add($label)

$keyBox = [Windows.Forms.TextBox]::new()
$keyBox.Location = [Drawing.Point]::new(24, 54)
$keyBox.Size = [Drawing.Size]::new(496, 28)
$keyBox.UseSystemPasswordChar = $true
$form.Controls.Add($keyBox)

$note = [Windows.Forms.Label]::new()
$note.Text = "The key is stored only in backend\.env and is ignored by Git."
$note.Location = [Drawing.Point]::new(24, 90)
$note.AutoSize = $true
$form.Controls.Add($note)

$saveButton = [Windows.Forms.Button]::new()
$saveButton.Text = "Save"
$saveButton.Location = [Drawing.Point]::new(354, 126)
$saveButton.Size = [Drawing.Size]::new(80, 32)
$form.Controls.Add($saveButton)

$cancelButton = [Windows.Forms.Button]::new()
$cancelButton.Text = "Cancel"
$cancelButton.Location = [Drawing.Point]::new(440, 126)
$cancelButton.Size = [Drawing.Size]::new(80, 32)
$form.Controls.Add($cancelButton)

$saveButton.Add_Click({
    if ([string]::IsNullOrWhiteSpace($keyBox.Text)) {
        [Windows.Forms.MessageBox]::Show(
            "Please paste an API key first.",
            "PAS DeepSeek API Setup",
            [Windows.Forms.MessageBoxButtons]::OK,
            [Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }

    Save-DeepSeekConfiguration -ApiKey $keyBox.Text
    $keyBox.Clear()
    [Windows.Forms.MessageBox]::Show(
        "Setup complete.",
        "PAS DeepSeek API Setup",
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    $form.DialogResult = [Windows.Forms.DialogResult]::OK
    $form.Close()
})

$cancelButton.Add_Click({
    $form.DialogResult = [Windows.Forms.DialogResult]::Cancel
    $form.Close()
})

$form.AcceptButton = $saveButton
$form.CancelButton = $cancelButton
$form.Add_Shown({ $keyBox.Focus() })
[void]$form.ShowDialog()
