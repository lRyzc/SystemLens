"""Read hardware identity once, independently from performance sampling."""

import json
import os
import platform
import subprocess


WINDOWS_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$result = @{}
$queries = @{
    cpu = @('Win32_Processor', @('Name'))
    memory = @('Win32_PhysicalMemory', @('Manufacturer','PartNumber','Capacity','ConfiguredClockSpeed','DeviceLocator'))
    disks = @('Win32_DiskDrive', @('Model','Size','InterfaceType'))
    graphics = @('Win32_VideoController', @('Name','VideoProcessor'))
}
foreach ($key in $queries.Keys) {
    try {
        $query = $queries[$key]
        $result[$key] = @(Get-CimInstance -ClassName $query[0] -OperationTimeoutSec 5 | Select-Object -Property $query[1])
    } catch { $result[$key] = @() }
}
ConvertTo-Json -InputObject $result -Depth 5 -Compress
"""


def clean(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.lower() in ('', 'unknown', 'undefined', 'not specified', 'default string',
                         'to be filled by o.e.m.', '00000000'):
        return None
    return value


def positive(value):
    try:
        result = int(value)
        return result if result > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize(payload):
    """Accept CIM's singleton or array forms; never invent missing model names."""
    def rows(key):
        value = payload.get(key, [])
        if isinstance(value, dict):
            value = [value]
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []

    return {
        'cpu': [{'model': clean(row.get('Name'))} for row in rows('cpu')],
        'memory': [{'model': clean(row.get('PartNumber')), 'manufacturer': clean(row.get('Manufacturer')),
                    'capacity': positive(row.get('Capacity')), 'speed_mts': positive(row.get('ConfiguredClockSpeed')),
                    'slot': clean(row.get('DeviceLocator'))} for row in rows('memory')],
        'disks': [{'model': clean(row.get('Model')), 'capacity': positive(row.get('Size')),
                   'interface': clean(row.get('InterfaceType'))} for row in rows('disks')],
        'graphics': [{'model': clean(row.get('Name')), 'processor': clean(row.get('VideoProcessor'))}
                     for row in rows('graphics')],
    }


def discover():
    result = {'status': 'ready', 'cpu': [], 'memory': [], 'disks': [], 'graphics': []}
    if platform.system() != 'Windows':
        result['status'] = 'unsupported'
        return result
    try:
        executable = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                                  'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
        completed = subprocess.run(
            [executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', WINDOWS_QUERY],
            capture_output=True, encoding='utf-8-sig', errors='replace', timeout=25,
            check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise ValueError('Invalid hardware payload')
        result.update(normalize(payload))
    except (OSError, subprocess.SubprocessError, ValueError):
        result['status'] = 'unavailable'
    # The CPU brand string remains available when CIM is restricted.
    if not any(cpu['model'] for cpu in result['cpu']):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                model = clean(winreg.QueryValueEx(key, 'ProcessorNameString')[0])
                if model:
                    result['cpu'] = [{'model': model}]
        except OSError:
            pass
    if not all(result[key] for key in ('cpu', 'memory', 'disks', 'graphics')):
        result['status'] = 'partial'
    return result
