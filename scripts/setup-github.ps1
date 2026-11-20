[Diagnostics.CodeAnalysis.SuppressMessageAttribute("PSUseDeclaredVarsMoreThanAssignments", "")]
param(
    [Parameter(Mandatory = $false)]
    [string]$RemoteUrl,

    [Parameter(Mandatory = $false)]
    [switch]$CreateInitialCommit
)

$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not available on PATH."
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".git")) {
    git init
    if ($LASTEXITCODE -ne 0) {
        throw "Git could not initialize the repository."
    }
}

$hasCommit = $false
git rev-parse --verify HEAD 2>$null
if ($LASTEXITCODE -eq 0) {
    $hasCommit = $true
}

if ($hasCommit) {
    git branch -M main
    if ($LASTEXITCODE -ne 0) {
        throw "Could not rename the current branch to main."
    }

    git show-ref --verify --quiet refs/heads/develop
    if ($LASTEXITCODE -eq 0) {
        git switch develop
    } else {
        git switch -c develop
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create or switch to the develop branch."
    }
    git switch main
    if ($LASTEXITCODE -ne 0) {
        throw "Could not switch back to the main branch."
    }
} else {
    git symbolic-ref HEAD refs/heads/main 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not prepare the unborn main branch."
    }
}

if ($RemoteUrl) {
    git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        git remote add origin $RemoteUrl
    } else {
        git remote set-url origin $RemoteUrl
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Could not configure the origin remote."
    }
}

if ($CreateInitialCommit) {
    git rev-parse --verify HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
        git add -A
        if ($LASTEXITCODE -ne 0) {
            throw "Could not stage project files."
        }
        git commit -m "chore: initial project"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the initial commit. Configure Git user.name and user.email, then rerun with -CreateInitialCommit."
        }
    }

    git show-ref --verify --quiet refs/heads/develop
    if ($LASTEXITCODE -ne 0) {
        git switch -c develop
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the develop branch."
        }
    } else {
        git switch develop
        if ($LASTEXITCODE -ne 0) {
            throw "Could not switch to the develop branch."
        }
    }
    git switch main
    if ($LASTEXITCODE -ne 0) {
        throw "Could not switch back to the main branch."
    }
}

Write-Host "Git repository prepared in $ProjectRoot."
Write-Host "Current branch: $(git branch --show-current)"
Write-Host "Next: commit changes, push main and develop, and configure Docker Hub secrets."
