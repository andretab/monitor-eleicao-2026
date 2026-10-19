# Robô reserva da apuração no PC (domingo, 25/10). Agendado no Windows para as 16h50 (tarefa
# "Monitor Eleicao - reserva domingo"). Liga os dois coletores em modo reserva: cada um acompanha o TSE
# a cada minuto e só publica no site se o robô do GitHub ficar mais de 4 minutos sem publicar.
#
#   powershell -ExecutionPolicy Bypass -File scripts\reserva-domingo.ps1            # noite real
#   powershell -ExecutionPolicy Bypass -File scripts\reserva-domingo.ps1 -Simular   # ensaio
param([switch]$Simular, [double]$Velocidade = 20, [int]$Ate = 0)

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$logs = Join-Path $raiz "apuracao\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$carimbo = Get-Date -Format "yyyyMMdd-HHmm"
$geral = Join-Path $logs "reserva-$carimbo.log"
"$(Get-Date -Format 'HH:mm:ss') robô reserva ligado (simulação: $Simular)" | Tee-Object -FilePath $geral

# Código e dados mais recentes (o robô do GitHub pode ter publicado melhorias durante a semana).
git pull --rebase --autostash origin main 2>&1 | Tee-Object -FilePath $geral -Append

$python = (Get-Command python -ErrorAction Stop).Source
$processos = foreach ($corrida in @("presidente", "rn")) {
    $argumentos = @("-I", "apuracao\coletor.py", "--corrida", $corrida, "--publicar", "--reserva")
    if ($Simular) {
        $argumentos += @("--simular", "--velocidade", "$Velocidade", "--sim-transferencia", "0.62", "--sim-swing", "0.01")
        if ($Ate -gt 0) { $argumentos += @("--ate", "$Ate") }
    }
    else { $argumentos += @("--intervalo", "60") }
    $saida = Join-Path $logs "$corrida-$carimbo.log"
    # Out-Host: a mensagem vai para a tela e o registro sem entrar na lista de processos esperados abaixo.
    "$(Get-Date -Format 'HH:mm:ss') ligando coletor $corrida -> $saida" | Tee-Object -FilePath $geral -Append | Out-Host
    Start-Process -FilePath $python -ArgumentList $argumentos -WorkingDirectory $raiz -NoNewWindow -PassThru `
        -RedirectStandardOutput $saida -RedirectStandardError "$saida.erros"
}
$processos | Wait-Process
"$(Get-Date -Format 'HH:mm:ss') coletores encerrados (apuração concluída ou interrompida)" | Tee-Object -FilePath $geral -Append
