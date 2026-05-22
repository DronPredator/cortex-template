# Recalcula los hashes SRI (sha384) de los scripts CDN usados por el frontend.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\sri_hashes.ps1
#
# Salida: cada URL con su sha384-XXX base64 listo para pegar como
# `integrity="..."` en static/index.html.
#
# Cuándo correrlo:
#  - Cuando subís la versión pineada de algún CDN script (react, babel,
#    marked, dompurify).
#  - Si el browser dice "Failed to find a valid digest in the 'integrity'
#    attribute" → el archivo del CDN cambió o vos cambiaste la versión
#    pero olvidaste actualizar el hash.

$urls = @(
    @{name="react@18.3.1"; url="https://unpkg.com/react@18.3.1/umd/react.production.min.js"},
    @{name="react-dom@18.3.1"; url="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"},
    @{name="@babel/standalone@7.29.4"; url="https://unpkg.com/@babel/standalone@7.29.4/babel.min.js"},
    @{name="marked@12.0.2"; url="https://unpkg.com/marked@12.0.2/marked.min.js"},
    @{name="dompurify@3.2.4"; url="https://unpkg.com/dompurify@3.2.4/dist/purify.min.js"}
)

Write-Host "Calculando SRI sha384 para $($urls.Count) scripts..."
Write-Host ""

foreach ($u in $urls) {
    $tmpFile = [System.IO.Path]::GetTempFileName()
    try {
        Invoke-WebRequest -Uri $u.url -OutFile $tmpFile -UseBasicParsing -TimeoutSec 30
        $sha384 = [Security.Cryptography.SHA384]::Create()
        $bytes = [IO.File]::ReadAllBytes($tmpFile)
        $hashBytes = $sha384.ComputeHash($bytes)
        $base64 = [Convert]::ToBase64String($hashBytes)
        Write-Host "$($u.name)"
        Write-Host "  src=`"$($u.url)`""
        Write-Host "  integrity=`"sha384-$base64`""
        Write-Host "  (size: $($bytes.Length) bytes)"
        Write-Host ""
    } catch {
        Write-Host "[X] $($u.name): $($_.Exception.Message)"
    } finally {
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    }
}

Write-Host "Listo. Pegá los integrity= en static/index.html."
