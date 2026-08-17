# Evidências do Network Automation Challenge

Este diretório reúne evidências técnicas e visuais das funcionalidades implementadas no desafio.

## Parte 1 — Automação de Switches Cisco

### 1. Frontend principal
Arquivo: `01-frontend-home.png`

### 2. Inventário Multi-Switch
Arquivo: `02-multiswitch-inventory.png`

### 3. Interfaces e VLANs em múltiplos switches
Arquivo: `03-multiswitch-interfaces.png`

Evidencia VLANs atuais, inventário de interfaces, estado operacional, modo, Access VLAN, Voice VLAN, PortFast e seleção de múltiplas interfaces.

### 4. Operações Multi-Switch
Arquivo: `04-multiswitch-operations.png`

Evidencia Access VLAN, Voice VLAN, descrição, estado administrativo, PortFast, restore default, bounce e aplicação sobre interfaces selecionadas.

### 5. Configuration Management
Arquivo: `05-configuration-management.png`

Evidencia save da running-config em NVRAM, download de running/startup, comparação Running x Startup e backup Local/FTP/SFTP/TFTP.

### 6. Provisionamento de switches
Arquivo: `06-switch-provisioning.png`

Evidencia geração, visualização, customização, download e deploy da baseline corporativa.

### 7. Troubleshooting — Ping
Arquivo: `07-troubleshooting-ping.png`

### 8. Troubleshooting — Extended Traceroute
Arquivo: `08-troubleshooting-traceroute.png`

### 9. Evidência CLI real
Arquivo: `02-switch-cli-validation.txt`

Contém hostname, VLAN database, interfaces, running-config e startup-config coletados no switch do laboratório.

### 10. Quality Gate
Arquivo: `01-project-validation.txt`

Estado validado:
- Ruff: OK
- Pytest: 495 passed
- Diff check: OK

## Parte 2 — Automação de VPN IPsec

Documento formal:
`../VPN_AUTOMATION_PLAN.md`

### 11. Provisionamento de firewall/branch
Arquivo: `09-firewall-provisioning.png`

### 12. Nautobot — IPAM
Arquivo: `10-nautobot-ipam.png`

### 13. Nautobot — VPN
Arquivo: `11-nautobot-vpn.png`

### 14. Nautobot — detalhes VPN
Arquivo: `12-nautobot-vpn-details.png`

## Artefatos adicionais

- `golden/` — baseline FortiGate/Palo Alto
- `generated/` — configurações geradas
- `backups/` — backups locais
- `templates/` — templates
- `src/` — implementação
- `tests/` — suíte automatizada
- `docs/VPN_AUTOMATION_PLAN.md` — plano formal da Parte 2

## Cobertura dos entregáveis

| Requisito | Evidência |
|---|---|
| Frontend | `01-frontend-home.png` |
| VLANs e interfaces | `03-multiswitch-interfaces.png` |
| Multi-device | `02-multiswitch-inventory.png`, `04-multiswitch-operations.png` |
| Hostname/VLAN na CLI | `02-switch-cli-validation.txt` |
| Save em NVRAM | `05-configuration-management.png` |
| Backup | `05-configuration-management.png`, `backups/` |
| Validação | `01-project-validation.txt` |
| Troubleshooting | `07-troubleshooting-ping.png`, `08-troubleshooting-traceroute.png` |
| Provisionamento de switch | `06-switch-provisioning.png` |
| Plano VPN | `../VPN_AUTOMATION_PLAN.md` |
| Implementação VPN | `09-firewall-provisioning.png` |
| Nautobot/IPAM | `10-nautobot-ipam.png` |
| Objetos VPN | `11-nautobot-vpn.png`, `12-nautobot-vpn-details.png` |
