"""Consulta os processos que escutam em uma porta TCP local no Windows."""

import os
import subprocess


def stop_server_process(pid: str, *names: str, tree: bool = False) -> bool:
    """Encerra o processo apenas se o nome ainda corresponder ao servidor."""
    command = """
        $ErrorActionPreference = 'Stop'
        $process = Get-Process -Id ([int]$env:VICTORIQUE_SERVER_PID)
        $null = $process.Handle
        if ($process.ProcessName -notin $env:VICTORIQUE_SERVER_NAMES.Split('|')) { exit 1 }
        if ($env:VICTORIQUE_SERVER_TREE -eq '1') {
            taskkill /PID $process.Id /T /F | Out-Null
        }
        if (!$process.HasExited) { $process.Kill() }
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "VICTORIQUE_SERVER_PID": pid, "VICTORIQUE_SERVER_NAMES": "|".join(names),
             "VICTORIQUE_SERVER_TREE": "1" if tree else "0"},
        capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def listening_pids(port: int, host: str | None = None) -> set[str]:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
        errors="replace", timeout=10, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    addresses = {"0.0.0.0", "::", host}
    if host == "localhost":
        addresses.update(("127.0.0.1", "::1"))
    pids = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 5 or fields[0].upper() != "TCP":
            continue
        address, _, local_port = fields[1].rpartition(":")
        if local_port != str(port) or (host and address.strip("[]") not in addresses):
            continue
        # Windows translates the state name, but a listener has remote port 0.
        if fields[2].endswith(":0") and fields[4].isdigit() and fields[4] != "0":
            pids.add(fields[4])
    return pids
