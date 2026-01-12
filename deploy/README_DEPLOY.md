Guia rápido: configurar Nginx para servir `STATIC` e `MEDIA` (GESTAO_OPERACIONAL)

Objetivo
- Configurar o Nginx para servir os arquivos estáticos (`STATIC_ROOT`) e os arquivos de mídia (`MEDIA_ROOT`) diretamente.
- Evitar que o Django entregue arquivos estáticos em produção (melhor desempenho e menos carga no WSGI).

Arquivos criados
- `deploy/nginx/gestao_operacional.conf` — exemplo de server block Nginx.

Passos recomendados (no servidor)
1) Verifique os caminhos em `settings.py`:
   - `STATIC_ROOT` deve apontar para o diretório onde você executará `python manage.py collectstatic`.
   - `MEDIA_ROOT` deve apontar para o diretório onde os uploads (fotos) são gravados.

2) Colete arquivos estáticos (no ambiente virtual do projeto):

```bash
# vá para o diretório do projeto (ajuste conforme seu ambiente)
cd /var/www/html/GESTAO_OPERACIONAL
# ative o venv se houver
source /path/to/venv/bin/activate
python manage.py collectstatic --noinput
```

3) Ajuste permissões (exemplo seguro):

```bash
# garantir que o usuário do nginx (www-data) consiga ler
sudo chown -R root:www-data /var/www/html/GESTAO_OPERACIONAL/static
sudo chown -R root:www-data /var/www/html/GESTAO_OPERACIONAL/fotos_rdo
sudo find /var/www/html/GESTAO_OPERACIONAL/static -type d -exec chmod 755 {} +
sudo find /var/www/html/GESTAO_OPERACIONAL/static -type f -exec chmod 644 {} +
sudo find /var/www/html/GESTAO_OPERACIONAL/fotos_rdo -type d -exec chmod 755 {} +
sudo find /var/www/html/GESTAO_OPERACIONAL/fotos_rdo -type f -exec chmod 644 {} +

# se o processo de upload precisa escrever em fotos_rdo, dê permissão ao usuário responsável pelo processo (ex: www-data ou usuário do serviço)
# sudo chown -R www-data:www-data /var/www/html/GESTAO_OPERACIONAL/fotos_rdo
```

4) Coloque a configuração do Nginx em `/etc/nginx/sites-available/gestao_operacional` e crie o symlink:

```bash
sudo cp deploy/nginx/gestao_operacional.conf /etc/nginx/sites-available/gestao_operacional
sudo ln -s /etc/nginx/sites-available/gestao_operacional /etc/nginx/sites-enabled/gestao_operacional
```

5) Teste a configuração e recarregue o Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

6) Verifique no navegador:
- Acesse `http://<seu-host>/media/<nome-da-imagem>` e `http://<seu-host>/static/<algum-css>` para checar que são servidos corretamente.

7) Remover fallback do Django (recomendado após confirmar funcionamento)
- No repositório, remova a seção temporária que adiciona `static(settings.MEDIA_URL...)` quando `DEBUG=False` em `setup/urls.py`.
- Commit e deploy da mudança.

Exemplo de commit para reverter a correção temporária (no servidor ou local):

```bash
# editar urls.py e remover o bloco:
# if not settings.DEBUG: ... urlpatterns += static(...)
# depois:
git add setup/urls.py
git commit -m "Remover fallback temporário para MEDIA; Nginx agora serve media/static"
git push
```

Considerações extras
- Se usar SELinux, ajuste contextos com `semanage fcontext` e `restorecon`.
- Se usar proxied HTTPS (Cloudflare etc), certifique-se que `X-Forwarded-Proto` é passado corretamente e que `SECURE_PROXY_SSL_HEADER` em Django está configurado se necessário.
- Se uploads são feitos por um processo diferente (um worker ou container), garanta que ambos escrevam e o Nginx leia do mesmo `MEDIA_ROOT`.

Cache e compressão (opcional)
- **WhiteNoise:** se preferir não usar nginx para estáticos em deployments simples, instale `whitenoise` (adicionado em `requirements.txt`) e habilite `WhiteNoiseMiddleware` + `CompressedManifestStaticFilesStorage` em `setup/settings.py`. Isso gera arquivos estáticos com hash e serve versões comprimidas (gzip/brotli).
- **Cabeçalhos long-lived:** quando servir `STATIC_ROOT` via nginx, configure `Cache-Control: public, max-age=31536000, immutable` para assets versionados (coleção com hashes). Isso evita que clientes precisem limpar cache após deploy.

Precisa que eu aplique a remoção do fallback em `setup/urls.py` agora (faço o patch) ou quer fazer isso após confirmar que o Nginx está servindo corretamente?