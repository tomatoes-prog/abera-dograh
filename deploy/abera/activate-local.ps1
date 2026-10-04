param(
    [string]$ProjectName = 'abera-dograh',
    [string]$ApiImage = 'abera/dograh-api:local-services',
    [string]$UiImage = 'abera/dograh-ui:local-services'
)

# Update an existing local installation while preserving its actual runtime
# configuration. The Compose files may belong to a different Git worktree.
$ErrorActionPreference = 'Stop'

function Read-Container([string]$ContainerName) {
    $containerJson = & docker inspect $ContainerName
    if ($LASTEXITCODE -ne 0) { throw "No se encontró el contenedor $ContainerName." }
    return ($containerJson | ConvertFrom-Json)[0]
}

function Read-Environment($Container) {
    $values = @{}
    foreach ($entry in $Container.Config.Env) {
        $separator = $entry.IndexOf('=')
        if ($separator -gt 0) {
            $values[$entry.Substring(0, $separator)] = $entry.Substring($separator + 1)
        }
    }
    return $values
}

function Escape-ComposeEnvironment([hashtable]$Values) {
    $escaped = @{}
    foreach ($key in $Values.Keys) {
        # Compose interpolates dollars even in JSON. Keep literal credential
        # characters intact, without printing any environment values.
        $escaped[$key] = ([string]$Values[$key]).Replace('$', '$$')
    }
    return $escaped
}

foreach ($image in @($ApiImage, $UiImage)) {
    $null = & docker image inspect $image --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0) { throw "Construye primero la imagen $image." }
}

$api = Read-Container "$ProjectName-api-1"
$ui = Read-Container "$ProjectName-ui-1"
if (
    $api.Config.Labels.'com.docker.compose.project' -ne $ProjectName -or
    $ui.Config.Labels.'com.docker.compose.project' -ne $ProjectName
) { throw 'La API y la UI deben pertenecer al mismo proyecto de Docker Compose.' }

# A mount over application source would hide the newly built image.
foreach ($container in @($api, $ui)) {
    foreach ($mount in $container.Mounts) {
        if ($mount.Destination -in @('/app', '/app/api', '/app/src', '/app/.next')) {
            throw 'La instalación monta código sobre la imagen. Revisa esos montajes antes de actualizarla.'
        }
    }
}

$composeDirectory = $api.Config.Labels.'com.docker.compose.project.working_dir'
$composeFiles = @($api.Config.Labels.'com.docker.compose.project.config_files'.Split(',') |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
if (-not $composeDirectory -or $composeFiles.Count -eq 0) {
    throw 'No se encontraron los archivos de Compose de la instalación actual.'
}

$apiEnv = Read-Environment $api
$uiEnv = Read-Environment $ui
if (-not $apiEnv['S3_BUCKET']) { throw 'La API actual debe tener su almacenamiento S3 configurado.' }
$apiEnv['ENABLE_DOGRAH_MPS'] = 'false'
$apiEnv['ENABLE_TELEMETRY'] = 'false'
$uiEnv['ENABLE_TELEMETRY'] = 'false'
$uiEnv['UI_DEFAULT_LOCALE'] = 'es-419'
$uiEnv['CHATWOOT_URL'] = ''
$uiEnv['CHATWOOT_WEBSITE_TOKEN'] = ''
$uiEnv['ONBOARDING_API_URL'] = ''

$override = @{
    services = @{
        api = @{ image = $ApiImage; environment = (Escape-ComposeEnvironment $apiEnv) }
        ui = @{ image = $UiImage; environment = (Escape-ComposeEnvironment $uiEnv) }
    }
}
$temporaryOverride = Join-Path ([System.IO.Path]::GetTempPath()) ('abera-local-runtime-' + [guid]::NewGuid().ToString('N') + '.json')
$previousBucket = [Environment]::GetEnvironmentVariable('S3_BUCKET', 'Process')
try {
    [System.IO.File]::WriteAllText($temporaryOverride, ($override | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
    # Supply required interpolation before the override restores actual values.
    $env:S3_BUCKET = $apiEnv['S3_BUCKET']
    $composeArguments = @('compose', '--project-name', $ProjectName, '--project-directory', $composeDirectory)
    foreach ($composeFile in $composeFiles) { $composeArguments += @('-f', $composeFile) }
    $composeArguments += @('-f', $temporaryOverride, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'api', 'ui')
    & docker @composeArguments
    if ($LASTEXITCODE -ne 0) { throw 'La actualización no terminó correctamente. Revisa el estado de API y UI.' }
    Write-Host 'API y UI actualizadas. La configuración, las bases y el almacenamiento existentes se conservan.'
} finally {
    [Environment]::SetEnvironmentVariable('S3_BUCKET', $previousBucket, 'Process')
    if (Test-Path -LiteralPath $temporaryOverride) { Remove-Item -LiteralPath $temporaryOverride }
}
