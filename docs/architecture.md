# Arquitetura do Projeto

## Objetivo

Separar responsabilidades para facilitar manutenção, testes e segurança.

## Componentes

### Frontend
Responsável por:
- receber VLAN ID e nome;
- receber hostname;
- iniciar a automação;
- exibir sucesso, falhas e divergências.

### Application Layer
Responsável por:
- coordenar o fluxo da automação;
- validar entradas;
- chamar os módulos de rede;
- retornar resultados ao frontend.

### Network Layer
Responsável por:
- conectar ao switch Cisco;
- aplicar VLANs;
- alterar hostname;
- salvar configuração.

### Validation Layer
Responsável por:
- consultar o estado atual do switch;
- comparar configuração desejada e aplicada;
- reportar divergências.

### Backup Layer
Responsável por:
- coletar a configuração;
- salvar backup com hostname e timestamp;
- evitar exposição de informações sensíveis.

## Princípios

- Separação de responsabilidades.
- Funções pequenas e testáveis.
- Credenciais fora do código.
- Validação de entrada.
- Tratamento explícito de erros.
- Logs sem dados sensíveis.
- Dependências mínimas.
