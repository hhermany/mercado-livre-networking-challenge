# MVP Switch Cisco - Checkpoint

Status: funcional e validado em equipamento Cisco real.

## Escopo obrigatório do Challenge - Parte 1

- Automação desenvolvida em Python.
- Frontend web com Flask.
- Conexão e configuração de switch Cisco.
- Configuração de VLANs.
- Configuração de hostname.
- Aplicação das configurações no equipamento.
- Salvamento da running-config para startup-config/NVRAM.
- Backup de configuração.
- Validação de configuração.
- Alertas para divergências/erros.
- Projeto gerenciado através de Git.

## Funcionalidades adicionais implementadas

- Gerenciamento de múltiplos switches.
- Inventário real de interfaces.
- Identificação de estado operacional das interfaces.
- Suporte a diferentes nomenclaturas de interfaces Cisco.
- Configuração de Access VLAN e Voice VLAN.
- Alteração de descrição de interfaces.
- Shutdown / no shutdown.
- Validação de caracteres e tamanho de description.
- Backup de running-config e startup-config.
- Comparação/diff de configurações.
- Operações e diagnóstico de interfaces.
- Provisionamento estruturado de novas filiais.
- Candidate Configuration antes da aplicação.
- Proteção da primeira interface física como Provision Port.
- Provision Port mantida fora das configurações de usuário/uplink.
- Detecção de capabilities da plataforma antes da geração do Candidate.
- Tratamento das variações de sintaxe `ip domain name` / `ip domain-name`.
- Baseline Cisco para Branch.
- AAA / RADIUS / 802.1X.
- DHCP Snooping.
- Rapid-PVST / PortFast / BPDU Guard.
- Management VLAN e uplink trunk.
- DNS, NTP, Syslog e SNMP.
- SNMP baseline mínima, sem habilitação indiscriminada de traps.
- Deploy real do Candidate no switch.
- Aplicação ordenada da configuração.
- Tratamento de erros retornados pelo parser IOS.
- Interrupção do deploy diante de erro.
- Validação pós-deploy através da running-config.
- Startup-config não é salva automaticamente pelo Deploy Config.
- Preflight e Candidate adaptados às capabilities do equipamento.
- Testes automatizados e Quality Gate com pytest, Ruff e git diff --check.

## Decisões de engenharia

### Provision Port

A primeira interface física é reservada para provisionamento e gerenciamento
temporário.

Ela:

- permanece em modo routed;
- mantém o endereço da rede 172.28.255.0/24;
- recebe a descrição `## PORTA PARA PROVISIONAMENTO ##`;
- não entra em interface range de usuários;
- não pode ser selecionada como uplink;
- não tem sua configuração operacional sobrescrita pelo Candidate.

O objetivo é preservar acesso ao equipamento durante todo o provisionamento.

### Candidate Configuration

A configuração é gerada antes do deploy e pode ser visualizada pelo operador.

O Deploy Config utiliza exatamente o Candidate armazenado, sem regenerá-lo
silenciosamente.

### Deploy

A configuração é aplicada em blocos ordenados para preservar dependências
e contextos Cisco IOS.

O executor:

- detecta erros do parser;
- interrompe a aplicação quando um bloco falha;
- coleta running-config após sucesso;
- não executa `write memory` automaticamente.

### Compatibilidade

O preflight detecta características da plataforma antes da geração do Candidate,
evitando incluir comandos não suportados quando possível.

### SNMP

A baseline do MVP mantém somente:

- community RO;
- destino SNMP.

A habilitação ampla de traps ficou deliberadamente fora do MVP.

## Validação em equipamento real

O fluxo completo foi testado contra switch Cisco real:

1. descoberta do equipamento;
2. inventário;
3. geração do Candidate;
4. preflight;
5. visualização do Candidate;
6. aplicação pelo Deploy Config;
7. configuração efetivamente aplicada;
8. validação pós-deploy.

## Estado deste checkpoint

Este checkpoint representa a versão funcional considerada MVP do módulo de
automação de switches Cisco do Networking Challenge.

Otimizações futuras de performance do deploy são consideradas melhorias e não
bloqueiam o MVP funcional.
