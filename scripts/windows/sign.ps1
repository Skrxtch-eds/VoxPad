[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Check', 'Sign', 'Audit')][string]$Mode,
    [string]$Path,
    [string]$Report,
    [string]$Publisher
)

$ErrorActionPreference = 'Stop'

try {
    if ($Mode -ne 'Audit') {
        $thumbprint = $env:VOXPAD_SIGN_CERT_SHA1 -replace '\s', ''
        if ($thumbprint -notmatch '^[0-9A-Fa-f]{40}$') {
            throw 'Trusted Code Signing is not configured. Set VOXPAD_SIGN_CERT_SHA1 to a certificate in Cert:\CurrentUser\My. See docs/windows-signing.md.'
        }
        $certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$thumbprint"
        if (!$certificate.HasPrivateKey -or $certificate.Subject -eq $certificate.Issuer -or
            $certificate.NotAfter -le (Get-Date) -or $certificate.NotBefore -gt (Get-Date) -or
            '1.3.6.1.5.5.7.3.3' -notin @($certificate.EnhancedKeyUsageList.ObjectId) -or
            !$certificate.Verify()) {
            throw 'A current, trusted Code Signing certificate with a private key is required. Self-signed certificates are not supported.'
        }
        $signTool = $env:VOXPAD_SIGNTOOL
        if (!$signTool) {
            $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
            if ($command) { $signTool = $command.Source }
            else {
                $signTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
                    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
            }
        }
        if (!$signTool -or !(Test-Path -LiteralPath $signTool -PathType Leaf)) {
            throw 'Install SignTool from the Windows SDK, or set VOXPAD_SIGNTOOL to signtool.exe.'
        }
        $timestamp = $env:VOXPAD_SIGN_TIMESTAMP_URL
        if (!$timestamp) { $timestamp = 'http://timestamp.digicert.com' }
        if ($timestamp -notmatch '^https?://') { throw 'An RFC 3161 timestamp URL is required.' }
        if ($Mode -eq 'Check') {
            Write-Output 'Trusted Code Signing configuration is available.'
            exit 0
        }
    }
    if (!$Path) { throw '-Path must specify a file or distribution directory.' }
    $target = Get-Item -LiteralPath $Path
    $files = if ($target.PSIsContainer) {
        @(Get-ChildItem -LiteralPath $target.FullName -Recurse -File |
            Where-Object { $_.Extension.ToLowerInvariant() -in @('.exe', '.dll', '.pyd') })
    } else { @($target) }
    if (!$files.Count) { throw 'No executable files found for signature verification.' }
    $results = @(
        foreach ($file in $files) {
            $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
            if ($Publisher -and $signature.SignerCertificate.Subject -notlike "*$Publisher*") {
                throw "Unexpected publisher: $($file.FullName)"
            }
            if ($Mode -eq 'Sign' -and $signature.Status -eq 'NotSigned') {
                & $signTool sign /sha1 $thumbprint /s My /fd SHA256 /tr $timestamp /td SHA256 /d VoxPad $file.FullName | Out-Host
                if ($LASTEXITCODE -ne 0) { throw "SignTool failed: $($file.FullName)" }
                & $signTool verify /pa /all $file.FullName | Out-Host
                if ($LASTEXITCODE -ne 0) { throw "SignTool verification failed: $($file.FullName)" }
                $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
                if (!$signature.TimeStamperCertificate -or $signature.SignerCertificate.Thumbprint -ne $thumbprint) {
                    throw "Missing timestamp or unexpected publisher: $($file.FullName)"
                }
            }
            # Never replace an invalid signature; preserve valid upstream signatures.
            [pscustomobject]@{
                file = $file.FullName
                status = [string]$signature.Status
                publisher = $signature.SignerCertificate.Subject
                thumbprint = $signature.SignerCertificate.Thumbprint
            }
        }
    )
    if ($Report) {
        ConvertTo-Json -InputObject $results -Depth 3 | Set-Content -LiteralPath $Report -Encoding UTF8
    }
    $invalid = @($results | Where-Object { $_.status -ne 'Valid' })
    Write-Output "Authenticode: $($results.Count - $invalid.Count)/$($results.Count) valid."
    if ($invalid.Count) {
        $invalid | Format-Table file, status -AutoSize | Out-Host
        throw 'Unsigned or invalid binaries cannot be released for Smart App Control. See docs/windows-signing.md.'
    }
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
