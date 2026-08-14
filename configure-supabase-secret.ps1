$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot "backend\.env"

function Test-SupabaseSecretKey {
    param([Parameter(Mandatory = $true)][string]$SecretKey)

    $trimmed = $SecretKey.Trim()
    if ($trimmed.StartsWith("sb_secret_", [StringComparison]::Ordinal)) {
        return $trimmed.Length -ge 24
    }

    # Legacy keys are JWTs. Accept only a payload that explicitly declares the
    # service_role; an anon JWT must never become the backend write credential.
    $segments = $trimmed.Split('.')
    if ($segments.Count -ne 3) {
        return $false
    }

    try {
        $payloadSegment = $segments[1].Replace('-', '+').Replace('_', '/')
        switch ($payloadSegment.Length % 4) {
            2 { $payloadSegment += '==' }
            3 { $payloadSegment += '=' }
            1 { return $false }
        }
        $payloadBytes = [Convert]::FromBase64String($payloadSegment)
        $payload = [Text.Encoding]::UTF8.GetString($payloadBytes) | ConvertFrom-Json
        return $payload.role -ceq 'service_role'
    }
    catch {
        return $false
    }
}

function Get-LocalEnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Test-Path -LiteralPath $envPath)) {
        return $null
    }

    $prefix = "$Name="
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding utf8) {
        if ($line.StartsWith($prefix, [StringComparison]::Ordinal)) {
            return $line.Substring($prefix.Length).Trim()
        }
    }
    return $null
}

function Test-SupabaseSecretKeyAgainstProject {
    param([Parameter(Mandatory = $true)][string]$SecretKey)

    $supabaseUrl = Get-LocalEnvValue -Name "SUPABASE_URL"
    if ([string]::IsNullOrWhiteSpace($supabaseUrl)) {
        return $false
    }

    $probeUrl = "$($supabaseUrl.TrimEnd('/'))/rest/v1/conversations?select=id&limit=0"
    $client = $null
    $request = $null
    $response = $null
    try {
        Add-Type -AssemblyName System.Net.Http
        $client = [Net.Http.HttpClient]::new()
        $client.Timeout = [TimeSpan]::FromSeconds(15)
        $request = [Net.Http.HttpRequestMessage]::new(
            [Net.Http.HttpMethod]::Get,
            $probeUrl
        )
        $request.Headers.TryAddWithoutValidation(
            "apikey",
            $SecretKey.Trim()
        ) | Out-Null
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        return $response.IsSuccessStatusCode
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $request) { $request.Dispose() }
        if ($null -ne $client) { $client.Dispose() }
    }
}

function Save-SupabaseSecretKey {
    param([Parameter(Mandatory = $true)][string]$SecretKey)

    $prefix = "SUPABASE_SECRET_KEY="
    $replacement = "$prefix$($SecretKey.Trim())"
    $lines = [System.Collections.Generic.List[string]]::new()

    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath -Encoding utf8) {
            $lines.Add($line)
        }
    }

    for ($index = $lines.Count - 1; $index -ge 0; $index--) {
        if ($lines[$index].StartsWith($prefix, [StringComparison]::Ordinal)) {
            $lines.RemoveAt($index)
        }
    }
    $lines.Add($replacement)

    [IO.File]::WriteAllLines(
        $envPath,
        $lines,
        [Text.UTF8Encoding]::new($false)
    )
}

$form = [Windows.Forms.Form]::new()
$form.Text = "PAS Supabase Server Key Setup"
$form.Size = [Drawing.Size]::new(640, 270)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = [Windows.Forms.Label]::new()
$label.Text = "Paste the Supabase secret key for the PAS project:"
$label.Location = [Drawing.Point]::new(24, 22)
$label.AutoSize = $true
$form.Controls.Add($label)

$keyBox = [Windows.Forms.TextBox]::new()
$keyBox.Location = [Drawing.Point]::new(24, 54)
$keyBox.Size = [Drawing.Size]::new(576, 28)
$keyBox.UseSystemPasswordChar = $true
$form.Controls.Add($keyBox)

$note = [Windows.Forms.Label]::new()
$note.Text = "Use Settings > API Keys > Secret key (not the publishable/anon key).`r`nThe key is stored only in backend\.env, which Git ignores. It is never shown here after saving."
$note.Location = [Drawing.Point]::new(24, 92)
$note.Size = [Drawing.Size]::new(576, 52)
$form.Controls.Add($note)

$saveButton = [Windows.Forms.Button]::new()
$saveButton.Text = "Save"
$saveButton.Location = [Drawing.Point]::new(434, 170)
$saveButton.Size = [Drawing.Size]::new(80, 32)
$form.Controls.Add($saveButton)

$cancelButton = [Windows.Forms.Button]::new()
$cancelButton.Text = "Cancel"
$cancelButton.Location = [Drawing.Point]::new(520, 170)
$cancelButton.Size = [Drawing.Size]::new(80, 32)
$form.Controls.Add($cancelButton)

$saveButton.Add_Click({
    if (-not (Test-SupabaseSecretKey -SecretKey $keyBox.Text)) {
        [Windows.Forms.MessageBox]::Show(
            "That does not look like a Supabase secret key. Use the secret key, not the publishable/anon key.",
            "PAS Supabase Server Key Setup",
            [Windows.Forms.MessageBoxButtons]::OK,
            [Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }

    $form.UseWaitCursor = $true
    $saveButton.Enabled = $false
    $cancelButton.Enabled = $false
    $validForProject = Test-SupabaseSecretKeyAgainstProject -SecretKey $keyBox.Text
    $form.UseWaitCursor = $false
    $saveButton.Enabled = $true
    $cancelButton.Enabled = $true

    if (-not $validForProject) {
        [Windows.Forms.MessageBox]::Show(
            "Supabase did not accept this key for the configured PAS project. Copy an active Secret key from this project's Settings > API Keys page.",
            "PAS Supabase Server Key Setup",
            [Windows.Forms.MessageBoxButtons]::OK,
            [Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        return
    }

    Save-SupabaseSecretKey -SecretKey $keyBox.Text
    $keyBox.Clear()
    [Windows.Forms.MessageBox]::Show(
        "Server key saved locally. Restart the PAS backend before testing conversation history.",
        "PAS Supabase Server Key Setup",
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    $form.DialogResult = [Windows.Forms.DialogResult]::OK
    $form.Close()
})

$cancelButton.Add_Click({
    $keyBox.Clear()
    $form.DialogResult = [Windows.Forms.DialogResult]::Cancel
    $form.Close()
})

$form.AcceptButton = $saveButton
$form.CancelButton = $cancelButton
$form.Add_Shown({ $keyBox.Focus() })
[void]$form.ShowDialog()
