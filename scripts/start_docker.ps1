$ErrorActionPreference = 'Stop'

$EnvFile = '.env'
$Registry = if ([string]::IsNullOrEmpty($env:REGISTRY)) { 'ghcr.io/dograh-hq' } else { $env:REGISTRY }
$EnableTelemetry = if ([string]::IsNullOrEmpty($env:ENABLE_TELEMETRY)) { 'true' } else { $env:ENABLE_TELEMETRY }
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function New-HexSecret {
    $bytes = [byte[]]::new(32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}


function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $resolvedPath = (Resolve-Path $Path).Path
    foreach ($line in [System.IO.File]::ReadLines($resolvedPath)) {
        if ($line.StartsWith("$Key=")) {
            return $line.Substring($Key.Length + 1)
        }
    }

    return $null
}

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $updated = $false

    if (Test-Path $Path) {
        $resolvedPath = (Resolve-Path $Path).Path
        foreach ($line in [System.IO.File]::ReadLines($resolvedPath)) {
            if ($line.StartsWith("$Key=")) {
                $lines.Add("$Key=$Value")
                $updated = $true
            } else {
                $lines.Add($line)
            }
        }
    }

    if (-not $updated) {
        $lines.Add("$Key=$Value")
    }

    [System.IO.File]::WriteAllLines((Join-Path (Get-Location) $Path), $lines, $Utf8NoBom)
}

function Get-PostgresVolumeName {
    try {
        $configJson = docker compose config --format json 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($configJson)) {
            $config = $configJson | ConvertFrom-Json
            $volumeName = $config.volumes.postgres_data.name
            if (-not [string]::IsNullOrEmpty($volumeName)) {
                return $volumeName
            }
        }
    } catch {
        # Fall back to Compose's default project-name convention below.
    }

    $projectName = if ([string]::IsNullOrEmpty($env:COMPOSE_PROJECT_NAME)) {
        (Split-Path -Leaf (Get-Location).Path).ToLowerInvariant() -replace '[^a-z0-9_-]', ''
    } else {
        $env:COMPOSE_PROJECT_NAME.ToLowerInvariant() -replace '[^a-z0-9_-]', ''
    }

    return "${projectName}_postgres_data"
}

function Test-DockerVolumeExists {
    param([string]$Name)

    docker volume inspect $Name *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-PostgresReady {
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        docker compose exec -T postgres pg_isready -U postgres *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 1
    }

    Write-Error 'Postgres did not become ready while syncing POSTGRES_PASSWORD.'
    exit 1
}

function Sync-PostgresPassword {
    param([string]$Password)

    if ([string]::IsNullOrEmpty($Password)) {
        return
    }

    $volumeName = Get-PostgresVolumeName
    if ([string]::IsNullOrEmpty($volumeName) -or -not (Test-DockerVolumeExists $volumeName)) {
        return
    }

    Write-Host "Existing Postgres volume detected; syncing postgres password from $EnvFile."
    $env:REGISTRY = $Registry
    $env:ENABLE_TELEMETRY = $EnableTelemetry
    docker compose up -d postgres
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Wait-PostgresReady

    "ALTER USER postgres WITH PASSWORD :'dograh_password';" | docker compose exec -T postgres psql `
        -U postgres `
        -d postgres `
        -v 'ON_ERROR_STOP=1' `
        -v "dograh_password=$Password" > $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Failed to sync POSTGRES_PASSWORD with the existing Postgres volume.'
        exit $LASTEXITCODE
    }

    Write-Host 'Postgres password synced.'
}

if (-not (Test-Path 'docker-compose.yaml')) {
    Write-Error 'docker-compose.yaml not found. Download it first, then re-run this script.'
    exit 1
}

$envFileExisted = Test-Path $EnvFile

$existingSecret = Get-DotEnvValue -Path $EnvFile -Key 'OSS_JWT_SECRET'
if ([string]::IsNullOrEmpty($existingSecret)) {
    Set-DotEnvValue -Path $EnvFile -Key 'OSS_JWT_SECRET' -Value (New-HexSecret)
    Write-Host "Created OSS_JWT_SECRET in $EnvFile."
} else {
    Write-Host "OSS_JWT_SECRET is already set in $EnvFile."
}

$existingPostgresPassword = Get-DotEnvValue -Path $EnvFile -Key 'POSTGRES_PASSWORD'
if ([string]::IsNullOrEmpty($existingPostgresPassword)) {
    if (-not $envFileExisted) {
        Set-DotEnvValue -Path $EnvFile -Key 'POSTGRES_PASSWORD' -Value (New-HexSecret)
        Write-Host "Created POSTGRES_PASSWORD in $EnvFile."
    } else {
        Write-Host "POSTGRES_PASSWORD is not set in $EnvFile; keeping the docker-compose fallback for existing local data volumes."
    }
} else {
    Write-Host "POSTGRES_PASSWORD is already set in $EnvFile."
}

$existingRedisPassword = Get-DotEnvValue -Path $EnvFile -Key 'REDIS_PASSWORD'
if ([string]::IsNullOrEmpty($existingRedisPassword)) {
    Set-DotEnvValue -Path $EnvFile -Key 'REDIS_PASSWORD' -Value (New-HexSecret)
    Write-Host "Created REDIS_PASSWORD in $EnvFile."
} else {
    Write-Host "REDIS_PASSWORD is already set in $EnvFile."
}

$s3Bucket = Get-DotEnvValue -Path $EnvFile -Key 'S3_BUCKET'
if ([string]::IsNullOrEmpty($s3Bucket)) { $s3Bucket = $env:S3_BUCKET }
if ([string]::IsNullOrEmpty($s3Bucket)) { throw 'Set S3_BUCKET and AWS credentials (or an IAM role) in .env before starting. See deploy/abera/IMAGE_OPTIMIZATION.md.' }
Set-DotEnvValue -Path $EnvFile -Key 'S3_BUCKET' -Value $s3Bucket
if (-not (Get-DotEnvValue -Path $EnvFile -Key 'S3_REGION')) { Set-DotEnvValue -Path $EnvFile -Key 'S3_REGION' -Value 'us-east-2' }
$composeArgs = @()
if ((Get-DotEnvValue -Path $EnvFile -Key 'ENABLE_CLOUDFLARE_TUNNEL') -eq 'true') { $composeArgs += @('--profile', 'tunnel') }
elseif (-not (Get-DotEnvValue -Path $EnvFile -Key 'BACKEND_API_ENDPOINT')) { Set-DotEnvValue -Path $EnvFile -Key 'BACKEND_API_ENDPOINT' -Value 'http://localhost:8000' }

Write-Host ''
Write-Host "Docker registry: $Registry"
Write-Host ''
Write-Host 'This will run:'
Write-Host "  `$env:REGISTRY = '$Registry'; `$env:ENABLE_TELEMETRY = '$EnableTelemetry'; docker compose $($composeArgs -join " ") up --pull always"
Write-Host ''

$answer = Read-Host 'Start Dograh now? [Y/n]'
if ($answer -match '^[Nn]') {
    Write-Host 'Dograh was not started.'
    exit 0
}

$env:REGISTRY = $Registry
$env:ENABLE_TELEMETRY = $EnableTelemetry
Sync-PostgresPassword -Password (Get-DotEnvValue -Path $EnvFile -Key 'POSTGRES_PASSWORD')
docker compose @composeArgs up --pull always
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
