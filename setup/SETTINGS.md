Instruções para configurações locais

Este repositório mantém as configurações base em `setup/settings.py` para desenvolvimento local. Para evitar subir segredos e overrides de ambiente, siga estas recomendações:

- Nunca commite valores sensíveis (SECRET_KEY, credenciais, etc.).
- Crie `setup/settings_local.py` a partir de `setup/settings_local.py.sample` e edite-o com suas overrides locais.
- `setup/settings_local.py` está no `.gitignore`, então não será rastreado pelo Git.

Exemplo rápido (PowerShell):

```powershell
Copy-Item setup\settings_local.py.sample setup\settings_local.py
# Edite setup\settings_local.py e ajuste SECRET_KEY, DEBUG, DATABASES, etc.
```

Se quiser parar de rastrear o arquivo `setup/settings.py` (por exemplo já contém segredos), rode os comandos Git abaixo **após** confirmar que todos os desenvolvedores têm uma cópia dos ajustes locais:

```bash
git rm --cached setup/settings.py
git commit -m "Stop tracking setup/settings.py"
```

Depois de `git rm --cached`, o arquivo permanece no seu disco mas não será mais enviado ao repositório.
