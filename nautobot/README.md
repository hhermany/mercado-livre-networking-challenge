# Nautobot Lab

Este diretório contém os artefatos necessários para reproduzir a configuração utilizada pelo projeto.

## Objetivo

Utilizar o Nautobot como fonte de verdade para o gerenciamento de endereçamento dos túneis VPN.

O pool utilizado pelo laboratório é:

`169.255.0.0/16`

A automação solicita dinamicamente prefixos `/30` disponíveis dentro deste bloco.

## Segurança

Credenciais, tokens, senhas e chaves não são versionados.

Utilize o arquivo `.env.example` como referência e crie um arquivo `.env` local com os valores reais.

## Componentes

- Nautobot
- PostgreSQL
- Redis
- REST API
- Usuário de automação com privilégios mínimos para gerenciamento de prefixos

## Bootstrap

O diretório `bootstrap/` contém o código responsável por criar os objetos necessários no Nautobot para o laboratório.
