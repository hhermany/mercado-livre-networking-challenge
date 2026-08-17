# Network Automation Challenge

Plataforma de automação e engenharia de redes desenvolvida em Python para um desafio técnico, integrando gerenciamento multi-device de switches Cisco, provisionamento end-to-end de filiais FortiGate, Palo Alto no datacenter, Nautobot como Source of Truth/IPAM e uma arquitetura de conectividade baseada em VPN IPsec, iBGP e SD-WAN.

O projeto foi construído para reduzir tarefas manuais, padronizar configurações, permitir gerenciamento seguro de múltiplos equipamentos e validar não apenas a configuração enviada, mas também o estado operacional resultante.

A solução utiliza Flask como interface Web, Netmiko para automação CLI, Jinja2 para geração de configurações, Requests para integração com APIs, Paramiko para SFTP, TFTPy para TFTP, SQLite para persistência local e Nautobot como Source of Truth/IPAM.

---

## Principais entregas

O projeto possui dois grandes domínios.

### Gerenciamento e provisionamento de switches Cisco

A aplicação permite cadastrar e gerenciar múltiplos switches e executar operações do dia a dia, incluindo:

- descoberta e inventário de interfaces;
- visualização de estado operacional e administrativo;
- alteração de hostname;
- criação e gerenciamento de VLANs;
- Access VLAN;
- Voice VLAN;
- descrição de interfaces;
- shutdown e no shutdown;
- bounce de portas;
- restauração de interface para o padrão;
- PortFast;
- visualização do database de VLANs;
- Candidate, Diff e Apply;
- comparação Running-config x Startup-config;
- save da running-config em NVRAM;
- backup local;
- backup FTP;
- backup SFTP;
- backup TFTP;
- download individual e em lote pela interface Web;
- ping;
- traceroute;
- operações simultâneas em múltiplos switches;
- provisionamento de novos switches a partir de uma baseline corporativa.

### Provisionamento automatizado de filiais

O segundo domínio automatiza o onboarding de novas filiais FortiGate conectadas ao datacenter por dois túneis IPsec terminados em Palo Alto.

O workflow coordena:

- plano de endereçamento;
- Nautobot/IPAM;
- golden baseline;
- FortiGate;
- Palo Alto;
- VPN IPsec;
- overlays /30;
- iBGP;
- route-maps e communities;
- SD-WAN;
- SLA/health-check;
- Candidate;
- reserva dos recursos;
- deployment;
- commit;
- validação de configuração;
- validação operacional.

A `BRANCH-1` é utilizada como golden/reference branch e possui proteção explícita para não ser utilizada como destino de um novo onboarding.

---

## Arquitetura de automação

```text
                         +-------------------+
                         |     Operador      |
                         +---------+---------+
                                   |
                                   v
                         +---------+---------+
                         |     Flask Web     |
                         +---------+---------+
                                   |
                    +--------------+--------------+
                    |                             |
                    v                             v
             Switch Management             Branch Provisioning
                    |                             |
                    v                             v
            Candidate / Diff              Candidate / Plan
                    |                             |
             +------+-------+              +------+------+
             |              |              |             |
             v              v              v             v
          SQLite        Cisco IOS       Nautobot       Jinja2
        Inventory       Devices         SoT/IPAM      Templates
                                            |             |
                                            +------+------+
                                                   |
                                                   v
                                           Deployment Engine
                                              /         \
                                             v           v
                                        Palo Alto    FortiGate
                                             \           /
                                              \         /
                                               v       v
                                               Validation
```

A interface Web é separada da lógica de negócio. Serviços e drivers específicos tratam comunicação, planejamento, renderização, deployment e validação.

---

## Arquitetura de rede das filiais

Cada filial possui dois caminhos VPN independentes para o datacenter.

```text
                          DATACENTER
                              |
                        +-----+-----+
                        | Palo Alto |
                        +-----+-----+
                         /         \
                        /           \
                   IPsec-1         IPsec-2
                      |               |
                      |     iBGP      |
                      |               |
                      +-------+-------+
                              |
                        +-----+-----+
                        | FortiGate |
                        |  Branch   |
                        +-----+-----+
                              |
                           SD-WAN
                              |
                           Branch LAN
```

Os túneis IPsec são route-based e formam os overlays utilizados para comunicação entre filial e datacenter. Sobre esses overlays são estabelecidas duas adjacências iBGP.

---

## BGP, SD-WAN e Self-Healing

A arquitetura integra roteamento dinâmico e monitoramento de qualidade dos caminhos.

A baseline implementada inclui:

- AS `65001`;
- dois neighbors iBGP;
- iBGP multipath;
- anúncio da LAN da filial;
- anúncio da loopback de gerenciamento;
- communities;
- route-maps;
- route-map preferencial por overlay;
- zona SD-WAN `VPN-DC`;
- health-check `SLA_DC`;
- associação dos overlays ao SLA;
- seleção de caminho baseada no estado do transporte.

O template FortiGate implementa communities e route-maps específicos dos dois overlays e habilita `ibgp-multipath`.

O objetivo do desenho é permitir que falha ou degradação de um caminho seja detectada pelo SD-WAN e que a conectividade continue utilizando o transporte disponível, reduzindo a necessidade de intervenção manual.

A arquitetura segue o princípio de *SD-WAN Self-Healing with BGP*: BGP fornece a troca dinâmica de rotas e o SD-WAN acompanha a qualidade dos transportes usados por essas rotas.

---

## SLA do datacenter

O endereço central:

```text
10.255.255.1
```

é utilizado como referência de reachability das filiais para o datacenter e como destino do health-check `SLA_DC`.

Parâmetros da baseline:

| Métrica | Threshold |
|---|---:|
| Latência | 100 ms |
| Jitter | 20 ms |
| Perda | 5% |
| Intervalo | 1000 ms |
| Timeout | 250 ms |
| Fail time | 2 |
| Recovery time | 10 |

O uso de um destino central estável permite avaliar o caminho do ponto de vista do serviço que a filial precisa alcançar, e não apenas pelo estado físico da WAN.

---

## Golden baseline das filiais

A `BRANCH-1` é a referência para novas filiais.

```text
BRANCH-1 -> Golden / referência
BRANCH-2 -> Provisionada a partir do padrão
BRANCH-3 -> Provisionada a partir do padrão
BRANCH-X -> Nova filial
```

Os artefatos de referência estão no diretório:

```text
golden/
```

A baseline contém snapshots reais de elementos como:

- interfaces;
- IPsec Phase 1;
- IPsec Phase 2;
- BGP;
- route-maps;
- community-lists;
- SD-WAN;
- firewall policies;
- address objects;
- services;
- Palo Alto do datacenter.

O projeto possui verificações de compliance entre a golden e a configuração candidata gerada.

---

## Plano de endereçamento

| Função | Prefixo |
|---|---|
| LAN das filiais | `10.0.0.0/16` |
| Loopbacks de gerenciamento | `172.31.255.0/24` |
| Overlays VPN | `169.255.0.0/16` |
| LAN do datacenter | `10.255.255.0/24` |
| Servidor/SLA do DC | `10.255.255.1` |

As loopbacks seguem uma convenção determinística:

```text
BRANCH-1 -> 172.31.255.1/32
BRANCH-2 -> 172.31.255.2/32
BRANCH-3 -> 172.31.255.3/32
...
BRANCH-X -> 172.31.255.X/32
```

Para cada overlay `/30`:

- primeiro endereço utilizável: Palo Alto / Datacenter;
- segundo endereço utilizável: FortiGate / Branch.

Exemplo validado para a `BRANCH-2`:

| Recurso | Valor |
|---|---|
| LAN | `10.0.1.0/24` |
| Gateway LAN | `10.0.1.254` |
| Loopback | `172.31.255.2/32` |
| VPN1 Palo Alto | `169.255.0.1` |
| VPN1 FortiGate | `169.255.0.2` |
| VPN2 Palo Alto | `169.255.0.5` |
| VPN2 FortiGate | `169.255.0.6` |

---

## DHCP da filial

O FortiGate atua como servidor DHCP da LAN.

Para a `BRANCH-2`:

| Item | Valor |
|---|---|
| Interface | `port4` |
| Gateway | `10.0.1.254` |
| Pool | `10.0.1.1 - 10.0.1.10` |
| DNS | `10.255.255.1` |

O DHCP relacionado ao `fortilink` permanece como parte do baseline/default do equipamento e não é recriado pelo onboarding.

---

## VPN IPsec

Cada filial utiliza dois túneis route-based para o datacenter.

Baseline do laboratório:

| Parâmetro | Valor |
|---|---|
| IKE | IKEv2 |
| Phase 1 proposal | DES / SHA256 |
| DH Group | 14 |
| Phase 1 lifetime | 28800 s |
| Phase 2 proposal | DES / SHA256 |
| PFS / DH Group | 14 |
| Phase 2 lifetime | 3600 s |
| Authentication | PSK |

> Esses parâmetros reproduzem a baseline efetivamente utilizada no laboratório do desafio. Eles não representam recomendação criptográfica para produção. Em produção devem ser utilizados algoritmos compatíveis com as políticas atuais de segurança e com as capacidades/licenciamento dos equipamentos.

A aplicação consulta as capabilities dos equipamentos para comparar proposals e grupos DH disponíveis antes do provisionamento.

---

## Nautobot como Source of Truth e IPAM

O Nautobot participa ativamente do workflow, e não apenas da documentação posterior.

A integração utiliza a REST API para consultar e criar recursos.

A solução trata:

- prefixo LAN;
- loopback;
- prefixos dos overlays;
- quatro endereços de túnel por branch;
- VPNs;
- quatro VPN Tunnel Endpoints;
- dois VPN Tunnels;
- Phase 1 Policy;
- Phase 2 Policy;
- VPN Profile/metadados associados;
- relacionamentos entre túneis e endpoints;
- metadados criptográficos.

A integração também valida que os dois VPN Tunnels referenciem exatamente os quatro endpoints esperados.

### Alocação e prevenção de overlap

O provider de IPAM consulta o endpoint `available-prefixes` do Nautobot para obter o próximo recurso disponível dentro do pool.

Isso permite retirar a decisão de alocação manual do operador e reduz o risco de overlap.

O fluxo é:

```text
Planejar
   |
   v
Consultar Nautobot
   |
   v
Obter recursos disponíveis
   |
   v
Gerar Candidate
   |
   v
Validar
   |
   v
Reservar
   |
   v
Deploy
```

### PSKs e metadados

As PSKs reais não são versionadas no repositório e não são gravadas no Nautobot como segredo em claro.

O inventário do Nautobot utiliza placeholders identificáveis e marca explicitamente que o PSK real não foi armazenado.

Isso permite documentar o relacionamento da VPN sem transformar o Source of Truth em um repositório inseguro de secrets.

---

## Tratamento de falhas e consistência de estado

O projeto considera falhas parciais.

Antes que qualquer firewall seja alterado, recursos novos criados por uma tentativa que falhou podem ser liberados.

Depois que um equipamento é alterado:

- as reservas permanecem no Nautobot;
- recursos já utilizados não são automaticamente oferecidos a outro site;
- reservas preexistentes também são preservadas.

Esse comportamento reduz o risco de reutilização de endereçamento após um deployment incompleto.

O cleanup implementado respeita dependências entre os objetos, incluindo túneis, endpoints, policies, endereços e prefixos.

---

## Provisionamento end-to-end de filial

O objetivo é minimizar a interação direta do operador com os equipamentos.

```text
Operador
   |
   | parâmetros mínimos do site e acesso
   v
Aplicação
   |
   +--> planeja a branch
   +--> consulta Nautobot
   +--> aloca endereçamento
   +--> gera Candidate
   +--> valida golden/capabilities
   +--> reserva recursos
   +--> cria inventário VPN
   +--> renderiza configs
   +--> configura Palo Alto
   +--> commit PAN-OS
   +--> configura FortiGate
   +--> valida config
   +--> valida operação
```

Fluxo principal:

1. cadastrar/selecionar FortiGate;
2. informar parâmetros da branch e WANs;
3. construir plano;
4. consultar endereçamento;
5. gerar Candidate;
6. validar Candidate;
7. reservar recursos no Nautobot;
8. criar inventário VPN;
9. gerar configuração Palo Alto;
10. gerar configuração FortiGate;
11. aplicar Palo Alto;
12. executar commit;
13. aplicar FortiGate;
14. validar configuração;
15. validar operação.

---

## Palo Alto

O Palo Alto é a extremidade central das VPNs.

O deployment cria/configura elementos relacionados a:

- tunnel interfaces;
- IKE gateways;
- IPsec tunnels;
- associação à zona;
- associação ao virtual router;
- peers BGP;
- endereçamento dos túneis.

O código mantém um contrato determinístico para os IDs das interfaces de túnel utilizadas por cada branch.

A aplicação separa geração, aplicação, commit e compliance.

---

## FortiGate

O FortiGate da filial recebe a baseline específica do site, incluindo:

- hostname;
- WANs;
- LAN;
- DHCP;
- loopback;
- VPN1;
- VPN2;
- overlays;
- firewall objects/policies;
- BGP;
- community-lists;
- route-maps;
- SD-WAN;
- `SLA_DC`.

A configuração gerada é comparada com elementos funcionais da golden.

---

## Validação pós-deployment

O deployment não é considerado concluído apenas porque comandos foram aceitos.

### Config Validation

Verifica presença e coerência de elementos esperados, incluindo:

- hostname;
- LAN;
- gateway;
- DHCP;
- loopback;
- VPN1;
- VPN2;
- endereçamento dos overlays;
- BGP;
- SD-WAN;
- health-check.

### Operational Validation

Verifica o funcionamento resultante, incluindo:

- estado dos túneis;
- dois neighbors BGP;
- rotas;
- rota para o datacenter;
- SD-WAN;
- SLA/health-check;
- reachability.

No laboratório, o fluxo completo da `BRANCH-2` foi validado:

```text
FW-BRANCH-2 provisionado.
Nautobot atualizado.
Palo Alto aplicado.
FortiGate validado.
```

O princípio é:

```text
Configuração presente != Serviço operacional
```

---

## Gerenciamento Multi-Switch

O gerenciamento de switches foi projetado para operar mais de um equipamento de forma centralizada.

A aplicação mantém um inventário persistente de equipamentos e permite selecionar vários switches e várias interfaces na mesma operação.

### Persistência

Os switches são armazenados em:

```text
.runtime/devices.sqlite3
```

Os FortiGates possuem persistência própria em:

```text
.runtime/fortigates.sqlite3
```

A aplicação também utiliza arquivos de chave locais em `.runtime/` para proteção dos dados sensíveis persistidos.

O diretório `.runtime/` não deve ser versionado.

### Inventário de interfaces

A interface apresenta:

- interface;
- status operacional;
- status administrativo;
- modo;
- Access VLAN;
- Voice VLAN;
- descrição;
- PortFast.

Estados tratados incluem:

- Up;
- Down;
- Admin Down;
- not-connected.

Modos tratados incluem:

- Access;
- Trunk;
- Routed.

---

## Operações Multi-Switch

As operações são agrupadas por equipamento e executadas concorrentemente com `ThreadPoolExecutor`.

Existem múltiplos pontos de paralelismo no Web layer e nos serviços de devices.

O projeto controla o número de workers e, nas operações de troubleshooting configuráveis pelo operador, limita o paralelismo total a 8.

Isso permite executar mudanças ou diagnósticos em múltiplos dispositivos sem transformar a aplicação em uma sequência de sessões SSH bloqueantes.

Cada equipamento preserva seu próprio resultado para que falhas sejam identificadas individualmente.

---

## Operações de interfaces

Funcionalidades implementadas:

- Access VLAN;
- Voice VLAN;
- remoção de Voice VLAN;
- descrição;
- remoção de descrição;
- shutdown;
- no shutdown;
- bounce;
- restore default;
- PortFast.

O bounce executa o ciclo administrativo de shutdown/no shutdown pela automação.

A aplicação valida parâmetros antes do envio e possui verificações posteriores para confirmar o estado esperado.

---

## VLANs e configurações gerais

A aplicação suporta:

- alteração de hostname;
- criação de VLAN;
- gerenciamento de VLAN;
- visualização do VLAN database;
- associação de VLAN às interfaces.

As operações podem ser utilizadas em um único equipamento ou em workflows multi-device.

---

## Configuration Management

A solução possui uma área dedicada à administração das configurações.

Funcionalidades:

- leitura de running-config;
- leitura de startup-config;
- comparação Startup x Running;
- identificação de blocos adicionados/removidos;
- save running-config -> startup-config/NVRAM;
- download de running-config;
- download de startup-config;
- download multi-device;
- geração de ZIP quando múltiplos arquivos são baixados;
- backup local;
- backup remoto.

O Candidate de provisionamento também pode ser baixado antes da aplicação.

---

## Backup local, FTP, SFTP e TFTP

Os quatro destinos são implementados de forma nativa:

```text
local
ftp
sftp
tftp
```

### Local

Armazena arquivos no diretório:

```text
backups/
```

### FTP

Implementado com `ftplib`, incluindo:

- host;
- porta;
- usuário;
- senha;
- diretório remoto;
- modo passivo;
- upload binário.

### SFTP

Implementado com Paramiko sobre SSH, incluindo:

- host;
- porta;
- usuário;
- senha;
- diretório remoto;
- validação do arquivo após upload.

### TFTP

Implementado com `tftpy`.

A interface Web permite selecionar protocolo e informar os parâmetros correspondentes.

As mesmas capacidades são disponibilizadas no fluxo multi-switch.

---

## Troubleshooting em múltiplos equipamentos

A aplicação permite execução de diagnóstico de forma paralela.

As operações incluem:

- consulta de interfaces;
- ping;
- traceroute;
- seleção de source L3 por equipamento;
- destino individual por equipamento;
- configuração de paralelismo;
- preservação da ordem/resultados.

O paralelismo de troubleshooting é validado e limitado pela aplicação.

---

## Provisionamento de novos switches

A solução possui uma baseline corporativa de provisionamento.

O código implementa blocos ordenados para geração da configuração, incluindo:

- hostname;
- VLANs;
- AAA;
- grupo RADIUS;
- autenticação RADIUS;
- authorization;
- accounting;
- Change of Authorization;
- 802.1X global;
- 802.1X nas portas de usuário;
- MAB;
- source-interface RADIUS;
- SNMP;
- spanning-tree;
- PortFast;
- BPDU Guard;
- gerenciamento;
- configuração de interfaces;
- parâmetros adicionais definidos pelo perfil.

A aplicação possui preflight e classificação das interfaces para reduzir o risco de aplicar uma baseline incompatível com o equipamento.

### AAA / RADIUS / 802.1X

A baseline implementa:

- `aaa new-model`;
- grupo RADIUS;
- autenticação de login local;
- autenticação 802.1X;
- authorization;
- accounting;
- dynamic authorization/CoA;
- `dot1x system-auth-control`;
- `authentication order dot1x mab`;
- `authentication priority dot1x mab`;
- `dot1x pae authenticator`.

Os valores sensíveis da baseline não são reproduzidos neste README.

### SNMP

A baseline inclui SNMP de monitoramento com community RO e host de gerenciamento definidos no perfil do laboratório.

Credenciais/communities específicas não são expostas nesta documentação.

### Spanning Tree

A baseline inclui:

- Rapid-PVST;
- PortFast padrão;
- BPDU Guard padrão;
- PortFast nas interfaces de usuário conforme a classificação.

### Candidate e Deploy

O fluxo de provisionamento gera a configuração antes de aplicá-la.

O operador pode:

- gerar;
- visualizar;
- revisar;
- baixar;
- aplicar.

O deploy trabalha por blocos de configuração para preservar contextos como AAA, RADIUS e interfaces.

A aplicação não salva automaticamente a startup-config quando um Candidate é aplicado à running-config; o save é uma operação explícita.

---

## Templates

O projeto utiliza dois mecanismos complementares:

1. renderer de baseline Cisco baseado em perfil e blocos ordenados;
2. Jinja2 para configurações FortiGate/Palo Alto e objetos de VPN.

Isso separa parâmetros, lógica e configuração e facilita reutilização.

---

## Segurança operacional

Mecanismos implementados para reduzir risco:

- Candidate antes de Apply;
- preflight;
- validação de capabilities;
- golden compliance;
- proteção da `BRANCH-1`;
- consulta ao Source of Truth;
- alocação pelo IPAM;
- prevenção de overlap;
- backup;
- validação pós-deployment;
- separação Config Validation x Operational Validation;
- persistência local fora do Git;
- preservação de recursos após falha parcial;
- resultados por equipamento em operações multi-device.

Credenciais, tokens e PSKs não devem ser versionados.

---

## Configuração do ambiente

Crie o arquivo local:

```bash
cp .env.example .env
```

Principais variáveis:

```text
SWITCH_HOST=
SWITCH_USERNAME=
SWITCH_PASSWORD=
SWITCH_SECRET=

NAUTOBOT_URL=
NAUTOBOT_TOKEN=
NAUTOBOT_PARENT_PREFIX=
NAUTOBOT_VPN_POOL=169.255.0.0/16
NAUTOBOT_LAN_POOL=10.0.0.0/16
NAUTOBOT_LOOPBACK_POOL=172.31.255.0/24

PALOALTO_HOST=
PALOALTO_USERNAME=
PALOALTO_PASSWORD=
```

O `.gitignore` deve manter fora do repositório:

- `.env`;
- `.venv`;
- `.runtime`;
- backups gerados;
- artefatos de runtime;
- secrets.

---

## Tecnologias e bibliotecas

| Tecnologia | Utilização |
|---|---|
| Python 3.12 | Linguagem principal |
| Flask 3.1 | Aplicação Web |
| Netmiko 4.7 | Automação CLI |
| Paramiko 4.0 | SSH/SFTP |
| Jinja2 3.1 | Templates |
| Requests | Integração REST |
| Nautobot REST API | Source of Truth/IPAM/VPN |
| SQLite | Persistência local |
| ftplib | FTP |
| TFTPy | TFTP |
| NTC Templates/TextFSM | Parsing de outputs |
| Pytest | Testes |
| Ruff | Lint/quality gate |
| Cisco IOS | Switching |
| Fortinet FortiGate | Branch firewall/SD-WAN |
| Palo Alto PAN-OS | Firewall/VPN no datacenter |

---

## Estrutura do repositório

```text
src/
├── branch/       planejamento, golden compliance, reserva e deployment
├── devices/      drivers e managers FortiGate/Palo Alto
├── ipam/         integração com Nautobot/IPAM
├── switch/       Cisco, multi-device, backup, troubleshooting e provisioning
├── templates/    renderer Jinja2
├── vpn/          modelos, addressing e serviços VPN
└── web/          aplicação Flask e orquestração Web

templates/
├── fortigate/
└── paloalto/

golden/
├── baseline FortiGate
└── paloalto/
    └── baseline do datacenter

nautobot/
├── bootstrap/
└── documentação

backups/          backups locais
generated/        configurações geradas
tests/            suíte automatizada
docs/             documentação
.runtime/         bancos SQLite/chaves locais - não versionar
```

---

## Instalação

Requisitos:

- Python 3.12;
- conectividade IP com os equipamentos;
- Nautobot acessível;
- credenciais válidas.

```bash
git clone <URL_DO_REPOSITORIO>
cd mercado-livre-networking-challenge

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Preencha o `.env` com os dados do laboratório.

---

## Execução

```bash
cd mercado-livre-networking-challenge
source .venv/bin/activate
python -m src.web.app
```

A aplicação Flask escuta na porta TCP `5000`.

---

## Métricas do projeto

Na auditoria realizada antes da entrega:

| Métrica | Valor |
|---|---:|
| Arquivos Python | 114 |
| Linhas Python | ~29,3 mil |
| Arquivos de teste | 59 |
| Funções de teste | 478 |
| Testes executados | 495 |

Os números representam o estado auditado do repositório e podem mudar com novas alterações.

---

## Testes e Quality Gate

```bash
ruff check .
pytest -q
git diff --check
```

Estado validado:

```text
Ruff: OK
Pytest: 495 passed
```

A suíte cobre, entre outros pontos:

- parsing e operações Cisco;
- multi-switch;
- paralelismo;
- backups local/FTP/SFTP/TFTP;
- Candidate/Deploy;
- baseline Cisco;
- AAA/RADIUS/802.1X;
- SNMP;
- preflight;
- VPN;
- IPAM;
- Nautobot;
- branch planning;
- golden compliance;
- Palo Alto;
- FortiGate;
- validação operacional;
- rotas Web.

---

## Como demonstrar o projeto

Uma demonstração objetiva pode seguir este roteiro:

1. acessar a interface Web;
2. cadastrar/selecionar dois switches;
3. abrir o workspace Multi-Switch;
4. mostrar inventário e VLAN database;
5. executar uma alteração em múltiplas interfaces;
6. demonstrar bounce ou restore default;
7. abrir Configuration Management;
8. comparar Running x Startup;
9. fazer backup local ou remoto;
10. mostrar o provisionamento de switch;
11. gerar e baixar o Candidate;
12. abrir o módulo de Firewalls;
13. gerar o plano de uma nova branch;
14. mostrar recursos alocados no Nautobot;
15. apresentar as configurações FortiGate/Palo Alto;
16. demonstrar VPN1/VPN2;
17. apresentar os dois neighbors BGP;
18. apresentar SD-WAN e `SLA_DC`;
19. demonstrar reachability de `10.255.255.1`;
20. executar o quality gate.

---

## Evidências

As funcionalidades podem ser evidenciadas por:

- configurações geradas em `generated/`;
- backups em `backups/`;
- Candidate baixável pela interface;
- Running x Startup;
- resultados Web de operações;
- estado do Nautobot;
- estado dos túneis;
- neighbors BGP;
- SD-WAN/SLA;
- execução dos testes automatizados.

Uma evolução planejada é consolidar essas evidências em um único relatório de execução, com timestamp, equipamento, operação, estado anterior, mudança aplicada, estado posterior e PASS/FAIL.

---

## Limitações do laboratório

O projeto foi desenvolvido especificamente para o laboratório do desafio.

As imagens virtuais utilizadas, especialmente no FortiGate, apresentaram limitações de versão/licenciamento/capabilities que influenciaram a baseline disponível.

Por isso:

- a solução consulta capabilities dos equipamentos;
- a configuração criptográfica do laboratório não deve ser usada como recomendação de produção;
- endereçamento e credenciais são específicos do lab;
- decisões de segurança devem ser reavaliadas antes de uso real.

---

## Evoluções futuras

Para produção, seriam recomendadas:

- autenticação da aplicação;
- RBAC da interface;
- secrets manager corporativo;
- banco de dados de produção;
- auditoria persistente;
- filas de execução;
- controle distribuído de concorrência;
- observabilidade centralizada;
- CI/CD;
- integração com ITSM/change management;
- HA da aplicação;
- rollback automático mais abrangente;
- reconciliação desired state x observed state;
- relatório consolidado de evidências;
- telemetria e dashboards.

Esses itens são apresentados como evoluções, não como funcionalidades já entregues.

---

## Resultado

O projeto demonstra uma automação de rede que vai além de executar comandos via SSH.

O fluxo central é:

```text
Intent
  |
  v
Plan
  |
  v
Candidate
  |
  v
Source of Truth
  |
  v
Deployment
  |
  v
Validation
```

Para switching, isso significa centralizar tarefas, administrar múltiplos equipamentos, executar operações em paralelo, gerar backups e provisionar novos switches de acordo com uma baseline corporativa.

Para filiais, significa coordenar Nautobot, Palo Alto, FortiGate, IPsec, iBGP e SD-WAN em um único workflow de onboarding.

O resultado é uma solução de automação padronizada, testável, reproduzível e desenhada para reduzir interação manual e inconsistência operacional.

