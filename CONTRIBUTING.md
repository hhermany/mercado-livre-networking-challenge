# Contributing Guidelines

## Code Style

- Follow PEP 8.
- Use descriptive names for variables, functions and modules.
- Use snake_case for functions and variables.
- Use PascalCase for classes.
- Prefer small functions with a single responsibility.
- Use type hints for function parameters and return values.
- Use docstrings for public functions and classes.
- Comments should explain why something is done, not repeat what the code already says.

## Security

- Never commit credentials, tokens, private keys or sensitive information.
- Credentials must be provided through environment variables or secure runtime input.
- Do not include sensitive information in logs.
- Production configuration backups must not be committed to the public repository.

## Git

Commits should be small, meaningful and focused on one logical change.

Examples:

- `Adiciona conexao SSH com switch Cisco`
- `Implementa configuracao de VLANs`
- `Adiciona validacao de hostname`
- `Implementa backup da configuracao`

Avoid generic messages such as:

- `update`
- `fix`
- `teste`
- `alteracoes`

## Testing

New functionality should be validated before being committed.

Whenever practical, automated tests should be created for logic that does not depend directly on a network device.
