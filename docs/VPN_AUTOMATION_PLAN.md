# Plano de Automação de VPN IPsec — FortiGate e Palo Alto

## 1. Objetivo

Este documento descreve o planejamento e a implementação da automação de VPN IPsec entre firewalls Fortinet FortiGate instalados nas filiais e um Palo Alto localizado no datacenter.

O requisito original do desafio solicita o planejamento da automação. Durante o desenvolvimento, o escopo foi ampliado e o fluxo foi efetivamente implementado e validado em laboratório, incluindo integração com Nautobot, geração de configurações, deployment nos dois fabricantes, BGP, SD-WAN e validação pós-deployment.

## 2. Arquitetura

Cada filial utiliza dois túneis IPsec route-based independentes em direção ao Palo Alto do datacenter.

Os túneis formam overlays de camada 3 e são utilizados para estabelecer duas adjacências iBGP entre o FortiGate da filial e o ambiente central.

No FortiGate, os overlays participam da zona SD-WAN VPN-DC e são monitorados pelo health-check SLA_DC.

## 3. Parâmetros necessários

O provisionamento utiliza parâmetros relacionados a:

- identificação da filial;
- endereço de gerenciamento do FortiGate;
- credenciais de acesso;
- interfaces e endereços WAN;
- peers públicos;
- rede LAN;
- loopback;
- redes dos overlays;
- endereços das extremidades dos túneis;
- parâmetros IPsec Phase 1 e Phase 2;
- PSK;
- parâmetros BGP;
- parâmetros SD-WAN.

## 4. Plano de endereçamento

Os principais pools utilizados no laboratório são:

- LAN das filiais: `10.0.0.0/16`
- Loopbacks de gerenciamento: `172.31.255.0/24`
- Overlays VPN: `169.255.0.0/16`
- LAN do datacenter: `10.255.255.0/24`
- Servidor central e destino do SLA: `10.255.255.1`

O endereço `169.255.1.0/30` especificado no enunciado do desafio é contemplado por esse modelo e representa um dos blocos `/30` disponíveis dentro do pool `169.255.0.0/16`.

Na implementação, em vez de manter um único `/30` fixo, o Nautobot/IPAM controla a alocação dos blocos de overlay para cada túnel e filial, permitindo a expansão do ambiente sem reutilização ou sobreposição de endereços. Em cada `/30`, o primeiro endereço utilizável é atribuído ao Palo Alto e o segundo ao FortiGate.

As loopbacks seguem uma convenção determinística:

- BRANCH-1: `172.31.255.1/32`
- BRANCH-2: `172.31.255.2/32`
- BRANCH-3: `172.31.255.3/32`
- BRANCH-X: `172.31.255.X/32`

O Nautobot é utilizado como Source of Truth e IPAM para controlar os recursos de endereçamento e reduzir o risco de overlap.

## 5. Phase 1 e Phase 2

A baseline utilizada no laboratório foi definida de acordo com as capabilities efetivamente disponíveis nas imagens utilizadas.

A configuração do laboratório utiliza IKEv2, parâmetros de Phase 1 e Phase 2 padronizados, PFS e autenticação por PSK.

A aplicação consulta capabilities dos equipamentos para verificar compatibilidade antes do provisionamento.

A configuração criptográfica utilizada no laboratório não deve ser interpretada como recomendação para produção. Em ambiente produtivo, as proposals devem seguir a política de segurança vigente e as capacidades e licenciamento dos equipamentos.

## 6. Ferramentas e integrações

A implementação utiliza:

- Python;
- Flask;
- Netmiko;
- Paramiko;
- Jinja2;
- Requests;
- Nautobot REST API;
- SQLite;
- Fortinet FortiGate;
- Palo Alto PAN-OS;
- Pytest;
- Ruff;
- Git.

O Nautobot funciona como Source of Truth e IPAM, enquanto drivers e serviços específicos da aplicação tratam a interação com cada fabricante.

## 7. Golden Template

A BRANCH-1 é utilizada como referência para novas filiais.

A baseline contempla os componentes necessários à arquitetura, incluindo:

- interfaces;
- LAN;
- loopback;
- IPsec;
- overlays;
- BGP;
- route-maps;
- communities;
- SD-WAN;
- health-check;
- firewall policies.

Novas filiais reutilizam essa estrutura com os parâmetros específicos de cada site.

A aplicação também possui verificações de compliance entre a golden e a configuração candidata.

## 8. Sequência da automação

O fluxo implementado é:

1. cadastro ou seleção do FortiGate;
2. definição dos parâmetros da filial;
3. construção do plano;
4. consulta ao Nautobot/IPAM;
5. alocação dos recursos de endereçamento;
6. geração do Candidate;
7. validação da golden e das capabilities;
8. reserva dos recursos no Nautobot;
9. construção do inventário VPN;
10. geração da configuração do Palo Alto;
11. geração da configuração do FortiGate;
12. aplicação da configuração no Palo Alto;
13. commit no PAN-OS;
14. aplicação da configuração no FortiGate;
15. validação da configuração;
16. validação operacional.

## 9. Automação do Palo Alto

O Palo Alto representa a extremidade central das VPNs.

A automação trata elementos relacionados a:

- tunnel interfaces;
- IKE gateways;
- IPsec tunnels;
- endereçamento dos overlays;
- zona;
- virtual router;
- peers BGP.

A aplicação separa geração, aplicação, commit e validação.

## 10. Automação do FortiGate

A configuração da filial contempla:

- hostname;
- interfaces WAN;
- LAN;
- DHCP;
- loopback;
- VPN1;
- VPN2;
- overlays;
- BGP;
- communities;
- route-maps;
- SD-WAN;
- health-check SLA_DC;
- políticas e objetos necessários.

## 11. BGP

Os dois overlays são utilizados para estabelecimento das adjacências BGP.

A arquitetura utiliza AS 65001 e contempla:

- dois neighbors iBGP;
- anúncio da LAN;
- anúncio da loopback;
- iBGP multipath;
- communities;
- route-maps;
- políticas específicas dos overlays.

A utilização de BGP permite troca dinâmica de rotas entre filial e datacenter.

## 12. SD-WAN e Self-Healing

Os overlays participam da arquitetura SD-WAN do FortiGate.

O health-check SLA_DC utiliza 10.255.255.1 como destino central de medição.

A baseline utiliza:

- latência máxima: 100 ms;
- jitter máximo: 20 ms;
- perda máxima: 5%;
- intervalo: 1000 ms;
- timeout: 250 ms;
- fail time: 2;
- recovery time: 10.

A integração BGP e SD-WAN permite que o estado dos caminhos participe da decisão de encaminhamento e da recuperação da conectividade.

## 13. Nautobot

Durante o onboarding, a aplicação consulta e registra recursos no Nautobot.

Entre os objetos tratados estão:

- LAN;
- loopback;
- prefixos dos overlays;
- endereços das extremidades;
- VPNs;
- VPN Tunnel Endpoints;
- VPN Tunnels;
- Phase 1 Policy;
- Phase 2 Policy;
- VPN Profile e metadados associados.

A aplicação consulta recursos disponíveis no IPAM em vez de depender da escolha manual do próximo prefixo.

PSKs reais não são publicadas no repositório nem armazenadas em claro no Nautobot.

## 14. Considerações sobre fabricantes diferentes

A automação FortiGate e Palo Alto precisa considerar diferenças de:

- modelo de configuração;
- nomenclatura;
- APIs;
- processo de commit;
- objetos;
- policies;
- representação dos túneis;
- parâmetros IPsec;
- roteamento.

Por isso, a solução utiliza drivers e templates específicos por fabricante, mantendo um modelo comum de planejamento e provisionamento.

## 15. Validação da configuração

Após o deployment, a aplicação verifica a presença e a coerência dos componentes esperados.

Entre as verificações estão:

- hostname;
- LAN;
- gateway;
- DHCP;
- loopback;
- VPN1;
- VPN2;
- overlays;
- parâmetros BGP;
- SD-WAN;
- health-check.

## 16. Validação operacional

A existência da configuração não significa necessariamente que o serviço esteja operacional.

A segunda etapa verifica:

- estado dos túneis;
- dois neighbors BGP;
- rotas;
- rota para o datacenter;
- SD-WAN;
- SLA_DC;
- reachability.

O princípio adotado é que configuração presente não é, isoladamente, evidência de serviço operacional.

## 17. Tratamento de falhas

O workflow considera deployments parciais.

Antes que qualquer firewall seja alterado, recursos novos criados por uma tentativa que falhou podem ser liberados.

Depois que um equipamento é alterado, os recursos utilizados são preservados no Source of Truth para evitar reutilização acidental por outra filial.

O cleanup respeita dependências entre objetos de VPN, endpoints, policies, endereços e prefixos.

## 18. Resultado

O requisito original solicitava o planejamento da automação de uma VPN IPsec entre FortiGate e Palo Alto.

A implementação desenvolvida amplia esse requisito ao integrar Nautobot/IPAM, planejamento de endereçamento, Candidate, Palo Alto, FortiGate, IPsec, BGP, SD-WAN e validação em um único workflow funcional de onboarding de filiais.
